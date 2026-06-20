"""
Seed de UNIDADES físicas de habitación (Fase 2) + backfill de reservas activas.

Genera las habitaciones numeradas de cada tipo según un esquema por piso, a partir de
`total_units`. Idempotente: si un tipo ya tiene unidades, no las duplica.

Esquema de numeración (por piso según tipo, realista para un hotel):
  - Doble Twin Accesible → planta baja: 001, 002…
  - King               → pisos 1-2:    101, 102… (20 → 110 por piso aprox.)
  - Twin               → pisos 2-3:    201, 202…
  - Family Plan        → piso 4:       401, 402…

Tras crear las unidades, asigna una unidad libre a las reservas NO canceladas con
check_out >= hoy (activas/futuras) que aún no tienen unidad, para dejar la demo
consistente. Las reservas pasadas quedan sin unidad (no importa operativamente).

Ejecutar:  python seed_room_units.py
"""
from datetime import date

from app.models.database import SessionLocal
from app.models.hotel import Room, RoomUnit, Booking

# Piso base por tipo. Se reparten correlativos por piso (máx 20 por piso).
_FLOOR_BY_TYPE = {
    "Doble Twin Accesible": 0,   # planta baja → 001, 002
    "King": 1,                   # 101…, sigue en 2xx si supera 20
    "Twin": 2,                   # 201…
    "Family Plan": 4,            # 401…
}
_ROOMS_PER_FLOOR = 20


def _numbers_for(room_type: str, total: int) -> list:
    """Devuelve la lista de números para `total` unidades de un tipo."""
    base_floor = _FLOOR_BY_TYPE.get(room_type, 1)
    nums = []
    for i in range(total):
        floor = base_floor + (i // _ROOMS_PER_FLOOR)
        idx = (i % _ROOMS_PER_FLOOR) + 1
        # Planta baja: "001".. ; pisos: "101".. con el piso como centena.
        number = f"{floor:01d}{idx:02d}" if floor == 0 else f"{floor}{idx:02d}"
        nums.append((number, floor))
    return nums


def seed_units():
    db = SessionLocal()
    created = 0
    try:
        for room in db.query(Room).all():
            existing = db.query(RoomUnit).filter(RoomUnit.room_id == room.id).count()
            if existing > 0:
                continue  # idempotente: ya tiene unidades
            for number, floor in _numbers_for(room.room_type, room.total_units or 0):
                db.add(RoomUnit(room_id=room.id, number=number, floor=floor, status="available"))
                created += 1
        db.commit()
        print(f"[seed_units] {created} unidades creadas.")
        for room in db.query(Room).order_by(Room.base_price_usd).all():
            units = db.query(RoomUnit).filter(RoomUnit.room_id == room.id).count()
            print(f"   - {room.room_type}: {units} unidades")
        _backfill_bookings(db)
    finally:
        db.close()


def _backfill_bookings(db):
    """Asigna unidad a reservas activas/futuras no canceladas y sin unidad."""
    today = date.today()
    pending = (
        db.query(Booking)
        .filter(
            Booking.room_unit_id.is_(None),
            Booking.check_out >= today,
            Booking.status != "cancelled",
        )
        .order_by(Booking.check_in.asc())
        .all()
    )
    assigned = 0
    for b in pending:
        # Buscar una unidad del tipo sin solape con otras reservas ya asignadas.
        units = db.query(RoomUnit).filter(
            RoomUnit.room_id == b.room_id, RoomUnit.status == "available"
        ).order_by(RoomUnit.number.asc()).all()
        occupied = {
            x.room_unit_id
            for x in db.query(Booking).filter(
                Booking.room_id == b.room_id,
                Booking.room_unit_id.isnot(None),
                Booking.check_in < b.check_out,
                Booking.check_out > b.check_in,
                Booking.status != "cancelled",
            )
        }
        free = next((u for u in units if u.id not in occupied), None)
        if free:
            b.room_unit_id = free.id
            assigned += 1
    db.commit()
    print(f"[seed_units] backfill: {assigned} reservas activas/futuras asignadas a una unidad.")


def _prepare_db():
    """Importa todos los modelos, crea tablas y aplica migraciones livianas ANTES de sembrar.

    Resuelve relationships/FKs (Booking→contacts, Conversation→ConversationMessage, etc.)
    y garantiza que room_units y las columnas nuevas (bookings.room_unit_id, rooms.status)
    existan, ya que en Render los seeds corren antes del lifespan de la app.
    """
    import importlib
    import pkgutil
    import app.models as models_pkg
    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    from app.models.database import Base, engine, run_light_migrations
    Base.metadata.create_all(bind=engine)
    run_light_migrations()


if __name__ == "__main__":
    _prepare_db()
    seed_units()
