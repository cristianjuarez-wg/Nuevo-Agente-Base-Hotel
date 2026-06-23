"""
Router de tickets de soporte del HOTEL (backoffice).

Lista los HotelTicket que genera el agente de post-venta, enriquecidos con datos de la
reserva asociada (código, huésped). Solo lectura para la demo.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.hotel import HotelTicket, TICKET_OPEN_STATES, TICKET_RESOLVED_STATES
from app.models.staff import StaffMember
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/hotel-tickets", tags=["HotelTickets"])


def _enrich(ticket: HotelTicket) -> dict:
    data = ticket.to_dict()
    booking = ticket.booking
    data["booking_code"] = booking.code if booking else None
    data["guest_name"] = booking.guest_name if booking else None
    data["room_type"] = (booking.room.room_type if booking and booking.room else None)
    data["room_number"] = (booking.room_unit.number if booking and booking.room_unit else None)
    # Bitácora: quién hizo cada acción (agente vs humano vs equipo). Para el timeline.
    data["events"] = [e.to_dict() for e in (ticket.events or [])]
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


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Elimina un ticket de soporte por su ID (backoffice)."""
    ticket = db.query(HotelTicket).filter(HotelTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    db.delete(ticket)
    db.commit()
    logger.info("Ticket eliminado", ticket_id=ticket_id)
    return {"success": True, "message": f"Ticket {ticket_id} eliminado"}


class AssignPayload(BaseModel):
    area: Optional[str] = None
    staff_id: Optional[int] = None


class ResolvePayload(BaseModel):
    note: Optional[str] = None


class PriorityPayload(BaseModel):
    priority: str  # low | medium | high


@router.patch("/{ticket_id}/assign")
async def assign_ticket(ticket_id: int, payload: AssignPayload, db: Session = Depends(get_db)):
    """Reasigna manualmente un ticket operativo a un área y/o persona (fallback humano)."""
    from app.services import operations_service as ops
    ticket = db.query(HotelTicket).filter(HotelTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if payload.staff_id:
        staff = db.query(StaffMember).filter(StaffMember.id == payload.staff_id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Miembro del equipo no encontrado")
        ticket.assigned_staff_id = staff.id
        ticket.assigned_area = payload.area or staff.area
        ticket.status = "asignado"
        db.commit()
        ops.log_event(db, ticket, "assigned", actor_type="human",
                      note=f"→ {staff.name} (manual)")
        ops.notify_staff_assignment(staff, ticket)
    elif payload.area:
        staff = ops.classify_and_assign(db, ticket, area_hint=payload.area, actor_type="human")
        ops.notify_staff_assignment(staff, ticket)
    else:
        raise HTTPException(status_code=422, detail="Indicá un área o una persona")
    return {"ticket": _enrich(ticket)}


@router.patch("/{ticket_id}/pre-resolve")
async def pre_resolve_ticket(ticket_id: int, payload: ResolvePayload, db: Session = Depends(get_db)):
    """Marca un ticket como pre-resuelto desde el backoffice (dispara validación del huésped)."""
    from app.services import operations_service as ops
    ticket = db.query(HotelTicket).filter(HotelTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    staff = (
        db.query(StaffMember).filter(StaffMember.id == ticket.assigned_staff_id).first()
        if ticket.assigned_staff_id else None
    )
    status = ops.mark_pre_resolved(
        db, ticket, staff, payload.note or "Resuelto desde el backoffice",
        actor_type="human", actor_name="Backoffice",
    )
    return {"ticket": _enrich(ticket), "status": status}


@router.patch("/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Fuerza el cierre definitivo de un ticket (resuelto) desde el backoffice."""
    ticket = db.query(HotelTicket).filter(HotelTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    ticket.status = "resuelto"
    db.commit()
    from app.services import operations_service as ops
    ops.log_event(db, ticket, "resolved", actor_type="human", actor_name="Backoffice",
                  note="Cierre forzado desde el backoffice")
    return {"ticket": _enrich(ticket)}


@router.patch("/{ticket_id}/reopen")
async def reopen_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Reabre un ticket (vuelve a 'asignado') desde el backoffice."""
    ticket = db.query(HotelTicket).filter(HotelTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    ticket.status = "asignado"
    db.commit()
    from app.services import operations_service as ops
    ops.log_event(db, ticket, "reopened", actor_type="human", actor_name="Backoffice",
                  note="Reabierto desde el backoffice")
    return {"ticket": _enrich(ticket)}


_PRIORITY_LABELS = {"low": "baja", "medium": "media", "high": "alta"}


@router.patch("/{ticket_id}/priority")
async def set_ticket_priority(ticket_id: int, payload: PriorityPayload, db: Session = Depends(get_db)):
    """Cambia la prioridad de un ticket desde el backoffice (acción manual)."""
    if payload.priority not in _PRIORITY_LABELS:
        raise HTTPException(status_code=422, detail="Prioridad inválida (low/medium/high)")
    ticket = db.query(HotelTicket).filter(HotelTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    ticket.priority = payload.priority
    db.commit()
    from app.services import operations_service as ops
    ops.log_event(db, ticket, "priority", actor_type="human", actor_name="Backoffice",
                  note=f"Prioridad → {_PRIORITY_LABELS[payload.priority]}")
    return {"ticket": _enrich(ticket)}


@router.get("/stats")
async def ticket_stats(db: Session = Depends(get_db)):
    """Métricas rápidas para el dashboard del backoffice."""
    tickets = db.query(HotelTicket).all()
    total = len(tickets)
    escalated = sum(1 for t in tickets if t.status == "escalated")
    resolved = sum(1 for t in tickets if t.status in TICKET_RESOLVED_STATES)
    open_count = sum(1 for t in tickets if t.status in TICKET_OPEN_STATES)
    return {
        "total": total,
        "escalated": escalated,
        "resolved": resolved,
        "open": open_count,
    }
