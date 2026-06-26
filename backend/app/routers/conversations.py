"""
API Router para leer la transcripción de una conversación del agente Aura.

Tickets y leads guardan el `session_id` de la charla que los originó; este endpoint
devuelve esos mensajes para mostrarlos en el backoffice (panel del ticket / del lead).
Solo lectura: no toca cómo se crean tickets, leads ni la conversación.
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.contact import Contact
from app.core.admin_auth import require_admin_key
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _phone_from_wa_session(session_id: str) -> Optional[str]:
    """Deriva el teléfono (+549...) de un session_id de WhatsApp ('wa_<phone>')."""
    return ("+" + session_id[3:]) if (session_id or "").startswith("wa_") else None

# Una conversación se considera "en vivo" si tuvo actividad en los últimos N minutos.
LIVE_WINDOW_MINUTES = 5


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

    items = []
    for r in rows:
        c = contacts.get(r.contact_id)
        phone = (c.phone_number if c else None) or _phone_from_session(r.session_id)
        name = (c.full_name or c.first_name) if c else None
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
# y libera (o la conversación se auto-libera por inactividad). Acciones críticas → X-Admin-Key.

class TakeoverPayload(BaseModel):
    staff_id: Optional[int] = None
    staff_name: Optional[str] = ""


class ReplyPayload(BaseModel):
    message: str
    staff_id: Optional[int] = None
    staff_name: Optional[str] = ""


@router.post("/{session_id}/takeover", dependencies=[Depends(require_admin_key)])
async def takeover_conversation(session_id: str, payload: TakeoverPayload,
                                db: Session = Depends(get_db)):
    """Un humano toma el control: Aura deja de responder en esta conversación."""
    from app.services import conversation_control_service as conv_ctrl
    ok = conv_ctrl.take_over(db, session_id, payload.staff_id, payload.staff_name or "")
    if not ok:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"taken_over": True, "state": conv_ctrl.get_state(db, session_id)}


@router.post("/{session_id}/release", dependencies=[Depends(require_admin_key)])
async def release_conversation(session_id: str, db: Session = Depends(get_db)):
    """Libera la conversación: Aura retoma."""
    from app.services import conversation_control_service as conv_ctrl
    conv_ctrl.release(db, session_id, reason="manual")
    return {"released": True}


@router.post("/{session_id}/reply", dependencies=[Depends(require_admin_key)])
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
    if not conv_ctrl.is_human_controlled(db, session_id):
        conv_ctrl.take_over(db, session_id, payload.staff_id, payload.staff_name or "")

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
    # TODO(realtime): empujar este mensaje al widget web por WebSocket cuando esté el canal.
    return {"sent": True, "delivered_whatsapp": delivered}
