"""
Webhook de Instagram (Meta Messaging API) — canal de captación de leads vía DM.

Espejo del webhook de WhatsApp (routers/whatsapp.py): traduce entre Meta y el agente
existente. Recibe el DM entrante, lo pasa por `agent_service.chat(db, message, session_id)`
(la MISMA entrada que el chat web y WhatsApp → flujo de preventa completo) y responde el DM
vía instagram_service. No reimplementa lógica del agente.

Decisiones de diseño:
- El IGSID (Instagram-scoped ID del usuario) ES la sesión: `session_id = "ig_" + <IGSID>`.
  Así Aura recuerda el hilo de ese usuario entre mensajes, igual que WhatsApp con el teléfono.
- Rol: siempre HUÉSPED (staff/dueño no operan por Instagram).
- El @username se guarda en Conversation.extra_metadata["ig_username"] para mostrarlo en el
  backoffice (los usuarios de IG no tienen teléfono).
- Funciona con la app de Meta en modo desarrollo (testers, sin App Review) — ver INSTAGRAM_SETUP.md.
"""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from app.services.agent_service import agent_service
from app.services.instagram_service import instagram_service
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/instagram", tags=["Instagram"])

CHAT_TIMEOUT_SECONDS = 60


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación del webhook de Meta: valida hub.verify_token y devuelve hub.challenge.

    Meta llama este GET al configurar el webhook en la app. Si el token no coincide (o no hay
    token configurado), 403.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    expected = (settings.INSTAGRAM_VERIFY_TOKEN or "").strip()
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    logger.warning("Instagram: verificación de webhook rechazada", mode=mode)
    return Response(status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request):
    """Recibe DMs entrantes de Instagram (formato Meta).

    Estructura: {"object": "instagram", "entry": [{"messaging": [{"sender": {"id": IGSID},
    "message": {"text": ...}}]}]}. Respondemos 200 enseguida y procesamos en background
    (mismo patrón que el webhook de Twilio). Los echoes (nuestros propios envíos) se ignoran.
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — payload no-JSON: 200 igual (Meta reintenta si no)
        return Response(status_code=200)

    for entry in (payload.get("entry") or []):
        for event in (entry.get("messaging") or []):
            msg = event.get("message") or {}
            # Ignorar echoes (mensajes que enviamos nosotros) y eventos sin texto.
            if msg.get("is_echo"):
                continue
            igsid = (event.get("sender") or {}).get("id")
            text = msg.get("text")
            if not igsid or not text:
                continue
            asyncio.create_task(_process_and_reply(str(igsid), text))

    return Response(status_code=200)


async def _process_and_reply(igsid: str, body: str) -> None:
    """Procesa el DM con el agente (flujo de preventa) y responde por Instagram.

    Corre en background con su propia sesión de DB (la del request ya se cerró).
    """
    from app.models.database import SessionLocal

    session_id = "ig_" + igsid

    db = SessionLocal()
    try:
        # GATE DE TOMA DE CONTROL HUMANA: si un humano tomó esta conversación, Aura NO
        # responde. Guardamos el mensaje entrante (visible en la bandeja) y cortamos.
        from app.services import conversation_control_service as conv_ctrl
        if conv_ctrl.is_human_controlled(db, session_id):
            try:
                agent_service._save_message_to_db(
                    db=db, session_id=session_id, role="user",
                    content=body, context_type="pre_sale",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Instagram: no se pudo guardar mensaje en takeover",
                               session_id=session_id, error=str(e))
            logger.info("Instagram: conversación bajo control humano, Aura no responde",
                        session_id=session_id)
            return

        # Despachar al agente (huésped siempre): mismo flujo de preventa que web/WhatsApp.
        try:
            result = await asyncio.wait_for(
                agent_service.chat(db, body, session_id),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("Instagram: el agente tardó demasiado", session_id=session_id)
            instagram_service.send_text(
                igsid, "Disculpá, estoy tardando más de lo normal. ¿Podés repetirme tu consulta?"
            )
            return

        # Identidad IG: guardar el @username en la conversación (una vez, best-effort).
        _store_username_once(db, session_id, igsid)

        # Responder el DM. IG es texto plano: reutilizamos el formateador de WhatsApp
        # (markdown → texto). Las habitaciones van con precios en el propio texto del agente.
        from app.routers.whatsapp import to_whatsapp_text
        reply = to_whatsapp_text(result.get("response") or "")
        if reply:
            ok = instagram_service.send_text(igsid, reply)
            if ok is False:
                logger.error("Instagram: no se pudo enviar la respuesta al usuario",
                             session_id=session_id)
    except Exception as e:  # noqa: BLE001
        logger.error("Instagram: error procesando mensaje", error=str(e), session_id=session_id)
        instagram_service.send_text(
            igsid, "Tuvimos un inconveniente procesando tu mensaje. Intentá de nuevo en un momento."
        )
    finally:
        db.close()


def _store_username_once(db, session_id: str, igsid: str) -> None:
    """Guarda el @username del usuario en Conversation.extra_metadata (si no está ya).

    Best-effort: requiere credenciales de Meta para el lookup; sin ellas queda sin username
    (el backoffice muestra el IGSID). Reasigna el dict para que SQLAlchemy persista el JSON.
    """
    try:
        from app.models.conversation import Conversation
        conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
        if not conv or (conv.extra_metadata or {}).get("ig_username"):
            return
        username = instagram_service.get_username(igsid)
        if not username:
            return
        meta = dict(conv.extra_metadata or {})
        meta["ig_username"] = username
        conv.extra_metadata = meta
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("Instagram: no se pudo guardar el username", session_id=session_id,
                       error=str(e))
