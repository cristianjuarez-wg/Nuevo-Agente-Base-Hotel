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


def _send_agent_reply(to_phone: str, result: dict) -> bool:
    """Envía al usuario la respuesta del agente: texto + fotos de habitaciones.

    Devuelve True si el texto principal fue aceptado por Twilio — es lo que define si el
    huésped recibió la respuesta de Aura. Las fotos son complementarias: su fallo ya se
    loguea dentro de whatsapp_service.send_media y NO marca el turno como fallido.
    """
    # 1) Texto principal del agente.
    sent = True
    body = to_whatsapp_text(result.get("response", ""))
    if body:
        sent = whatsapp_service.send_text(to_phone, body)

    # 2) Habitaciones ofrecidas este turno -> una foto + caption por habitación.
    rooms = result.get("rooms_offered") or []
    for room in rooms[: settings.WHATSAPP_MAX_ROOM_CARDS]:
        images = room.get("images") or []
        image = images[0] if images else _FALLBACK_IMG
        caption = _room_caption(room)
        whatsapp_service.send_media(to_phone, caption, image)

    return sent


def _save_checkin_document(media_url: str, content_type: str | None,
                           session_id: str, db: Session) -> str | None:
    """Descarga la imagen del documento (Twilio media) y la guarda en MEDIA_DIR/checkin/.

    Devuelve la ruta pública ("/media/checkin/<code>.<ext>") o None si falló. Twilio exige
    autenticación básica (Account SID + Auth Token) para bajar el media.
    """
    import os
    import requests
    from app.models.hotel import Booking

    try:
        # Buscar el código de la reserva en flujo para nombrar el archivo.
        from app.services import checkin_express_service as checkin
        b = checkin._get_booking_by_session(db, session_id)
        code = b.code if b else session_id.replace("wa_", "")

        ext = "jpg"
        if content_type and "/" in content_type:
            ext = content_type.split("/")[-1].split(";")[0] or "jpg"
            ext = {"jpeg": "jpg"}.get(ext, ext)

        auth = None
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        resp = requests.get(media_url, auth=auth, timeout=20)
        if resp.status_code != 200 or not resp.content:
            logger.error("Check-in: no se pudo descargar el documento de Twilio",
                         status=resp.status_code, session_id=session_id)
            return None

        checkin_dir = os.path.join(settings.MEDIA_DIR, "checkin")
        os.makedirs(checkin_dir, exist_ok=True)
        filename = f"{code}.{ext}"
        with open(os.path.join(checkin_dir, filename), "wb") as f:
            f.write(resp.content)
        return f"/media/checkin/{filename}"
    except Exception as e:  # noqa: BLE001
        logger.error("Check-in: error guardando el documento", error=str(e), session_id=session_id)
        return None


