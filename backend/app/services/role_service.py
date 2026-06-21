"""
Resolución de ROL por número de teléfono — base del agente multi-rol.

Dado un teléfono (de un mensaje de WhatsApp), determina si quien escribe es el dueño
(`owner`), un miembro del staff (`staff`) o un huésped (`guest`, default). El webhook
usa esto para rutear a un orquestador distinto según el rol.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.staff import StaffMember
from app.utils.phone_normalizer import normalize_phone
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def resolve_role(phone: Optional[str], db: Session) -> str:
    """Devuelve "owner" | "staff" | "guest" según el teléfono (normalizado).

    Busca el teléfono entre los StaffMember ACTIVOS. Si no está, es un huésped.
    Nunca lanza: ante cualquier problema, trata el número como huésped (flujo seguro).
    """
    try:
        norm = normalize_phone(phone) if phone else None
        if not norm:
            return "guest"
        member = (
            db.query(StaffMember)
            .filter(StaffMember.phone == norm, StaffMember.active == True)  # noqa: E712
            .first()
        )
        if member and member.role in ("owner", "staff"):
            return member.role
        return "guest"
    except Exception as e:  # noqa: BLE001
        logger.warning("resolve_role falló, tratando como guest", error=str(e))
        return "guest"
