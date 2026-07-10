"""
Precio de habitación por MONEDA (Tarea B — multimoneda).

Hasta ahora el precio vivía en dos columnas de `rooms` (base_price_usd/base_price_ars), lo que
ataba el sistema al par USD/ARS. Esta tabla guarda un precio explícito por (room, moneda), para
que un cliente con CUALQUIER moneda (BRL, MXN...) tenga precios reales por moneda, no un valor
USD con la etiqueta cambiada.

Resolución de precio (ver room_price_service):
1. fila explícita en room_prices para la moneda pedida → gana;
2. si no, conversión desde otra moneda si hay cotización del par;
3. si no, el precio primario sin convertir (comportamiento de format_price_pair).

Las columnas legacy base_price_usd/base_price_ars NO se dropean (DB de producción; el drop se
documenta para una migración Alembic futura). Se siguen poblando para compat.
"""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint

from app.models.database import Base, engine


class RoomPrice(Base):
    __tablename__ = "room_prices"
    __table_args__ = (UniqueConstraint("room_id", "currency", name="uq_room_currency"),)

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    currency = Column(String(3), nullable=False)   # ISO 4217: "USD", "ARS", "BRL", "MXN"...
    amount = Column(Float, nullable=False)          # precio por noche en esa moneda

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "currency": self.currency, "amount": self.amount}


def ensure_table() -> None:
    """Crea la tabla room_prices si no existe. Se llama en el startup DESPUÉS de registrar
    `rooms` (la FK la necesita). No se hace a nivel de módulo para no fallar si `hotel` aún no
    fue importado (orden de FK). Importa contact/staff/restaurant antes que hotel para que el
    create_all a nivel de módulo de hotel.py resuelva sus FKs (mismo orden que bootstrap)."""
    import app.models.contact  # noqa: F401
    import app.models.staff  # noqa: F401
    import app.models.restaurant  # noqa: F401
    import app.models.hotel  # noqa: F401 — `rooms` en el metadata
    Base.metadata.create_all(bind=engine, tables=[RoomPrice.__table__])