async def _process_and_reply(
    from_field: str,
    body: str,
    profile_name: str,
    audio_url: str | None = None,
    audio_type: str | None = None,
    message_sid: str | None = None,
    image_url: str | None = None,
    image_type: str | None = None,
) -> None:
    """Procesa el mensaje con el agente y responde por WhatsApp. Corre en background.

    Usa su propia sesión de DB porque la del request ya se cerró cuando esto ejecuta.
    Si llegó una nota de voz (audio_url), primero la transcribimos con Whisper y el
    texto resultante se trata exactamente igual que un mensaje escrito.
    """
    from app.models.database import SessionLocal

    # Teléfono: viene como "whatsapp:+549..." -> nos quedamos con "+549...".
    raw_phone = from_field.replace("whatsapp:", "").strip()
    phone = normalize_phone(raw_phone)
    if not phone:
        logger.warning("WhatsApp: teléfono inválido", from_field=from_field)
        return

    # Feedback inmediato al huésped: "escribiendo…" + marca su mensaje como leído (tilde
    # azul). Best-effort, antes de invocar al agente. Cubre también audios (mientras
    # Whisper + agente trabajan, el huésped ve que estamos con eso).
    whatsapp_service.send_typing_indicator(message_sid)

    session_id = "wa_" + phone.lstrip("+")

    # Nota de voz → texto. Si falla la transcripción, avisamos y cortamos.
    transcribed = False
    if audio_url:
        from app.services.transcription_service import transcribe_whatsapp_audio
        text = await transcribe_whatsapp_audio(audio_url, audio_type)
        if not text:
            whatsapp_service.send_text(
                phone,
                "No pude entender el audio 🙇 ¿Podés escribir tu consulta o intentar de nuevo?",
            )
            return
        body = text
        transcribed = True

    db = SessionLocal()
    try:
        # Resolver el ROL del remitente (huésped / staff / dueño). Define qué agente atiende.
        from app.services.role_service import resolve_role
        role = resolve_role(phone, db)

        # El preprocesamiento de huésped (crear Contact, pre-cargar Lead) SOLO aplica a
        # huéspedes — el dueño/staff no son leads ni contactos comerciales.
        if role == "guest":
            try:
                _contact_service.get_or_create_contact(phone=phone, name=profile_name or None, db=db)
            except Exception as e:  # noqa: BLE001 — no bloquear la respuesta por esto
                logger.warning("WhatsApp: no se pudo crear/vincular Contact", error=str(e))
            try:
                from app.services.lead_service import lead_service
                lead = lead_service._get_or_create_lead(db, session_id)
                if not lead.phone:
                    lead.phone = phone
                    db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("WhatsApp: no se pudo pre-cargar teléfono en Lead", error=str(e))

        # 🆕 GATE DE TOMA DE CONTROL HUMANA: si un humano tomó esta conversación, Aura NO
        # responde. Guardamos el mensaje entrante (para que el humano lo vea en la bandeja) y
        # cortamos sin invocar al agente. Solo aplica a huéspedes (staff/owner no se "toman").
        if role == "guest":
            from app.services import conversation_control_service as conv_ctrl
            if conv_ctrl.is_human_controlled(db, session_id):
                try:
                    agent_service._save_message_to_db(
                        db=db, session_id=session_id, role="user",
                        content=body, context_type="pre_sale",
                    )
                except Exception as e:  # noqa: BLE001 — no romper por el guardado
                    logger.warning("WhatsApp: no se pudo guardar mensaje en takeover",
                                   session_id=session_id, error=str(e))
                logger.info("WhatsApp: conversación bajo control humano, Aura no responde",
                            session_id=session_id)
                return  # el humano responderá desde el backoffice

        # 🆕 GATE CHECK-IN EXPRESS (determinístico, FUERA del LLM). Si esta sesión tiene un
        # check-in en curso, el flujo lo maneja checkin_express_service — el agente NO se invoca.
        if role == "guest":
            from app.services import checkin_express_service as checkin
            # (a) Llegó una IMAGEN y estábamos esperando el documento → guardarla y cerrar.
            if image_url and checkin.awaiting_document(db, session_id):
                doc_url = _save_checkin_document(image_url, image_type, session_id, db)
                reply = checkin.save_document(db, session_id, doc_url) if doc_url else (
                    "No pude guardar la imagen 🙇. ¿Podés reenviarla? O escribí *OMITIR* "
                    "para mostrar el documento al llegar.")
                whatsapp_service.send_text(phone, to_whatsapp_text(reply))
                return
            # (b) Texto dentro del flujo → procesar el paso (sin LLM).
            if body and checkin.is_in_flow(db, session_id):
                reply = checkin.handle_text_step(db, session_id, body)
                whatsapp_service.send_text(phone, to_whatsapp_text(reply))
                return

        # Imagen fuera del flujo de check-in: no la maneja el agente; avisamos amablemente.
        if image_url and not body:
            whatsapp_service.send_text(
                phone, "Recibí tu imagen 📷, pero no la esperaba ahora. ¿En qué te ayudo?")
            return

        # Despachar al agente correcto según el rol (punto único de ruteo).
        from app.services.agent_router import route_whatsapp
        try:
            result = await asyncio.wait_for(
                route_whatsapp(db, phone, body),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("WhatsApp: el agente tardó demasiado", session_id=session_id, role=role)
            whatsapp_service.send_text(
                phone,
                "Disculpá, estoy tardando más de lo normal. ¿Podés repetirme tu consulta?",
            )
            return

        # Si el mensaje vino por audio, confirmamos qué entendió Aura. Así el huésped
        # ve la transcripción y puede corregir si Whisper se equivocó.
        if transcribed:
            confirm = f"🎙️ Entendí: «{body}»\n\n"
            result["response"] = confirm + (result.get("response") or "")

        # Gerencia puede devolver un gráfico (chart_url) → se envía como media.
        chart_url = result.get("chart_url")
        # Para owner/staff garantizamos que NUNCA se envíe vacío (Twilio rechaza el envío y
        # el usuario queda en silencio): si el agente no produjo texto, mandamos un aviso.
        reply_text = (result.get("response") or "").strip()
        if role in ("owner", "staff") and not reply_text:
            reply_text = "Disculpá, no pude generar la respuesta. ¿Me repetís la consulta?"

        if chart_url:
            ok = whatsapp_service.send_media(phone, reply_text, chart_url)
        elif role in ("owner", "staff"):
            ok = whatsapp_service.send_text(phone, reply_text)
        else:
            ok = _send_agent_reply(phone, result)
        # Observabilidad: si el envío falló (Twilio lo rechazó), que quede en los logs con
        # el contexto del turno — es el punto ciego que dejaba al owner sin respuesta.
        if ok is False:
            logger.error("WhatsApp: no se pudo enviar la respuesta al usuario",
                         session_id=session_id, role=role, is_audio=transcribed,
                         had_chart=bool(chart_url))
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
    message_sid = form.get("MessageSid", "")  # para el typing indicator / read-receipt

    # Validación de firma: garantiza que el POST viene de Twilio.
    if settings.TWILIO_AUTH_TOKEN:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        if not validator.validate(url, dict(form), signature):
            logger.warning("WhatsApp: firma de Twilio inválida", url=url)
            return Response(status_code=403)

    # Media entrante: Twilio la manda sin Body de texto. Distinguimos:
    #  - audio → nota de voz (la transcribe el background task antes del agente).
    #  - imagen → puede ser el documento del check-in express (lo maneja un gate aparte).
    audio_url = None
    audio_type = None
    image_url = None
    image_type = None
    num_media = int(form.get("NumMedia", "0") or "0")
    if not body and num_media > 0:
        content_type = (form.get("MediaContentType0") or "").lower()
        if content_type.startswith("audio"):
            audio_url = form.get("MediaUrl0")
            audio_type = content_type
        elif content_type.startswith("image"):
            image_url = form.get("MediaUrl0")
            image_type = content_type

    if not body and not audio_url and not image_url:
        # Sin texto ni audio ni imagen (stickers, ubicaciones, etc.) — los ignoramos.
        return Response(status_code=200)

    logger.info(
        "WhatsApp message received",
        from_field=from_field,
        length=len(body),
        is_audio=bool(audio_url),
        is_image=bool(image_url),
    )

    # Procesar en background: respondemos 200 a Twilio ya mismo.
    task = asyncio.create_task(
        _process_and_reply(from_field, body, profile_name, audio_url, audio_type,
                           message_sid, image_url, image_type)
    )
    # Si la task lanza una excepción FUERA del try interno (ej. en la transcripción, que
    # corre antes), sin callback se perdería en silencio ("Task exception was never
    # retrieved"). El callback la loguea para que el fallo sea visible en Render.
    def _log_task_exc(t: asyncio.Task) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.error("WhatsApp: el procesamiento en background falló sin recuperarse",
                         error=str(exc), from_field=from_field, is_audio=bool(audio_url))
    task.add_done_callback(_log_task_exc)
    return Response(status_code=200)
