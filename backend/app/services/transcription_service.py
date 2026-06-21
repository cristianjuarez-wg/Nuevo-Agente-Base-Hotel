"""
Transcripción de notas de voz de WhatsApp (Twilio) a texto.

Cuando un huésped manda un audio en lugar de escribir, Twilio nos pasa la URL del
archivo (MediaUrl0). Acá lo descargamos —las URLs de media de Twilio son privadas y
requieren autenticación con las credenciales de la cuenta— y lo transcribimos con
Whisper de OpenAI. El texto resultante se trata igual que un mensaje escrito: el
resto del pipeline del agente no cambia.

Usamos OpenAI (mismo OPENAI_API_KEY que el resto del agente), así no sumamos un
proveedor nuevo. Costo de Whisper: ~USD 0,006/minuto, despreciable para la demo.
"""
import io

import httpx

from app.config import settings
from app.core.openai_client import get_async_openai
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Cap de duración por tamaño de archivo: las notas de voz reales de una consulta son
# cortas. WhatsApp usa OGG/Opus (~1 KB/s), así ~3 min ≈ 250 KB; ponemos un techo
# holgado de 5 MB para cortar audios anómalos sin gastar de más ni arriesgar timeouts.
_MAX_AUDIO_BYTES = 5 * 1024 * 1024

# Extensión por content-type, para que Whisper reconozca el formato del archivo.
_EXT_BY_CONTENT_TYPE = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/webm": "webm",
    "audio/amr": "amr",
}


async def _download_twilio_media(media_url: str) -> bytes | None:
    """Descarga el archivo de media desde Twilio con autenticación de la cuenta.

    Las MediaUrl de Twilio son privadas: requieren Basic Auth con el Account SID y el
    Auth Token. Devuelve los bytes, o None si falla o el archivo es demasiado grande.
    """
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
        logger.warning("Transcripción: faltan credenciales de Twilio para bajar el audio")
        return None

    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(media_url, auth=auth)
            resp.raise_for_status()
            data = resp.content
            if len(data) > _MAX_AUDIO_BYTES:
                logger.warning("Transcripción: audio demasiado grande", size=len(data))
                return None
            return data
    except Exception as e:  # noqa: BLE001 — un fallo de descarga no debe tumbar el webhook
        logger.error("Transcripción: error descargando audio de Twilio", error=str(e))
        return None


async def transcribe_whatsapp_audio(media_url: str, content_type: str | None) -> str | None:
    """Descarga y transcribe una nota de voz de WhatsApp. Devuelve el texto o None.

    None indica que no se pudo transcribir (descarga fallida, formato no soportado o
    error de Whisper); el caller debe avisarle al usuario que reintente o escriba.
    """
    audio = await _download_twilio_media(media_url)
    if not audio:
        return None

    ext = _EXT_BY_CONTENT_TYPE.get((content_type or "").split(";")[0].strip().lower(), "ogg")
    buffer = io.BytesIO(audio)
    buffer.name = f"voice.{ext}"  # Whisper infiere el formato por la extensión del nombre.

    try:
        client = get_async_openai()
        result = await client.audio.transcriptions.create(
            model="whisper-1",
            file=buffer,
        )
        text = (result.text or "").strip()
        if not text:
            logger.info("Transcripción: Whisper devolvió texto vacío")
            return None
        logger.info("Transcripción OK", length=len(text))
        return text
    except Exception as e:  # noqa: BLE001
        logger.error("Transcripción: error en Whisper", error=str(e))
        return None
