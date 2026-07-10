"""
Servicio de precios por moneda (Tarea B — multimoneda).

Encapsula:
- `backfill_from_legacy(db)`: migración idempotente que puebla room_prices desde las columnas
  legacy base_price_usd/base_price_ars (para que el Hampton y cualquier dato existente tengan
  sus filas por moneda sin re-cargar nada).
- `set_prices(db, room_id, prices)`: upsert de precios por moneda (lo usan seeds/bootstrap).
- `price_in(db, room, currency)`: resuelve el precio de una habitación en la moneda pedida con
  la regla fila-explícita → conversión → primario-sin-convertir.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.room_price import RoomPrice
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


def set_prices(db: Session, room_id: int, prices: dict) -> None:
    """Upsert de precios por moneda para una habitación. `prices` = {"USD": 130, "BRL": 650}."""
    for ccy, amount in (prices or {}).items():
        if amount is None:
            continue
        ccy = (ccy or "").upper().strip()
        if not ccy:
            continue
        row = db.query(RoomPrice).filter(
            RoomPrice.room_id == room_id, RoomPrice.currency == ccy).first()
        if row:
            row.amount = float(amount)
        else:
            db.add(RoomPrice(room_id=room_id, currency=ccy, amount=float(amount)))
    db.commit()


def backfill_from_legacy(db: Session) -> None:
    """Puebla room_prices desde base_price_usd/base_price_ars si faltan (idempotente).

    Solo agrega filas que no existan: no pisa un precio por moneda ya cargado por el cliente.
    """
    try:
        from app.models.hotel import Room
        created = 0
        for room in db.query(Room).all():
            existing = {r.currency for r in db.query(RoomPrice).filter(
                RoomPrice.room_id == room.id).all()}
            to_add = {}
            if "USD" not in existing and room.base_price_usd is not None:
                to_add["USD"] = room.base_price_usd
            if "ARS" not in existing and room.base_price_ars is not None:
                to_add["ARS"] = room.base_price_ars
            if to_add:
                set_prices(db, room.id, to_add)
                created += len(to_add)
        if created:
            logger.info("room_prices backfill desde columnas legacy", filas=created)
    except Exception as e:  # noqa: BLE001 — nunca tumbar el arranque
        logger.warning("No se pudo hacer backfill de room_prices", error=str(e))
        db.rollback()


def _explicit_price(db: Session, room_id: int, currency: str) -> Optional[float]:
    row = db.query(RoomPrice).filter(
        RoomPrice.room_id == room_id, RoomPrice.currency == (currency or "").upper()).first()
    return row.amount if row else None


def price_in(db: Session, room, currency: str) -> Optional[float]:
    """Precio por noche de una habitación en `currency`. Regla:
    1. fila explícita en room_prices → gana;
    2. conversión desde otra moneda con cotización disponible (hoy solo USD↔ARS);
    3. si no se puede convertir, el precio en USD guardado (fallback conservador, no inventa).

    `room` puede ser un modelo Room o un dict con room_id/base_price_usd/base_price_ars.
    """
    ccy = (currency or "USD").upper()
    room_id = getattr(room, "id", None) or (room.get("room_id") if isinstance(room, dict) else None) \
        or (room.get("id") if isinstance(room, dict) else None)
    base_usd = getattr(room, "base_price_usd", None) if not isinstance(room, dict) \
        else room.get("base_price_usd")

    # 1. fila explícita
    if room_id is not None:
        explicit = _explicit_price(db, room_id, ccy)
        if explicit is not None:
            return explicit

    # 2. conversión desde USD si hay cotización del par (hoy exchange_rate_service cubre USD→ARS)
    if base_usd is not None:
        try:
            from app.services import exchange_rate_service
            converted = exchange_rate_service.convert(base_usd, "USD", ccy, db)
            if converted is not None:
                return converted
        except Exception:  # noqa: BLE001
            pass

    # 3. fallback: el precio en USD tal cual (no inventa una conversión que no existe)
    return base_usd
