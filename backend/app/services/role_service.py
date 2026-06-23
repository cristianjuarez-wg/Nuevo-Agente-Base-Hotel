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


def find_staff_member(phone: Optional[str], db: Session) -> Optional[StaffMember]:
    """Busca el StaffMember ACTIVO de un teléfono. Primero por match exacto del
    canónico; si no aparece, fallback TOLERANTE (últimos dígitos, ignora "9"/"0"/"15"
    y separadores) para números cargados con formato viejo.

    Única fuente de verdad del matching de staff: la usan resolve_role Y el ruteo
    (_route_staff/_route_owner), para que NO puedan divergir (antes el ruteo re-buscaba
    con match exacto y rechazaba a quien resolve_role había aceptado por el tolerante).
    """
    norm = normalize_phone(phone) if phone else None
    if not norm:
        return None
    # 1) Match exacto del canónico (caso ideal, datos bien cargados).
    member = (
        db.query(StaffMember)
        .filter(StaffMember.phone == norm, StaffMember.active == True)  # noqa: E712
        .first()
    )
    # 2) Fallback tolerante (el universo de staff es chico → comparamos en Python).
    if not member:
        actives = (
            db.query(StaffMember)
            .filter(StaffMember.active == True)  # noqa: E712
            .all()
        )
        member = next((m for m in actives if phones_match(m.phone, norm)), None)
    return member


def resolve_role(phone: Optional[str], db: Session) -> str:
    """Devuelve "owner" | "staff" | "guest" según el teléfono.

    Si no está entre el staff activo, es un huésped. Nunca lanza: ante cualquier
    problema, trata el número como huésped (flujo seguro).
    """
    try:
        member = find_staff_member(phone, db)
        if member and member.role in ("owner", "staff"):
            return member.role
        return "guest"
    except Exception as e:  # noqa: BLE001
        logger.warning("resolve_role falló, tratando como guest", error=str(e))
        return "guest"
