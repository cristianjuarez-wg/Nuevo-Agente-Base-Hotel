"""
Cliente de WhatsApp sobre Twilio (sandbox para la demo).

Encapsula el SDK de Twilio para ENVIAR mensajes salientes (texto y media) hacia el
WhatsApp del usuario. La recepción la maneja el webhook en routers/whatsapp.py.

El cliente se construye perezosamente y solo si hay credenciales: así el backend
arranca igual en local sin Twilio configurado (el canal queda simplemente inactivo).
"""
from typing import Optional

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class WhatsAppService:
    """Envía mensajes de WhatsApp vía la API REST de Twilio."""

    def __init__(self) -> None:
        self._client = None  # se inicializa en el primer uso

    @property
    def is_configured(self) -> bool:
        """True si hay credenciales para operar el canal."""
        return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)

    def _get_client(self):
        """Devuelve el Client de Twilio, creándolo una sola vez. None si no hay credenciales."""
        if not self.is_configured:
            return None
        if self._client is None:
            from twilio.rest import Client  # import diferido: evita exigir twilio en local
            self._client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        return self._client

    def _ensure_whatsapp_prefix(self, to: str) -> str:
        """Twilio exige el prefijo 'whatsapp:' en los números de este canal."""
        return to if to.startswith("whatsapp:") else f"whatsapp:{to}"

    def send_text(self, to: str, body: str) -> bool:
        """Envía un mensaje de texto. Devuelve True si Twilio lo aceptó."""
        client = self._get_client()
        if client is None:
            logger.warning("WhatsApp no configurado: se omite send_text")
            return False
        try:
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=self._ensure_whatsapp_prefix(to),
                body=body,
            )
            return True
        except Exception as e:  # noqa: BLE001 — un fallo de envío no debe tumbar el webhook
            logger.error("Error enviando texto por WhatsApp", error=str(e), to=to)
            return False

    def send_media(self, to: str, body: str, media_url: str) -> bool:
        """Envía un mensaje con una imagen (media_url debe ser una URL pública). True si OK."""
        client = self._get_client()
        if client is None:
            logger.warning("WhatsApp no configurado: se omite send_media")
            return False
        try:
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=self._ensure_whatsapp_prefix(to),
                body=body,
                media_url=[media_url],
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Error enviando media por WhatsApp", error=str(e), to=to, media_url=media_url)
            # Fallback: al menos mandamos el texto, así el usuario no se queda sin la info.
            return self.send_text(to, body)


whatsapp_service = WhatsAppService()
