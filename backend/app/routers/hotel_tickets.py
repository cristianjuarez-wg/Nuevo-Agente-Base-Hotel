"""
Router de tickets de soporte del HOTEL (backoffice).

Lista los HotelTicket que genera el agente de post-venta, enriquecidos con datos de la
reserva asociada (código, huésped). Solo lectura para la demo.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.hotel import HotelTicket
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/hotel-tickets", tags=["HotelTickets"])


def _enrich(ticket: HotelTicket) -> dict:
    data = ticket.to_dict()
    booking = ticket.booking
    data["booking_code"] = booking.code if booking else None
    data["guest_name"] = booking.guest_name if booking else None
    data["room_type"] = (booking.room.room_type if booking and booking.room else None)
    return data


@router.get("")
async def list_tickets(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Lista los tickets de soporte. Filtro opcional por status."""
    query = db.query(HotelTicket)
    if status:
        query = query.filter(HotelTicket.status == status)
    tickets = query.order_by(HotelTicket.created_at.desc()).all()
    return {"tickets": [_enrich(t) for t in tickets]}


@router.get("/stats")
async def ticket_stats(db: Session = Depends(get_db)):
    """Métricas rápidas para el dashboard del backoffice."""
    tickets = db.query(HotelTicket).all()
    total = len(tickets)
    escalated = sum(1 for t in tickets if t.status == "escalated")
    resolved = sum(1 for t in tickets if t.status == "resolved")
    open_count = sum(1 for t in tickets if t.status in ("open", "in_progress"))
    return {
        "total": total,
        "escalated": escalated,
        "resolved": resolved,
        "open": open_count,
    }
