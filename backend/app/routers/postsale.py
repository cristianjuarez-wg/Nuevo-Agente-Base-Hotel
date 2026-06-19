"""
Router de Post-Venta
Endpoints para gestión de paquetes vendidos y tickets de soporte
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from typing import List, Optional, Literal
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytz
from pydantic import BaseModel

from app.models.database import get_db
from app.models.postsale import (
    SoldPackage, SupportTicket, TicketInteraction,
    PackageFlight, PackageAccommodation
)
from app.services.postsale_service import PostSaleService
from app.services.package_validator import PackageValidator
from app.services.postsale_vector_store import PostSaleVectorStore
from app.services.package_service import PackageService
from app.services.voucher_service import voucher_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/postsale", tags=["postsale"])


# ============================================================================
# HELPERS
# ============================================================================

def get_argentina_time():
    """Obtiene la hora actual en Argentina (UTC-3)"""
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    return datetime.now(tz)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CommentCreate(BaseModel):
    comment: str
    operator_name: str
    comment_type: str = "operator_comment"


class TicketUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "waiting_customer", "resolved", "closed"]] = None
    priority: Optional[Literal["low", "medium", "high", "urgent"]] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# PAQUETES VENDIDOS
# ============================================================================

@router.get("/packages")
def list_packages(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    trip_status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Lista paquetes vendidos con filtros
    
    - **skip**: Número de registros a saltar (paginación)
    - **limit**: Número máximo de registros a retornar
    - **trip_status**: Filtrar por estado (confirmed, in_progress, completed, cancelled)
    - **search**: Buscar por nombre, email, código de reserva
    """
    try:
        query = db.query(SoldPackage)
        
        # Filtro por estado
        if trip_status:
            query = query.filter(SoldPackage.trip_status == trip_status)
        
        # Búsqueda
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                (SoldPackage.booking_code.ilike(search_filter)) |
                (SoldPackage.passenger_name.ilike(search_filter)) |
                (SoldPackage.passenger_email.ilike(search_filter)) |
                (SoldPackage.package_name.ilike(search_filter))
            )
        
        # Ordenar por fecha de creación (más recientes primero)
        query = query.order_by(SoldPackage.created_at.desc())
        
        # Paginación
        total = query.count()
        packages = query.offset(skip).limit(limit).all()
        
        logger.info("Packages listed",
                   total=total,
                   returned=len(packages),
                   trip_status=trip_status)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "packages": [pkg.to_dict() for pkg in packages]
        }
        
    except Exception as e:
        logger.error("Error listing packages", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/grouped")
async def get_packages_grouped(db: Session = Depends(get_db)):
    """
    Obtiene paquetes turísticos agrupados con sus reservas y pasajeros
    
    Returns:
        Lista de paquetes con estructura jerárquica:
        - Paquete turístico base
          - Reservas (vouchers)
            - Pasajeros
    """
    try:
        logger.info("Getting packages grouped")
        
        package_service = PackageService(db)
        packages = package_service.get_packages_grouped()
        
        logger.info(f"Packages grouped retrieved: {len(packages)} packages")
        
        return {
            "packages": packages,
            "total_packages": len(packages),
            "total_reservations": sum(p["reservation_count"] for p in packages),
            "total_passengers": sum(p["total_passengers"] for p in packages)
        }
        
    except Exception as e:
        logger.error("Error getting packages grouped", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{package_id}")
def get_package(package_id: int, db: Session = Depends(get_db)):
    """
    Obtiene detalle completo de un paquete vendido.

    Incluye: vuelos, hoteles, traslados, actividades, documentos.
    """
    try:
        package = (
            db.query(SoldPackage)
            .options(
                selectinload(SoldPackage.flights),
                selectinload(SoldPackage.accommodations),
            )
            .filter(SoldPackage.id == package_id)
            .first()
        )
        
        if not package:
            raise HTTPException(status_code=404, detail="Paquete no encontrado")
        
        # Construir respuesta completa
        result = package.to_dict()
        
        # Agregar detalles relacionados
        result["flights"] = [
            {
                "id": f.id,
                "airline": f.airline,
                "flight_number": f.flight_number,
                "departure_airport": f.departure_airport_code,
                "departure_terminal": f.departure_terminal,
                "arrival_airport": f.arrival_airport_code,
                "arrival_terminal": f.arrival_terminal,
                "departure_datetime": f.departure_datetime.isoformat() if f.departure_datetime else None,
                "arrival_datetime": f.arrival_datetime.isoformat() if f.arrival_datetime else None,
                "seat_numbers": f.seat_numbers,
                "cabin_class": f.cabin_class,
                "baggage_allowance": f.baggage_allowance,
                "status": f.flight_status,
                "provider_id": f.provider_id,
                "provider_name": f.provider.provider_name if f.provider else None
            }
            for f in package.flights
        ]
        
        result["accommodations"] = [
            {
                "id": h.id,
                "hotel_name": h.hotel_name,
                "hotel_category": h.hotel_category,
                "city": h.city,
                "address": h.address,
                "checkin_date": h.checkin_date.isoformat() if h.checkin_date else None,
                "checkout_date": h.checkout_date.isoformat() if h.checkout_date else None,
                "nights_count": h.nights_count,
                "room_type": h.room_type,
                "bed_configuration": h.bed_configuration,
                "meal_plan": h.meal_plan,
                "provider_id": h.provider_id,
                "provider_name": h.provider.provider_name if h.provider else None
            }
            for h in package.accommodations
        ]
        
        result["transfers"] = [
            {
                "id": t.id,
                "transfer_type": t.transfer_type,
                "pickup_location": t.pickup_location,
                "dropoff_location": t.dropoff_location,
                "transfer_date": t.transfer_date.isoformat() if t.transfer_date else None,
                "pickup_time": str(t.pickup_time) if t.pickup_time else None,
                "pickup_instructions": t.pickup_instructions,
                "vehicle_type": t.vehicle_type,
                "transfer_status": t.transfer_status,
                "provider_id": t.provider_id,
                "provider_name": t.provider.provider_name if t.provider else None
            }
            for t in package.transfers
        ]
        
        result["activities"] = [
            {
                "id": a.id,
                "activity_name": a.activity_name,
                "city": a.city,
                "activity_date": a.activity_date.isoformat() if a.activity_date else None,
                "start_time": str(a.start_time) if a.start_time else None,
                "duration_hours": a.duration_hours,
                "meeting_point": a.meeting_point,
                "description": a.description,
                "provider_id": a.provider_id,
                "provider_name": a.provider.provider_name if a.provider else None
            }
            for a in package.activities
        ]
        
        result["documents"] = [
            {
                "id": d.id,
                "document_type": d.document_type,
                "document_name": d.document_name,
                "file_url": d.file_url
            }
            for d in package.documents
        ]
        
        result["itinerary"] = [
            {
                "id": i.id,
                "day_number": i.day_number,
                "day_title": i.day_title,
                "city": i.city,
                "morning_activities": i.morning_activities,
                "afternoon_activities": i.afternoon_activities,
                "evening_activities": i.evening_activities,
                "breakfast_included": i.breakfast_included,
                "lunch_included": i.lunch_included,
                "dinner_included": i.dinner_included
            }
            for i in package.itinerary
        ]
        
        logger.info("Package retrieved", package_id=package_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting package", package_id=package_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/search/semantic")
def search_packages_semantic(
    query: str = Query(..., min_length=3),
    n_results: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Búsqueda semántica de paquetes
    
    - **query**: Texto de búsqueda natural
    - **n_results**: Número de resultados a retornar
    """
    try:
        vector_store = PostSaleVectorStore()
        
        # Buscar en vector store
        results = vector_store.search_package(query, n_results=n_results)
        
        # Enriquecer con datos de BD
        enriched_results = []
        for result in results:
            package_id = result["package_id"]
            package = db.query(SoldPackage).get(package_id)
            
            if package:
                enriched_results.append({
                    **result,
                    "package": package.to_dict()
                })
        
        logger.info("Semantic search completed",
                   query=query,
                   results_found=len(enriched_results))
        
        return {
            "query": query,
            "results": enriched_results
        }
        
    except Exception as e:
        logger.error("Error in semantic search", query=query, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TICKETS DE SOPORTE
# ============================================================================

@router.get("/tickets")
def list_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    package_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Lista tickets de soporte con filtros
    
    - **status**: open, in_progress, waiting_customer, resolved, closed
    - **priority**: low, medium, high, urgent
    - **package_id**: Filtrar por paquete específico
    """
    try:
        # ✅ OPTIMIZACIÓN: Eager loading para evitar N+1 queries
        query = db.query(SupportTicket).options(
            joinedload(SupportTicket.package),  # Cargar paquete asociado
            selectinload(SupportTicket.interactions)  # Cargar interacciones
        )
        
        # Filtros
        if status:
            query = query.filter(SupportTicket.status == status)
        
        if priority:
            query = query.filter(SupportTicket.priority == priority)
        
        if package_id:
            query = query.filter(SupportTicket.package_id == package_id)
        
        # Ordenar por prioridad y fecha
        priority_order = {
            'urgent': 1,
            'high': 2,
            'medium': 3,
            'low': 4
        }
        
        query = query.order_by(SupportTicket.created_at.desc())
        
        # Paginación
        total = query.count()
        tickets = query.offset(skip).limit(limit).all()
        
        logger.info("Tickets listed",
                   total=total,
                   returned=len(tickets),
                   status=status,
                   priority=priority)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "tickets": [ticket.to_dict() for ticket in tickets]
        }
        
    except Exception as e:
        logger.error("Error listing tickets", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """
    Obtiene detalle completo de un ticket
    
    Incluye: interacciones, paquete asociado
    """
    try:
        # ✅ OPTIMIZACIÓN: Eager loading para cargar relaciones
        ticket = db.query(SupportTicket).options(
            joinedload(SupportTicket.package),
            selectinload(SupportTicket.interactions),
            joinedload(SupportTicket.provider)
        ).filter(SupportTicket.id == ticket_id).first()
        
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        
        # Construir respuesta
        result = ticket.to_dict()
        
        # Agregar interacciones
        result["interactions"] = [
            {
                "id": i.id,
                "interaction_type": i.interaction_type,
                "message": i.message,
                "created_by": i.created_by,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "channel": i.channel
            }
            for i in ticket.interactions
        ]
        
        # Agregar info del paquete
        if ticket.package:
            result["package"] = ticket.package.to_dict()
        
        logger.info("Ticket retrieved", ticket_id=ticket_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting ticket", ticket_id=ticket_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int,
    update: TicketUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Actualiza un ticket de soporte.

    - **status**: open | in_progress | waiting_customer | resolved | closed
    - **priority**: low | medium | high | urgent
    - **assigned_to**: Asignar a operador
    - **notes**: Notas adicionales
    """
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")

        now_utc = datetime.now(timezone.utc)

        if update.status is not None:
            ticket.status = update.status

        if update.priority is not None:
            ticket.priority = update.priority

        if update.assigned_to is not None:
            ticket.assigned_to = update.assigned_to
            ticket.assigned_at = now_utc

        ticket.updated_at = now_utc

        if update.notes:
            interaction = TicketInteraction(
                ticket_id=ticket.id,
                interaction_type="note",
                message=update.notes,
                created_by=update.assigned_to or "System",
                created_at=now_utc,
            )
            db.add(interaction)

        db.commit()
        db.refresh(ticket)

        logger.info("Ticket updated",
                   ticket_id=ticket_id,
                   status=update.status,
                   priority=update.priority)

        return ticket.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating ticket", ticket_id=ticket_id, error=str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: int,
    resolution: str,
    resolution_type: str = "operator_resolved",
    db: Session = Depends(get_db)
):
    """
    Marca un ticket como resuelto
    
    - **resolution**: Texto de la resolución
    - **resolution_type**: auto_resolved o operator_resolved
    """
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        
        # Resolver ticket
        postsale_service = PostSaleService(db)
        postsale_service.resolve_ticket(
            ticket,
            resolution,
            auto_resolved=(resolution_type == "auto_resolved")
        )
        
        logger.info("Ticket resolved",
                   ticket_id=ticket_id,
                   resolution_type=resolution_type)
        
        return ticket.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resolving ticket", ticket_id=ticket_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets/{ticket_id}/comments")
def add_operator_comment(
    ticket_id: int,
    comment_data: CommentCreate,
    db: Session = Depends(get_db)
):
    """
    Agrega un comentario de operador al ticket
    
    - **comment**: Texto del comentario
    - **operator_name**: Nombre del operador que comenta
    - **comment_type**: Tipo de comentario (operator_comment, operator_action, system_event)
    """
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        
        # Contar interacciones para sequence_number
        interaction_count = db.query(TicketInteraction).filter(
            TicketInteraction.ticket_id == ticket.id
        ).count()
        
        # Crear interacción de comentario
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type=comment_data.comment_type,
            message=comment_data.comment,
            created_by=comment_data.operator_name,
            created_at=get_argentina_time(),
            sequence_number=interaction_count + 1,
            channel="operator_panel"
        )
        
        db.add(interaction)
        
        # Actualizar timestamp del ticket
        ticket.updated_at = get_argentina_time()
        
        db.commit()
        db.refresh(interaction)
        
        logger.info("Operator comment added",
                   ticket_id=ticket_id,
                   operator=comment_data.operator_name,
                   comment_type=comment_data.comment_type)
        
        return {
            "success": True,
            "interaction_id": interaction.id,
            "created_at": interaction.created_at.isoformat(),
            "sequence_number": interaction.sequence_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error adding operator comment", ticket_id=ticket_id, error=str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tickets/{ticket_id}/timeline")
def get_ticket_timeline(
    ticket_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Obtiene la timeline del ticket con paginación.

    - **page**: Página (desde 1)
    - **limit**: Ítems por página (máx 200)
    """
    from app.models.conversation_message import ConversationMessage

    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")

        timeline = []

        # 1. Mensajes de conversación (post_sale)
        if ticket.session_id:
            conversation_messages = db.query(ConversationMessage).filter(
                ConversationMessage.session_id == ticket.session_id,
                ConversationMessage.context_type == "post_sale"
            ).order_by(ConversationMessage.sequence_number).all()

            for msg in conversation_messages:
                timeline.append({
                    "id": f"msg_{msg.id}",
                    "type": "conversation_message",
                    "role": msg.role,
                    "message": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "sequence_number": msg.sequence_number,
                    "is_conversation": True,
                    "is_user": msg.role == "user",
                    "is_agent": msg.role == "assistant",
                    "metadata": {
                        "has_context": msg.has_context,
                        "sources_used": msg.sources_used,
                        "tokens_used": msg.tokens_used,
                        "response_time_ms": msg.response_time_ms,
                    },
                })

        # 2. Interactions del ticket
        interactions = db.query(TicketInteraction).filter(
            TicketInteraction.ticket_id == ticket.id
        ).order_by(TicketInteraction.sequence_number).all()

        for interaction in interactions:
            timeline.append({
                "id": f"int_{interaction.id}",
                "type": interaction.interaction_type,
                "message": interaction.message,
                "created_by": interaction.created_by,
                "created_at": interaction.created_at.isoformat() if interaction.created_at else None,
                "sequence_number": interaction.sequence_number,
                "channel": interaction.channel,
                "category": interaction.interaction_category,
                "requires_escalation": interaction.requires_escalation,
                "auto_resolved": interaction.auto_resolved,
                "resolved_at": interaction.resolved_at.isoformat() if interaction.resolved_at else None,
                "is_conversation": False,
                "is_operator": interaction.interaction_type in [
                    "operator_comment", "operator_action", "system_event"
                ],
            })

        # 3. Ordenar y paginar
        timeline.sort(key=lambda x: x["created_at"] or "")
        total_items = len(timeline)
        offset = (page - 1) * limit
        paginated = timeline[offset: offset + limit]

        for i, item in enumerate(paginated, start=offset + 1):
            item["display_sequence"] = i

        conversation_count = sum(1 for x in paginated if x.get("is_conversation", False))
        interaction_count = sum(1 for x in paginated if not x.get("is_conversation", False))

        logger.info("Timeline retrieved",
                   ticket_id=ticket_id,
                   total_items=total_items,
                   page=page,
                   limit=limit)

        return {
            "ticket_id": ticket_id,
            "ticket_number": ticket.ticket_number,
            "session_id": ticket.session_id,
            "total_items": total_items,
            "page": page,
            "limit": limit,
            "total_pages": (total_items + limit - 1) // limit,
            "conversation_messages_count": conversation_count,
            "ticket_interactions_count": interaction_count,
            "timeline": paginated,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving timeline", ticket_id=ticket_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ANALYTICS
# ============================================================================

@router.get("/analytics/summary")
def get_analytics_summary(db: Session = Depends(get_db)):
    """
    Resumen general de analytics post-venta
    
    Incluye: total tickets, tasa auto-resolución, tiempo promedio, etc.
    """
    try:
        # Total de tickets
        total_tickets = db.query(SupportTicket).count()
        
        # Tickets por estado
        tickets_by_status = {}
        for status in ['open', 'in_progress', 'waiting_customer', 'resolved', 'closed']:
            count = db.query(SupportTicket).filter(SupportTicket.status == status).count()
            tickets_by_status[status] = count
        
        # Tickets por prioridad
        tickets_by_priority = {}
        for priority in ['urgent', 'high', 'medium', 'low']:
            count = db.query(SupportTicket).filter(SupportTicket.priority == priority).count()
            tickets_by_priority[priority] = count
        
        # Tasa de auto-resolución
        auto_resolved = db.query(SupportTicket).filter(
            SupportTicket.auto_resolved_by_agent == True
        ).count()
        auto_resolution_rate = (auto_resolved / total_tickets * 100) if total_tickets > 0 else 0
        
        # Tiempo promedio de resolución
        resolved_tickets = db.query(SupportTicket).filter(
            SupportTicket.resolution_time_minutes.isnot(None)
        ).all()
        
        avg_resolution_time = 0
        if resolved_tickets:
            total_time = sum(t.resolution_time_minutes for t in resolved_tickets)
            avg_resolution_time = total_time / len(resolved_tickets)
        
        # Tickets creados últimos 7 días
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_tickets = db.query(SupportTicket).filter(
            SupportTicket.created_at >= seven_days_ago
        ).count()
        
        logger.info("Analytics summary generated")
        
        return {
            "total_tickets": total_tickets,
            "tickets_by_status": tickets_by_status,
            "tickets_by_priority": tickets_by_priority,
            "auto_resolution_rate": round(auto_resolution_rate, 2),
            "avg_resolution_time_minutes": round(avg_resolution_time, 2),
            "recent_tickets_7_days": recent_tickets,
            "total_packages": db.query(SoldPackage).count()
        }
        
    except Exception as e:
        logger.error("Error generating analytics summary", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/tickets-by-category")
def get_tickets_by_category(db: Session = Depends(get_db)):
    """
    Distribución de tickets por categoría
    """
    try:
        categories = ['flight', 'hotel', 'transfer', 'activity', 'documentation', 'change', 'general']
        
        result = {}
        for category in categories:
            count = db.query(SupportTicket).filter(
                SupportTicket.ticket_category == category
            ).count()
            result[category] = count
        
        logger.info("Tickets by category retrieved")
        
        return result
        
    except Exception as e:
        logger.error("Error getting tickets by category", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINTS - DETALLE COMPLETO DE RESERVA
# ============================================================================

@router.get("/reservations/{booking_code}/complete")
async def get_reservation_complete(
    booking_code: str,
    db: Session = Depends(get_db)
):
    """
    Obtiene información completa de una reserva incluyendo:
    - Pasajeros
    - Vuelos con proveedores
    - Hoteles con proveedores
    - Traslados con proveedores
    - Actividades con proveedores
    - Itinerario
    
    Args:
        booking_code: Código de reserva (ej: BK-2025-200)
    """
    try:
        logger.info(f"Getting complete reservation: {booking_code}")
        
        package_service = PackageService(db)
        reservation_data = package_service.get_reservation_complete(booking_code)
        
        if not reservation_data:
            raise HTTPException(
                status_code=404,
                detail=f"Reservation {booking_code} not found"
            )
        
        logger.info(f"Complete reservation retrieved: {booking_code}")
        
        return reservation_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting complete reservation {booking_code}", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VOUCHERS
# ============================================================================

import re as _re
_BOOKING_CODE_RE = _re.compile(r'^[A-Z0-9\-]{3,20}$')


@router.get("/voucher/{booking_code}")
async def download_voucher(
    booking_code: str,
    db: Session = Depends(get_db)
):
    """
    Descarga el voucher en PDF de una reserva.

    Args:
        booking_code: Código de reserva alfanumérico (ej: BK-2025-001)

    Returns:
        FileResponse: Archivo PDF del voucher
    """
    if not _BOOKING_CODE_RE.match(booking_code.upper()):
        raise HTTPException(status_code=400, detail="Formato de código de reserva inválido")

    booking_code = booking_code.upper()

    try:
        logger.info(f"Voucher download requested for {booking_code}")
        
        # Verificar que la reserva existe
        package = db.query(SoldPackage).filter(
            SoldPackage.booking_code == booking_code
        ).first()
        
        if not package:
            logger.warning(f"Package not found for voucher: {booking_code}")
            raise HTTPException(
                status_code=404,
                detail=f"Reservation {booking_code} not found"
            )
        
        # Generar o recuperar PDF
        pdf_path = await voucher_service.generate_voucher_pdf(booking_code, db)
        
        # Verificar que el archivo existe
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            logger.error(f"Voucher PDF not found: {pdf_path}")
            raise HTTPException(
                status_code=500,
                detail="Error generating voucher"
            )
        
        logger.info(f"Voucher downloaded successfully: {booking_code}")
        
        # Retornar archivo PDF
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"Voucher_{booking_code}.pdf",
            headers={
                "Content-Disposition": f"attachment; filename=Voucher_{booking_code}.pdf"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading voucher {booking_code}", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))