"""
Bootstrap de instancia (Fase 3.1) — aplica un instance/<cliente>.yaml a la base.

Idempotente: crea/actualiza el BusinessProfile (singleton id=1), siembra el catálogo de
habitaciones y crea el admin bootstrap si la tabla de admins está vacía. Se puede correr N
veces sin duplicar datos. Reemplaza a los seeds hardcodeados por cliente (seed_hotel.py, etc.):
el Hampton se convierte en la primera instancia de la plantilla (instance/hampton.yaml).

Uso:
    python -m instance.bootstrap_instance instance/hampton.yaml

Nota sobre precios: el esquema actual de `rooms` usa base_price_usd/base_price_ars (NOT NULL).
Hasta que exista la tabla room_prices (diferida a esta fase, ver DEUDA_TECNICA), el bootstrap
mapea el dict `prices` del YAML a esas dos columnas: usa USD si está, y la moneda primaria para
la columna _ars (que en la práctica es "el precio en la moneda local"). Cuando se agregue
room_prices, este mapeo se reemplaza por filas por moneda sin cambiar el YAML.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from app.models.database import SessionLocal
from app.services import business_profile_service
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


# Campos del bloque `business` del YAML → columnas del BusinessProfile.
_PROFILE_MAP = {
    "name": "business_name",
    "brand_line": "brand_line",
    "vertical": "vertical",
    "agent_name": "agent_display_name",
    "role_descriptor": "role_descriptor",
    "timezone": "timezone",
    "locale": "locale",
    "language": "language",
    "dialect_style": "dialect_style",
    "city": "city",
    "region_line": "region_line",
    "lat": "lat",
    "lng": "lng",
    "primary_currency": "primary_currency",
    "secondary_currency": "secondary_currency",
    "facts": "facts",
    "contact_phone": "contact_phone",
    "contact_email": "contact_email",
}


def _load_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[bootstrap] No existe el archivo: {path}")
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if "business" not in data:
        raise SystemExit(f"[bootstrap] {path} no tiene bloque 'business' (obligatorio).")
    return data


def _apply_profile(db, business: dict) -> None:
    payload = {}
    for ykey, col in _PROFILE_MAP.items():
        if ykey in business:
            payload[col] = business[ykey]
    if not payload.get("business_name"):
        raise SystemExit("[bootstrap] business.name es obligatorio.")
    profile = business_profile_service.update_profile(db, payload)
    print(f"[bootstrap] BusinessProfile → {profile['business_name']} "
          f"({profile.get('primary_currency')}/{profile.get('secondary_currency')}, "
          f"{profile.get('language')}/{profile.get('dialect_style')})")


def _room_prices(prices: dict, primary: str, secondary: str | None) -> tuple[float, float]:
    """Mapea el dict de precios por moneda del YAML a (base_price_usd, base_price_ars).

    El esquema actual solo tiene columnas _usd y _ars. Se llenan por su moneda EXACTA si el
    YAML la trae; si falta, se usa el precio de la moneda primaria como fallback (para que
    NOT NULL no rompa). Un cliente sin ARS (ej. MXN/USD) tendrá _ars = su precio primario,
    inofensivo hasta que exista room_prices (que reemplaza este mapeo por filas por moneda).
    """
    prices = prices or {}
    price_primary = float(prices.get(primary, 0) or 0)
    price_usd = float(prices.get("USD", price_primary) or price_primary)
    price_ars = float(prices.get("ARS", price_primary) or price_primary)
    return price_usd, price_ars


def _apply_rooms(db, rooms: list, primary: str, secondary: str | None) -> None:
    from app.models.hotel import Room
    if not rooms:
        print("[bootstrap] Sin rooms en el YAML (se cargarán por backoffice).")
        return
    n_new = n_upd = 0
    for r in rooms:
        rtype = r.get("room_type")
        if not rtype:
            print("[bootstrap] room sin room_type, se omite.")
            continue
        usd, ars = _room_prices(r.get("prices", {}), primary, secondary)
        row = db.query(Room).filter(Room.room_type == rtype).first()
        fields = dict(
            room_type=rtype,
            description=r.get("description", ""),
            capacity=int(r.get("capacity", 2)),
            base_price_usd=usd,
            base_price_ars=ars,
            total_units=int(r.get("total_units", 1)),
            bed_config=r.get("bed_config", ""),
            view=r.get("view", ""),
            images=r.get("images", []),
            amenities=r.get("amenities", []),
            status="active",
        )
        if row:
            for k, v in fields.items():
                setattr(row, k, v)
            n_upd += 1
        else:
            db.add(Room(**fields))
            n_new += 1
    db.commit()
    print(f"[bootstrap] Rooms: {n_new} creadas, {n_upd} actualizadas.")
    _apply_room_units(db)
    # Tarea B: poblar room_prices con TODAS las monedas del YAML (precio real por moneda).
    from app.services import room_price_service
    from app.models import room_price as _rp
    _rp.ensure_table()
    for r in rooms:
        rtype = r.get("room_type")
        prices = r.get("prices") or {}
        if not rtype or not prices:
            continue
        room = db.query(Room).filter(Room.room_type == rtype).first()
        if room:
            room_price_service.set_prices(db, room.id, prices)
    print("[bootstrap] room_prices poblado desde el YAML.")


def _numbers_for(total: int) -> list:
    """Genera N números de habitación (mismo criterio que seed_room_units): 101, 102... por piso."""
    nums = []
    for i in range(total):
        floor = 1 + (i // 20)
        idx = (i % 20) + 1
        nums.append(f"{floor}{idx:02d}")
    return nums


def _apply_room_units(db) -> None:
    """Crea las unidades físicas (RoomUnit) de cada Room desde su total_units. La disponibilidad
    las necesita: sin unidades, el agente responde 'no hay disponibilidad'. Idempotente: si un
    tipo ya tiene unidades, no las duplica. Reproduce lo que hacía seed_room_units.py."""
    from app.models.hotel import Room, RoomUnit
    created = 0
    for room in db.query(Room).all():
        existing = db.query(RoomUnit).filter(RoomUnit.room_id == room.id).count()
        if existing > 0:
            continue
        for number in _numbers_for(room.total_units or 0):
            db.add(RoomUnit(room_id=room.id, number=number, floor=int(number[0]), status="available"))
            created += 1
    db.commit()
    if created:
        print(f"[bootstrap] RoomUnits: {created} unidades creadas.")


def _apply_admin(db, admin: dict) -> None:
    """Crea el admin bootstrap SOLO si la tabla está vacía. La password llega por env var
    (BOOTSTRAP_ADMIN_PASSWORD), no por el YAML — el YAML no debe contener secretos."""
    if not admin or not admin.get("email"):
        return
    from app.core.security.auth import ensure_bootstrap_admin
    from app.config import settings
    # Si el YAML trae email pero no hay env de bootstrap, lo inyectamos para que ensure_* lo use.
    if not settings.BOOTSTRAP_ADMIN_EMAIL:
        settings.BOOTSTRAP_ADMIN_EMAIL = admin["email"]
    ensure_bootstrap_admin(db)
    print(f"[bootstrap] Admin bootstrap verificado (email {admin['email']}; "
          "password vía BOOTSTRAP_ADMIN_PASSWORD si la tabla estaba vacía).")


def bootstrap(path: str) -> None:
    data = _load_yaml(path)
    business = data["business"]
    primary = business.get("primary_currency", "USD")
    secondary = business.get("secondary_currency")
    # ORDEN DE IMPORT CRÍTICO: hotel.py hace un create_all a nivel de módulo de sus tablas
    # (Booking, HotelTicket...), cuyas FKs apuntan a contacts, staff_members y room_units. Esas
    # tablas deben existir en el metadata ANTES de importar hotel, o ese create_all revienta con
    # NoReferencedTableError. Por eso importamos primero los modelos referenciados.
    from app.models import contact, staff, restaurant  # noqa: F401  (contacts, staff_members, room_units)
    # Luego el resto, con el barrido completo (idempotente: reimportar es no-op).
    import importlib, pkgutil
    import app.models as models_pkg
    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    # Asegurar el esquema (idempotente): en producción las tablas ya existen (alembic upgrade
    # head las creó); en una DB nueva/efímera esto las crea, así el bootstrap corre solo.
    from app.models.database import Base, engine, run_light_migrations
    Base.metadata.create_all(bind=engine)
    run_light_migrations()
    db = SessionLocal()
    try:
        _apply_profile(db, business)
        _apply_rooms(db, data.get("rooms", []), primary, secondary)
        _apply_admin(db, data.get("admin", {}))
        print(f"[bootstrap] OK — instancia '{business.get('name')}' aplicada desde {path}.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m instance.bootstrap_instance instance/<cliente>.yaml")
    bootstrap(sys.argv[1])
