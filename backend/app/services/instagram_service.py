"""
Cliente de Instagram Messaging (Meta Graph API) — espejo de whatsapp_service para el canal IG.

Envía mensajes salientes (DMs) hacia el Instagram del usuario vía la Messaging API de Meta.
La recepción la maneja el webhook en routers/instagram.py.

Funciona con la app de Meta en MODO DESARROLLO (hasta 25 testers invitados, sin App Review):
el equivalente al sandbox de Twilio. Ver INSTAGRAM_SETUP.md para el paso a paso de las cuentas.

Sin credenciales configuradas el canal queda simplemente inactivo (el backend arranca igual
en local), mismo diseño que whatsapp_service.
"""
from typing import Optional

import httpx

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Versión de la Graph API de Meta. Se actualiza acá si Meta la deprecia.
GRAPH_API_BASE = "https://graph.instagram.com/v21.0"


class InstagramService:
    """Envía DMs de Instagram vía la Messaging API de Meta (Graph API)."""

    @property
    def is_configured(self) -> bool:
        """True si hay credenciales para operar el canal."""
        return bool(settings.INSTAGRAM_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID)

    def send_text(self, igsid: str, body: str) -> bool:
        """Envía un DM de texto al usuario (por su IGSID). Devuelve True si Meta lo aceptó.

        Best-effort: un fallo de envío se loguea y devuelve False, nunca rompe el webhook
        (mismo contrato que whatsapp_service.send_text).
        """
        if not self.is_configured:
            logger.warning("Instagram no configurado: se omite send_text")
            return False
        try:
            resp = httpx.post(
                f"{GRAPH_API_BASE}/{settings.INSTAGRAM_ACCOUNT_ID}/messages",
                headers={"Authorization": f"Bearer {settings.INSTAGRAM_ACCESS_TOKEN}"},
                json={
                    "recipient": {"id": igsid},
                    "message": {"text": body},
                },
                timeout=15.0,
            )
            if resp.status_code >= 400:
                logger.error("Instagram: Meta rechazó el envío",
                             status=resp.status_code, body=resp.text[:300], igsid=igsid)
                return False
            return True
        except Exception as e:  # noqa: BLE001 — un fallo de envío no debe tumbar el webhook
            logger.error("Error enviando DM por Instagram", error=str(e), igsid=igsid)
            return False

    def get_username(self, igsid: str) -> Optional[str]:
        """Devuelve el @username del usuario (por IGSID), o None. Best-effort: se usa para
        mostrar la identidad en el backoffice; un fallo no afecta el flujo."""
        if not self.is_configured:
            return None
        try:
            resp = httpx.get(
                f"{GRAPH_API_BASE}/{igsid}",
                params={"fields": "username"},
                headers={"Authorization": f"Bearer {settings.INSTAGRAM_ACCESS_TOKEN}"},
                timeout=10.0,
            )
            if resp.status_code >= 400:
                return None
            return (resp.json() or {}).get("username")
        except Exception:  # noqa: BLE001
            return None


instagram_service = InstagramService()
