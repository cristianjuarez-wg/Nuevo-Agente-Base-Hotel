"""
Servicio del motor de reserva (single-hotel).

Contiene la lógica de negocio de disponibilidad y creación de reservas, separada del
router para que las TOOLS del agente (hotel_tools.py) puedan reutilizarla directamente
sin pasar por HTTP — mismo patrón que en Freeway, donde las tools envuelven services.

Disponibilidad CALCULADA por solapamiento de fechas (no se almacena por día):
una Room está disponible en [check_in, check_out) si
    total_units − (bookings que solapan ese rango y no están cancelados) > 0.
"""
import secrets
import string
from datetime import date
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from app.models.hotel import Room, Booking
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Estados que NO ocupan inventario (no cuentan para el solapamiento).
_NON_BLOCKING_STATUSES = {"cancelled"}


def _generate_booking_code() -> str:
    """Código corto y legible para una reserva, ej. 'HTL-7F3A'."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"HTL-{suffix}"


def _nights_between(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def _units_booked(db: Session, room_id: int, check_in: date, check_out: date) -> int:
    """Cuántas unidades de un tipo de habitación están ocupadas en el rango dado.

    Dos rangos [a_in, a_out) y [b_in, b_out) se solapan si a_in < b_out y b_in < a_out.
    """
    overlapping = (
        db.query(Booking)
        .filter(
            Booking.room_id == room_id,
            Booking.check_in < check_out,
            Booking.check_out > check_in,
            ~Booking.status.in_(_NON_BLOCKING_STATUSES),
        )
        .count()
    )
    return overlapping


def list_rooms(db: Session) -> List[Dict]:
    """Catálogo de tipos de habitación (para la landing)."""
    rooms = db.query(Room).order_by(Room.base_price_usd.asc()).all()
    return [r.to_dict() for r in rooms]


def get_availability(
    db: Session, check_in: date, check_out: date, guests: int = 1
) -> List[Dict]:
    """Tipos de habitación disponibles en el rango, con precio total calculado.

    Devuelve solo habitaciones con capacidad suficiente y unidades libres.
    """
    if check_out <= check_in:
        raise ValueError("check_out debe ser posterior a check_in")

    nights = _nights_between(check_in, check_out)
    results: List[Dict] = []

    rooms = db.query(Room).filter(Room.capacity >= guests).all()
    for room in rooms:
        booked = _units_booked(db, room.id, check_in, check_out)
        units_left = room.total_units - booked
        if units_left <= 0:
            continue
        info = room.to_dict()
        info.update(
            {
                "units_available": units_left,
                "nights": nights,
                "total_price_usd": round(room.base_price_usd * nights, 2),
                "total_price_ars": round(room.base_price_ars * nights, 2),
            }
        )
        results.append(info)

    return results


def create_booking(
    db: Session,
    *,
    room_type: Optional[str] = None,
    room_id: Optional[int] = None,
    check_in: date,
    check_out: date,
    guest_name: str,
    guest_email: Optional[str] = None,
    guest_phone: Optional[str] = None,
    guests: int = 1,
    source: str = "web",
) -> Dict:
    """Crea una reserva si hay disponibilidad. Pago SIMULADO → payment_status='paid'.

    Acepta `room_id` (preciso, desde la landing) o `room_type` (desde el agente, que
    razona en lenguaje natural). Valida disponibilidad ANTES de crear — es el punto
    "determinístico" que el agente NO puede saltarse.

    Returns: dict con la reserva creada (incluye `code`) o un dict {"error": ...}.
    """
    if check_out <= check_in:
        return {"error": "El check-out debe ser posterior al check-in."}

    # Resolver la habitación
    room = None
    if room_id is not None:
        room = db.query(Room).filter(Room.id == room_id).first()
    elif room_type:
        room = (
            db.query(Room)
            .filter(Room.room_type.ilike(f"%{room_type.strip()}%"))
            .first()
        )
    if room is None:
        return {"error": "No se encontró ese tipo de habitación."}

    if room.capacity < guests:
        return {
            "error": f"La habitación '{room.room_type}' admite hasta {room.capacity} "
            f"huéspedes (se pidieron {guests})."
        }

    # Validación determinística de disponibilidad
    booked = _units_booked(db, room.id, check_in, check_out)
    if room.total_units - booked <= 0:
        return {
            "error": f"No hay disponibilidad de '{room.room_type}' para esas fechas."
        }

    nights = _nights_between(check_in, check_out)
    booking = Booking(
        code=_generate_booking_code(),
        room_id=room.id,
        guest_name=guest_name.strip(),
        guest_email=(guest_email or "").strip() or None,
        guest_phone=(guest_phone or "").strip() or None,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        nights=nights,
        total_price_usd=round(room.base_price_usd * nights, 2),
        total_price_ars=round(room.base_price_ars * nights, 2),
        status="confirmed",
        payment_status="paid",  # pago simulado
        source=source,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    logger.info(
        "Booking created",
        code=booking.code,
        room_type=room.room_type,
        source=source,
        check_in=str(check_in),
        check_out=str(check_out),
    )
    return booking.to_dict()


def get_booking(db: Session, code: str) -> Optional[Dict]:
    """Consulta una reserva por su código (usado por la landing, el agente y posventa)."""
    booking = db.query(Booking).filter(Booking.code == code.strip().upper()).first()
    return booking.to_dict() if booking else None


def list_bookings(db: Session) -> List[Dict]:
    """Todas las reservas (para el backoffice)."""
    bookings = db.query(Booking).order_by(Booking.check_in.asc()).all()
    return [b.to_dict() for b in bookings]
