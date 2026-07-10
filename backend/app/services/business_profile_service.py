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
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

# Valores de fábrica (Hampton) — el fallback si la DB no está lista. Coinciden con los
# defaults de las columnas del modelo, así el arranque tiene identidad antes del seed.
# Hechos duros del Hampton — antes estaban hardcodeados en los prompts ("no spa ni sauna", etc.).
# Fase A: se movieron al perfil (facts) para que sean parametrizables por cliente. El Hampton los
# recibe por seed / migración; el agente los respeta vía build_facts_block.
_HAMPTON_FACTS = (
    "No tiene spa ni sauna",
    "Desayuno buffet incluido en todas las tarifas",
    "El estacionamiento es con cargo (salvo promo Stay & Park)",
)

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


def get_contact(db: Session) -> dict:
    """Tel/email de contacto del negocio para los fallbacks del agente ("contactanos al ...").

    Devuelve {"phone": ..., "email": ...} desde el perfil. Fase 3.5.

    Fallback SOLO para el Hampton (business_name histórico): así se preserva el comportamiento
    histórico sin filtrarle a OTRO cliente el teléfono/email del Hampton (bug de la prueba de
    fuego: una instancia nueva mostraba el contacto del Hampton). Un cliente que no cargó su
    contacto obtiene strings vacíos y el agente omite la línea de contacto.
    """
    prof = get_profile(db)
    phone = prof.get("contact_phone")
    email = prof.get("contact_email")
    es_hampton = (prof.get("business_name") or "").startswith("Hampton by Hilton")
    if not phone and es_hampton:
        phone = "+54 294-474-6200"
    if not email and es_hampton:
        email = "info@hamptonbariloche.com"
    return {"phone": phone or "", "email": email or ""}


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
            facts=list(_HAMPTON_FACTS),
            contact_phone="+54 294-474-6200",
            contact_email="info@hamptonbariloche.com",
        )
        db.add(row)
        db.commit()
        invalidate_cache()
        logger.info("BusinessProfile sembrado con los valores del Hampton (id=1)")
    except Exception as e:  # noqa: BLE001 — el seed nunca debe tumbar el arranque
        logger.warning("No se pudo sembrar el BusinessProfile", error=str(e))
        db.rollback()


def ensure_hampton_facts(db: Session) -> None:
    """Migración idempotente (Fase A): rellena los facts del Hampton si su perfil ya existía
    con facts=[]. Necesario porque los hechos ('no spa ni sauna', etc.) se movieron del texto
    hardcodeado de los prompts a los facts del perfil; sin esto, un Hampton ya seedeado los
    perdería. Solo aplica si el negocio ES el Hampton y no tiene facts cargados por el cliente.
    """
    try:
        row = db.query(BusinessProfile).filter(BusinessProfile.id == 1).first()
        if not row:
            return
        es_hampton = (row.business_name or "").startswith("Hampton by Hilton")
        if es_hampton and not (row.facts or []):
            row.facts = list(_HAMPTON_FACTS)
            db.commit()
            invalidate_cache()
            logger.info("Facts del Hampton rellenados en el perfil existente")
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudieron rellenar los facts del Hampton", error=str(e))
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
        "contact_phone", "contact_email",
    }
    for key, value in (data or {}).items():
        if key in editable:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    invalidate_cache()
    return row.to_dict()
