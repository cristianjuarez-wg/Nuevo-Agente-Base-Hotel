"""
Webhook de WhatsApp (Twilio Sandbox) — canal adicional para la demo.

Traduce entre Twilio y el agente existente: recibe el mensaje entrante, lo pasa por
`agent_service.chat(db, message, session_id)` (la MISMA entrada que el chat web) y
envía la respuesta de vuelta por WhatsApp. No reimplementa lógica del agente.

Decisiones de diseño (ver plan):
- El número de WhatsApp ES la sesión: `session_id = "wa_" + <teléfono sin '+'>`. Así Aura
  recuerda el hilo de ese número entre mensajes, igual que una conversación real.
- Respuesta = texto del agente + (opcional) fotos de las habitaciones ofrecidas en el turno.
- Envío vía REST de Twilio (no TwiML), porque texto+imagen puede ser varios mensajes.
"""
import asyncio
import re

from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services.agent_service import agent_service
from app.services.contact_service import ContactService
from app.services.whatsapp_service import whatsapp_service
from app.utils.phone_normalizer import normalize_phone
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])

CHAT_TIMEOUT_SECONDS = 60
_FALLBACK_IMG = "https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_02-0b2b9eb8-1920w.jpg"

_contact_service = ContactService()


def to_whatsapp_text(text: str) -> str:
    """Convierte el Markdown del agente al formato de WhatsApp.

    WhatsApp usa *negrita* (un asterisco), no **negrita** (Markdown). También quitamos
    encabezados Markdown y enlaces, que no se renderizan en WhatsApp.
    """
    if not text:
        return ""
    # **negrita** -> *negrita*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # Encabezados "### titulo" -> "titulo"
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # [texto](url) -> texto
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return text.strip()


def _room_caption(room: dict) -> str:
    """Arma el texto que acompaña la foto de una habitación."""
    name = room.get("room_type") or "Habitación"
    price_usd = room.get("total_price_usd") or room.get("base_price_usd")
    price_night = room.get("base_price_usd")
    nights = room.get("nights")

    lines = [f"*{name}*"]
    if room.get("view"):
        lines.append(f"🌅 {room['view']}")
    if room.get("bed_config"):
        lines.append(f"🛏️ {room['bed_config']}")
    if room.get("capacity"):
        lines.append(f"👥 Hasta {room['capacity']} huéspedes")
    if price_usd and nights:
        lines.append(f"💵 USD {price_usd:.0f} total ({nights} noche/s · USD {price_night:.0f}/noche)")
    elif price_night:
        lines.append(f"💵 Desde USD {price_night:.0f}/noche")
    lines.append(f"\n➡️ Respondé *RESERVAR {name}* para reservar esta habitación.")
    return "\n".join(lines)


def _send_agent_reply(to_phone: str, result: dict) -> None:
    """Envía al usuario la respuesta del agente: texto + fotos de habitaciones."""
    # 1) Texto principal del agente.
    body = to_whatsapp_text(result.get("response", ""))
    if body:
        whatsapp_service.send_text(to_phone, body)

    # 2) Habitaciones ofrecidas este turno -> una foto + caption por habitación.
    rooms = result.get("rooms_offered") or []
    for room in rooms[: settings.WHATSAPP_MAX_ROOM_CARDS]:
        images = room.get("images") or []
        image = images[0] if images else _FALLBACK_IMG
        caption = _room_caption(room)
        whatsapp_service.send_media(to_phone, caption, image)


async def _process_and_reply(from_field: str, body: str, profile_name: str) -> None:
    """Procesa el mensaje con el agente y responde por WhatsApp. Corre en background.

    Usa su propia sesión de DB porque la del request ya se cerró cuando esto ejecuta.
    """
    from app.models.database import SessionLocal

    # Teléfono: viene como "whatsapp:+549..." -> nos quedamos con "+549...".
    raw_phone = from_field.replace("whatsapp:", "").strip()
    phone = normalize_phone(raw_phone)
    if not phone:
        logger.warning("WhatsApp: teléfono inválido", from_field=from_field)
        return

    session_id = "wa_" + phone.lstrip("+")
    db = SessionLocal()
    try:
        # Vincular/crear el Contact por teléfono (Visión 360°).
        try:
            _contact_service.get_or_create_contact(phone=phone, name=profile_name or None, db=db)
        except Exception as e:  # noqa: BLE001 — no bloquear la respuesta por esto
            logger.warning("WhatsApp: no se pudo crear/vincular Contact", error=str(e))

        # Pre-cargar el teléfono de WhatsApp en el Lead: ya conocemos el número, así el
        # agente no necesita pedirlo (ver build_whatsapp_contact_block en el orquestador).
        try:
            from app.services.lead_service import lead_service
            lead = lead_service._get_or_create_lead(db, session_id)
            if not lead.phone:
                lead.phone = phone
                db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("WhatsApp: no se pudo pre-cargar teléfono en Lead", error=str(e))

        try:
            result = await asyncio.wait_for(
                agent_service.chat(db, body, session_id),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("WhatsApp: el agente tardó demasiado", session_id=session_id)
            whatsapp_service.send_text(
                phone,
                "Disculpá, estoy tardando más de lo normal. ¿Podés repetirme tu consulta?",
            )
            return

        _send_agent_reply(phone, result)
    except Exception as e:  # noqa: BLE001
        logger.error("WhatsApp: error procesando mensaje", error=str(e), session_id=session_id)
        whatsapp_service.send_text(
            phone, "Tuvimos un inconveniente procesando tu mensaje. Intentá de nuevo en un momento."
        )
    finally:
        db.close()


@router.get("/webhook")
async def verify_webhook():
    """Eco simple para confirmar que Twilio/uno mismo puede alcanzar la URL."""
    return PlainTextResponse("WhatsApp webhook activo")


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """Recibe un mensaje entrante de Twilio WhatsApp.

    Twilio manda form-urlencoded. Validamos la firma, respondemos 200 enseguida y
    procesamos en background (el envío de varios mensajes no debe bloquear a Twilio).
    """
    form = await request.form()
    from_field = form.get("From", "")
    body = (form.get("Body") or "").strip()
    profile_name = form.get("ProfileName", "")

    # Validación de firma: garantiza que el POST viene de Twilio.
    if settings.TWILIO_AUTH_TOKEN:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        if not validator.validate(url, dict(form), signature):
            logger.warning("WhatsApp: firma de Twilio inválida", url=url)
            return Response(status_code=403)

    if not body:
        # Mensajes sin texto (stickers, ubicaciones, etc.) — los ignoramos en la demo.
        return Response(status_code=200)

    logger.info("WhatsApp message received", from_field=from_field, length=len(body))

    # Procesar en background: respondemos 200 a Twilio ya mismo.
    asyncio.create_task(_process_and_reply(from_field, body, profile_name))
    return Response(status_code=200)
