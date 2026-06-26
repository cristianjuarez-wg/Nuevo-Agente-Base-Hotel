"""
API Router para leer la transcripción de una conversación del agente Aura.

Tickets y leads guardan el `session_id` de la charla que los originó; este endpoint
devuelve esos mensajes para mostrarlos en el backoffice (panel del ticket / del lead).
Solo lectura: no toca cómo se crean tickets, leads ni la conversación.
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.hotel import Booking
from app.core.logging_config import get_logger
# Ventana "en vivo" centralizada en el servicio de control (fuente única).
from app.services.conversation_control_service import LIVE_WINDOW_MINUTES

logger = get_logger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _phone_from_wa_session(session_id: str) -> Optional[str]:
    """Deriva el teléfono (+549...) de un session_id de WhatsApp ('wa_<phone>')."""
    return ("+" + session_id[3:]) if (session_id or "").startswith("wa_") else None


@router.get("")
async def list_conversations(
    channel: str = Query("whatsapp"),
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lista las conversaciones de un canal, de la más reciente a la más vieja.

    `channel="all"` trae web + whatsapp juntas (bandeja en vivo del backoffice); cualquier
    otro valor filtra por ese canal (compat: el sub-tab de Leads pasa "whatsapp").
    Enriquece cada fila con teléfono/nombre del Contact, un preview del último mensaje y un
    flag `is_live` (actividad en los últimos LIVE_WINDOW_MINUTES).
    """
    q = db.query(Conversation)
    if channel and channel != "all":
        q = q.filter(Conversation.channel == channel)
    total = q.count()
    rows = (
        q.order_by(Conversation.last_message_at.desc().nullslast(),
                   Conversation.started_at.desc())
        .limit(limit).offset(offset).all()
    )

    # Lookup de contactos en lote (evita N+1).
    contact_ids = [r.contact_id for r in rows if r.contact_id]
    contacts = {}
    if contact_ids:
        for c in db.query(Contact).filter(Contact.id.in_(contact_ids)).all():
            contacts[c.id] = c

    # Preview del último mensaje por sesión, en lote (evita N+1). Tomamos el más reciente
    # de cada session_id presente en esta página de resultados.
    session_ids = [r.session_id for r in rows]
    previews = {}
    if session_ids:
        msgs = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.session_id.in_(session_ids))
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .all()
        )
        for m in msgs:
            if m.session_id not in previews:  # el primero por sesión es el más reciente
                previews[m.session_id] = {"role": m.role, "content": m.content or ""}

    live_cutoff = datetime.utcnow() - timedelta(minutes=LIVE_WINDOW_MINUTES)

    def _phone_from_session(sid: str) -> Optional[str]:
        return ("+" + sid[3:]) if (sid or "").startswith("wa_") else None

    # Bookings en lote (para guest_status: alojado ahora vs reserva futura). Una sola query.
    from datetime import date as _date
    today = _date.today()
    staying_now: set = set()   # contact_ids con estadía activa hoy
    upcoming: set = set()      # contact_ids con reserva futura
    if contact_ids:
        bookings = (
            db.query(Booking.contact_id, Booking.check_in, Booking.check_out)
            .filter(Booking.contact_id.in_(contact_ids), Booking.status != "cancelled")
            .all()
        )
        for cid, ci, co in bookings:
            if ci and co and ci <= today <= co:
                staying_now.add(cid)
            elif ci and ci > today:
                upcoming.add(cid)

    # Leads en lote por session_id (fallback de nombre cuando la conversación no tiene Contact).
    leads_by_session: dict = {}
    if session_ids:
        for ld in db.query(Lead).filter(Lead.session_id.in_(session_ids)).all():
            # El más reciente por sesión gana (sobrescribe); con nombre real preferido.
            existing = leads_by_session.get(ld.session_id)
            if existing is None or (ld.name and not existing.name):
                leads_by_session[ld.session_id] = ld

    def _guest_status(cid: Optional[int], contact: Optional[Contact]) -> Optional[str]:
        """Estado del interlocutor, por prioridad de accionabilidad. None si es anónimo."""
        if not cid or not contact:
            return None
        if cid in staying_now:
            return "in_house"
        if cid in upcoming:
            return "upcoming"
        if (contact.purchases_made or 0) > 0 or contact.contact_type in ("customer", "both"):
            return "customer"
        return "lead"

    items = []
    for r in rows:
        c = contacts.get(r.contact_id)
        phone = (c.phone_number if c else None) or _phone_from_session(r.session_id)
        # Nombre: 1) Contact, 2) Lead (por session), 3) display de anónimo según canal.
        name = (c.full_name or c.first_name) if c else None
        if not name:
            ld = leads_by_session.get(r.session_id)
            if ld and ld.name:
                name = (f"{ld.name} {ld.last_name}".strip() if ld.last_name else ld.name)
        display_name = name or (phone if r.channel == "whatsapp" and phone else "Visitante web")
        prev = previews.get(r.session_id)
        preview_text = (prev["content"][:120] if prev else "")
        is_live = bool(r.last_message_at and r.last_message_at >= live_cutoff)
        tk = (r.extra_metadata or {}).get("takeover")
        takeover = {"active": True, "staff_name": tk.get("staff_name", "")} if (tk and tk.get("active")) else None
        items.append({
            "session_id": r.session_id,
            "contact_id": r.contact_id,
            "phone": phone,
            "name": name,
            "display_name": display_name,
            "guest_status": _guest_status(r.contact_id, c),
            "channel": r.channel,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
            "message_count": r.message_count,
            "status": r.status,
            "lead_generated": r.lead_generated,
            "last_message_preview": preview_text,
            "last_message_role": prev["role"] if prev else None,
            "is_live": is_live,
            "takeover": takeover,
        })
    return {"conversations": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{session_id}/messages")
async def get_conversation_messages(
    session_id: str,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Devuelve los mensajes de una conversación (por session_id) en orden cronológico.

    Se usa para visualizar, desde el ticket o el lead, la charla con Aura que los generó.
    Si el session_id no tiene mensajes (p. ej. un ticket creado por el equipo), devuelve
    una lista vacía.
    """
    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .limit(limit)
        .all()
    )
    return {
        "session_id": session_id,
        "messages": [m.to_dict() for m in messages],
        "total": len(messages),
    }


# ── Toma de control humana (HITL) ─────────────────────────────────────────────
# Un humano puede tomar el control de una conversación: Aura se pausa, el humano responde,
# y libera (o la conversación se auto-libera por inactividad). NO se exige X-Admin-Key: es una
# acción operativa frecuente y no destructiva (a diferencia de resetear la base o los topes de
# gasto, que sí la requieren). El acceso al backoffice es la barrera para estas acciones.

class TakeoverPayload(BaseModel):
    staff_id: Optional[int] = None
    staff_name: Optional[str] = ""


class ReplyPayload(BaseModel):
    message: str
    staff_id: Optional[int] = None
    staff_name: Optional[str] = ""


_WEB_OFFLINE_MSG = ("El visitante cerró el chat web; no se puede tomar el control. "
                    "Para retomar contacto, usá WhatsApp.")


@router.post("/{session_id}/takeover")
async def takeover_conversation(session_id: str, payload: TakeoverPayload,
                                db: Session = Depends(get_db)):
    """Un humano toma el control: Aura deja de responder en esta conversación."""
    from app.services import conversation_control_service as conv_ctrl
    try:
        ok = conv_ctrl.take_over(db, session_id, payload.staff_id, payload.staff_name or "")
    except conv_ctrl.WebChatOffline:
        raise HTTPException(status_code=409, detail=_WEB_OFFLINE_MSG)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"taken_over": True, "state": conv_ctrl.get_state(db, session_id)}


@router.post("/{session_id}/release")
async def release_conversation(session_id: str, db: Session = Depends(get_db)):
    """Libera la conversación: Aura retoma."""
    from app.services import conversation_control_service as conv_ctrl
    conv_ctrl.release(db, session_id, reason="manual")
    return {"released": True}


@router.post("/{session_id}/reply")
async def human_reply(session_id: str, payload: ReplyPayload, db: Session = Depends(get_db)):
    """Envía una respuesta HUMANA al huésped y la registra en la conversación.

    - WhatsApp: se entrega vía Twilio (whatsapp_service.send_text).
    - Web: se persiste; el widget la recibirá por WebSocket (realtime de Etapa 2).
    El mensaje se guarda con role='assistant' + metadata sent_by (staff) para distinguirlo de
    Aura sin romper las lecturas que asumen user|assistant. Refresca la actividad humana
    (postpone el auto-release).
    """
    from app.services import conversation_control_service as conv_ctrl
    from app.services.agent_service import agent_service

    text = (payload.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    # Si no estaba tomada, la tomamos implícitamente (responder = tomar el control).
    # Si es un chat web ya inactivo, no se puede entregar la respuesta → 409 (no persistir).
    if not conv_ctrl.is_human_controlled(db, session_id):
        try:
            conv_ctrl.take_over(db, session_id, payload.staff_id, payload.staff_name or "")
        except conv_ctrl.WebChatOffline:
            raise HTTPException(status_code=409, detail=_WEB_OFFLINE_MSG)

    delivered = None
    phone = _phone_from_wa_session(session_id)
    if phone:
        from app.services.whatsapp_service import whatsapp_service
        delivered = whatsapp_service.send_text(phone, text)
        if delivered is False:
            logger.error("Respuesta humana: Twilio rechazó el envío",
                         session_id=session_id, phone=phone)

    # Persistir el mensaje del humano (visible en la bandeja y en el transcripto).
    try:
        agent_service._save_message_to_db(
            db=db, session_id=session_id, role="assistant",
            content=text, context_type="pre_sale",
        )
    except Exception as e:  # noqa: BLE001
        logger.error("No se pudo guardar la respuesta humana", session_id=session_id, error=str(e))

    conv_ctrl.touch_activity(db, session_id)

    # Push en vivo al widget web: si hay un visitante con el chat abierto (WS suscrito a esta
    # sesión), recibe el mensaje del humano al instante. No-op si no hay listeners (p. ej.
    # WhatsApp, que ya entregó por Twilio). Best-effort: un fallo no rompe la respuesta.
    pushed = 0
    try:
        from app.services.ws_hub import ws_hub
        pushed = await ws_hub.broadcast(session_id, {
            "type": "human_message",
            "content": text,
            "staff_name": payload.staff_name or "",
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo transmitir por WebSocket", session_id=session_id, error=str(e))

    return {"sent": True, "delivered_whatsapp": delivered, "ws_pushed": pushed}


@router.websocket("/ws/{session_id}")
async def conversation_ws(websocket: WebSocket, session_id: str):
    """Canal de SOLO RECEPCIÓN para el widget del chat web: recibe las respuestas humanas en
    vivo (cuando un asesor tomó la conversación). El visitante sigue ENVIANDO por HTTP
    (/api/chat/message); este socket solo empuja mensajes del servidor al cliente.

    Valida el Origin a mano: el CORSMiddleware NO cubre el handshake WebSocket.
    """
    from app.services.ws_hub import ws_hub, origin_allowed

    if not origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008)  # policy violation
        logger.warning("WS rechazado por Origin", origin=websocket.headers.get("origin"))
        return

    await websocket.accept()
    await ws_hub.connect(session_id, websocket)
    try:
        # Mantener la conexión viva. No procesamos lo que envíe el cliente (solo ping/keepalive);
        # receive_text se bloquea hasta que llega algo o el socket se cierra.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("WS error", session_id=session_id, error=str(e))
    finally:
        await ws_hub.disconnect(session_id, websocket)
