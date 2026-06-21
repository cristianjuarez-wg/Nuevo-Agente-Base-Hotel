"""
Resolución de ROL por número de teléfono — base del agente multi-rol.

Dado un teléfono (de un mensaje de WhatsApp), determina si quien escribe es el dueño
(`owner`), un miembro del staff (`staff`) o un huésped (`guest`, default). El webhook
usa esto para rutear a un orquestador distinto según el rol.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.staff import StaffMember
from app.utils.phone_normalizer import normalize_phone, phones_match
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def resolve_role(phone: Optional[str], db: Session) -> str:
    """Devuelve "owner" | "staff" | "guest" según el teléfono.

    Busca el teléfono entre los StaffMember ACTIVOS. Primero por match exacto del
    canónico; si no aparece, hace un fallback TOLERANTE (por los últimos dígitos)
    para reconocer números cargados con formato viejo — p. ej. el dueño guardado sin
    el "9" móvil argentino, escribiendo desde WhatsApp que sí lo incluye.

    Si no está, es un huésped. Nunca lanza: ante cualquier problema, trata el número
    como huésped (flujo seguro).
    """
    try:
        norm = normalize_phone(phone) if phone else None
        if not norm:
            return "guest"

        # 1) Match exacto del canónico (caso ideal, datos bien cargados).
        member = (
            db.query(StaffMember)
            .filter(StaffMember.phone == norm, StaffMember.active == True)  # noqa: E712
            .first()
        )

        # 2) Fallback tolerante: el universo de staff es chico, comparamos en Python
        #    por clave de últimos dígitos (ignora el "9"/"0"/"15" y separadores).
        if not member:
            actives = (
                db.query(StaffMember)
                .filter(StaffMember.active == True)  # noqa: E712
                .all()
            )
            member = next((m for m in actives if phones_match(m.phone, norm)), None)

        if member and member.role in ("owner", "staff"):
            return member.role
        return "guest"
    except Exception as e:  # noqa: BLE001
        logger.warning("resolve_role falló, tratando como guest", error=str(e))
        return "guest"
