"""
Router de administración de HABITACIONES (backoffice).

CRUD de tipos de habitación. El precio se gestiona en USD (fuente de verdad);
el ARS se calcula al vuelo con la cotización vigente. Las habitaciones inactivas
no se ofrecen en el chat ni en la disponibilidad del sitio público.

Nota: en producción esta info vendría del PMS del hotel; acá la demo la gestiona
localmente.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.hotel import Room, Booking
from app.services import reservation_service, exchange_rate_service
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/admin/rooms", tags=["RoomsAdmin"])


class RoomPayload(BaseModel):
    room_type: str = Field(..., min_length=1)
    description: Optional[str] = None
    capacity: int = Field(2, ge=1)
    base_price_usd: float = Field(..., ge=0)
    total_units: int = Field(1, ge=0)
    bed_config: Optional[str] = None
    view: Optional[str] = None
    images: Optional[List[str]] = None
    amenities: Optional[List[str]] = None
    status: Optional[str] = "active"   # "active" | "inactive"


class StatusUpdate(BaseModel):
    status: str  # "active" | "inactive"


@router.get("")
def list_rooms_admin(db: Session = Depends(get_db)):
    """Todas las habitaciones (incluye inactivas), con ARS calculado de referencia."""
    rooms = reservation_service.list_rooms(db, include_inactive=True)
    current = exchange_rate_service.get_current_rate(db)
    return {"rooms": rooms, "exchange_rate": current}


@router.post("")
def create_room(payload: RoomPayload, db: Session = Depends(get_db)):
    """Crea una habitación. base_price_ars se deriva del USD (no se persiste con valor real)."""
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    room = Room(
        room_type=payload.room_type.strip(),
        description=(payload.description or "").strip() or None,
        capacity=payload.capacity,
        base_price_usd=payload.base_price_usd,
        base_price_ars=round(payload.base_price_usd * rate, 2),  # snapshot; el real se calcula al vuelo
        total_units=payload.total_units,
        bed_config=(payload.bed_config or "").strip() or None,
        view=(payload.view or "").strip() or None,
        images=payload.images or [],
        amenities=payload.amenities or [],
        status=payload.status or "active",
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    logger.info("Room created", id=room.id, room_type=room.room_type)
    return room.to_dict()


@router.put("/{room_id}")
def update_room(room_id: int, payload: RoomPayload, db: Session = Depends(get_db)):
    """Actualiza una habitación."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Habitación no encontrada.")
    rate = exchange_rate_service.get_current_rate(db)["rate"]

    room.room_type = payload.room_type.strip()
    room.description = (payload.description or "").strip() or None
    room.capacity = payload.capacity
    room.base_price_usd = payload.base_price_usd
    room.base_price_ars = round(payload.base_price_usd * rate, 2)
    room.total_units = payload.total_units
    room.bed_config = (payload.bed_config or "").strip() or None
    room.view = (payload.view or "").strip() or None
    room.images = payload.images or []
    room.amenities = payload.amenities or []
    if payload.status:
        room.status = payload.status

    db.commit()
    db.refresh(room)
    logger.info("Room updated", id=room.id)
    return room.to_dict()


@router.patch("/{room_id}/status")
def update_status(room_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    """Activa o desactiva una habitación."""
    if payload.status not in ("active", "inactive"):
        raise HTTPException(400, "Estado inválido. Usar 'active' o 'inactive'.")
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Habitación no encontrada.")
    room.status = payload.status
    db.commit()
    db.refresh(room)
    return room.to_dict()


@router.delete("/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    """Elimina una habitación. Si tiene reservas, sugiere desactivar en su lugar."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Habitación no encontrada.")

    has_bookings = db.query(Booking).filter(Booking.room_id == room_id).first()
    if has_bookings:
        raise HTTPException(
            409,
            "Esta habitación tiene reservas asociadas. Desactivala en lugar de eliminarla.",
        )

    db.delete(room)
    db.commit()
    logger.info("Room deleted", id=room_id)
    return {"deleted": True, "id": room_id}
