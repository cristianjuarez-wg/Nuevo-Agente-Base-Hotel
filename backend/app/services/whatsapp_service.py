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

    def send_typing_indicator(self, message_sid: str) -> bool:
        """Muestra "escribiendo…" al huésped y marca su mensaje como LEÍDO (tilde azul).

        Una sola llamada al recurso Typing Indicators de Twilio cubre ambas señales: el
        indicador de escritura y el read-receipt del mensaje entrante referenciado. Dura
        hasta 25 s o hasta que enviemos la respuesta real. Best-effort: cualquier fallo se
        loguea y se ignora — NUNCA debe bloquear ni cortar la respuesta del agente.

        El SDK de Twilio aún no expone este recurso V3, así que lo llamamos por REST.
        """
        if not message_sid or not self.is_configured:
            return False
        try:
            import httpx
            resp = httpx.post(
                "https://messaging.twilio.com/v3/Indicators/Typing.json",
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                json={"channel": "whatsapp", "messageId": message_sid},
                timeout=5.0,
            )
            if resp.status_code >= 400:
                logger.warning("Typing indicator: Twilio respondió error",
                               status=resp.status_code, body=resp.text[:200])
                return False
            return True
        except Exception as e:  # noqa: BLE001 — best-effort, no debe afectar el flujo
            logger.warning("No se pudo enviar el typing indicator", error=str(e))
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
