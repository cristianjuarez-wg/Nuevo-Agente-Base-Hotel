"""
Acceso cacheado al BusinessProfile (Fase 1) — la identidad del negocio.

Fila única id=1. Se cachea en memoria (se lee en CADA turno para componer prompts) y se
invalida explícitamente al guardar desde el endpoint PUT. Fail-open: si la DB no está
lista (arranque) o falla, devuelve un perfil por defecto con los valores del Hampton, para
que el sistema nunca quede sin identidad.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.business_profile import BusinessProfile
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Valores de fábrica (Hampton) — el fallback si la DB no está lista. Coinciden con los
# defaults de las columnas del modelo, así el arranque tiene identidad antes del seed.
_FACTORY_DEFAULTS = {
    "id": 1,
    "business_name": "Hampton by Hilton Bariloche",
    "brand_line": "el primer Hilton de la Patagonia",
    "vertical": "hotel",
    "agent_display_name": "Aura",
    "role_descriptor": "concierge",
    "timezone": "America/Argentina/Buenos_Aires",
    "locale": "es_AR",
    "language": "es",
    "dialect_style": "rioplatense_voseo",
    "city": "Bariloche",
    "region_line": None,
    "lat": None,
    "lng": None,
    "primary_currency": "USD",
    "secondary_currency": "ARS",
    "facts": [],
    "updated_at": None,
}

# Caché del dict del perfil (no la instancia ORM, para no atarlo a una sesión cerrada).
_cache: Optional[dict] = None


def get_profile(db: Session) -> dict:
    """Devuelve el perfil del negocio como dict (cacheado). Fail-open a los defaults."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        row = db.query(BusinessProfile).filter(BusinessProfile.id == 1).first()
        _cache = row.to_dict() if row else dict(_FACTORY_DEFAULTS)
    except Exception as e:  # noqa: BLE001 — nunca dejar al sistema sin identidad
        logger.warning("BusinessProfile no disponible, usando defaults de fábrica", error=str(e))
        return dict(_FACTORY_DEFAULTS)
    return _cache


def invalidate_cache() -> None:
    """Descarta el perfil cacheado (llamar tras un PUT que lo modifica)."""
    global _cache
    _cache = None
    # El timezone del negocio puede haber cambiado → invalidar también su caché.
    try:
        from app.utils.timezone_utils import invalidate_tz_cache
        invalidate_tz_cache()
    except Exception:  # noqa: BLE001
        pass


def ensure_seeded(db: Session) -> None:
    """Crea la fila id=1 con los valores del Hampton si no existe (idempotente).

    Paridad: con estos valores de fábrica, el agente se comporta igual que antes de la
    Fase 1. No pisa un perfil ya editado por el cliente.
    """
    try:
        existing = db.query(BusinessProfile).filter(BusinessProfile.id == 1).first()
        if existing:
            return
        row = BusinessProfile(
            id=1,
            business_name="Hampton by Hilton Bariloche",
            brand_line="el primer Hilton de la Patagonia",
            vertical="hotel",
            agent_display_name="Aura",
            role_descriptor="concierge",
            timezone="America/Argentina/Buenos_Aires",
            locale="es_AR",
            language="es",
            dialect_style="rioplatense_voseo",
            city="Bariloche",
            region_line=None,
            primary_currency="USD",
            secondary_currency="ARS",
            facts=[],
        )
        db.add(row)
        db.commit()
        invalidate_cache()
        logger.info("BusinessProfile sembrado con los valores del Hampton (id=1)")
    except Exception as e:  # noqa: BLE001 — el seed nunca debe tumbar el arranque
        logger.warning("No se pudo sembrar el BusinessProfile", error=str(e))
        db.rollback()


def update_profile(db: Session, data: dict) -> dict:
    """Actualiza los campos editables del perfil (id=1) e invalida el caché."""
    row = db.query(BusinessProfile).filter(BusinessProfile.id == 1).first()
    if not row:
        row = BusinessProfile(id=1)
        db.add(row)
    editable = {
        "business_name", "brand_line", "vertical", "agent_display_name", "role_descriptor",
        "timezone", "locale", "language", "dialect_style", "city", "region_line",
        "lat", "lng", "primary_currency", "secondary_currency", "facts",
    }
    for key, value in (data or {}).items():
        if key in editable:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    invalidate_cache()
    return row.to_dict()
