"""
Router del motor de reserva (single-hotel).

Expone el catálogo de habitaciones, la disponibilidad calculada y el alta/consulta de
reservas. La lógica vive en services/reservation_service.py (reutilizable por las tools
del agente). Pago SIMULADO: las reservas nacen con payment_status='paid'.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import reservation_service
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/reservations", tags=["Reservations"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class BookingCreate(BaseModel):
    room_id: Optional[int] = None
    room_type: Optional[str] = None
    check_in: date
    check_out: date
    guest_name: str = Field(..., min_length=2)
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    guests: int = Field(1, ge=1)
    source: str = "web"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/rooms")
async def get_rooms(db: Session = Depends(get_db)):
    """Catálogo de tipos de habitación (para la landing)."""
    return {"rooms": reservation_service.list_rooms(db)}


@router.get("/availability")
async def get_availability(
    check_in: date = Query(...),
    check_out: date = Query(...),
    guests: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Habitaciones disponibles en el rango, con precio total calculado."""
    try:
        rooms = reservation_service.get_availability(db, check_in, check_out, guests)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "guests": guests,
        "available_rooms": rooms,
    }


@router.post("/bookings")
async def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    """Crea una reserva (pago simulado). Devuelve el código de reserva."""
    if payload.room_id is None and not payload.room_type:
        raise HTTPException(
            status_code=400, detail="Indicá room_id o room_type."
        )
    result = reservation_service.create_booking(
        db,
        room_id=payload.room_id,
        room_type=payload.room_type,
        check_in=payload.check_in,
        check_out=payload.check_out,
        guest_name=payload.guest_name,
        guest_email=payload.guest_email,
        guest_phone=payload.guest_phone,
        guests=payload.guests,
        source=payload.source,
    )
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return {"booking": result}


@router.get("/bookings/{code}")
async def get_booking(code: str, db: Session = Depends(get_db)):
    """Consulta una reserva por su código (landing, agente y posventa)."""
    booking = reservation_service.get_booking(db, code)
    if booking is None:
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")
    return {"booking": booking}


@router.get("/bookings")
async def list_bookings(db: Session = Depends(get_db)):
    """Lista todas las reservas (para el backoffice)."""
    return {"bookings": reservation_service.list_bookings(db)}


@router.delete("/bookings/{code}")
async def delete_booking(code: str, db: Session = Depends(get_db)):
    """Elimina una reserva por su código (backoffice)."""
    ok = reservation_service.delete_booking(db, code)
    if not ok:
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")
    return {"success": True, "message": f"Reserva {code} eliminada"}
