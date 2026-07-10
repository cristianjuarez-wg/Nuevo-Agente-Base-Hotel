"""
Router para endpoints del Kanban de leads
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.models.database import get_db
from app.services.kanban_service import kanban_service
from app.utils.timezone_utils import iso_business
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/kanban", tags=["kanban"])

# Modelos de request
class UpdateStageRequest(BaseModel):
    stage: str

class AddNoteRequest(BaseModel):
    note: str

@router.get("/leads")
async def get_kanban_leads(db: Session = Depends(get_db)):
    """
    Obtiene todos los leads organizados por estado del kanban
    
    Returns:
        {
            "success": true,
            "data": {
                "new": [...],
                "contacted": [...],
                "interested": [...],
                "won": [...],
                "lost": [...]
            },
            "stats": {...}
        }
    """
    try:
        logger.info("GET /api/kanban/leads - Fetching kanban board")
        
        leads_by_stage = kanban_service.get_leads_by_stage(db)
        stats = kanban_service.get_kanban_stats(db)
        
        return {
            "success": True,
            "data": leads_by_stage,
            "stats": stats
        }
        
    except Exception as e:
        logger.error("Error in get_kanban_leads", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo leads del kanban: {str(e)}"
        )

@router.get("/leads/{lead_id}")
async def get_lead_detail(lead_id: int, db: Session = Depends(get_db)):
    """
    Obtiene el detalle completo de un lead
    
    Args:
        lead_id: ID del lead
        
    Returns:
        {
            "success": true,
            "data": {...}
        }
    """
    try:
        logger.info("GET /api/kanban/leads/{lead_id}", lead_id=lead_id)
        
        lead_detail = kanban_service.get_lead_detail(db, lead_id)
        
        if not lead_detail:
            raise HTTPException(
                status_code=404,
                detail=f"Lead {lead_id} no encontrado"
            )
        
        return {
            "success": True,
            "data": lead_detail
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in get_lead_detail", lead_id=lead_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo detalle del lead: {str(e)}"
        )

@router.put("/leads/{lead_id}/stage")
async def update_lead_stage(
    lead_id: int,
    request: UpdateStageRequest,
    db: Session = Depends(get_db)
):
    """
    Actualiza el estado del kanban de un lead
    
    Args:
        lead_id: ID del lead
        request: {"stage": "contacted"}
        
    Returns:
        {
            "success": true,
            "message": "Estado actualizado"
        }
    """
    try:
        logger.info("PUT /api/kanban/leads/{lead_id}/stage",
                   lead_id=lead_id,
                   new_stage=request.stage)
        
        success = kanban_service.update_lead_stage(db, lead_id, request.stage)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Lead {lead_id} no encontrado"
            )
        
        return {
            "success": True,
            "message": f"Lead movido a {request.stage}"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in update_lead_stage",
                    lead_id=lead_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error actualizando estado del lead: {str(e)}"
        )

@router.post("/leads/{lead_id}/notes")
async def add_lead_note(
    lead_id: int,
    request: AddNoteRequest,
    db: Session = Depends(get_db)
):
    """
    Agrega una nota a un lead
    
    Args:
        lead_id: ID del lead
        request: {"note": "Contactado por teléfono"}
        
    Returns:
        {
            "success": true,
            "message": "Nota agregada"
        }
    """
    try:
        logger.info("POST /api/kanban/leads/{lead_id}/notes", lead_id=lead_id)
        
        success = kanban_service.add_lead_note(db, lead_id, request.note)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Lead {lead_id} no encontrado"
            )
        
        return {
            "success": True,
            "message": "Nota agregada exitosamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in add_lead_note", lead_id=lead_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error agregando nota: {str(e)}"
        )

@router.get("/stats")
async def get_kanban_stats(db: Session = Depends(get_db)):
    """
    Obtiene estadísticas del kanban
    
    Returns:
        {
            "success": true,
            "data": {
                "total_leads": 43,
                "by_stage": {...},
                "conversion_rate": 65.5,
                "active_leads": 25
            }
        }
    """
    try:
        logger.info("GET /api/kanban/stats")
        
        stats = kanban_service.get_kanban_stats(db)
        
        return {
            "success": True,
            "data": stats
        }
        
    except Exception as e:
        logger.error("Error in get_kanban_stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )

@router.get("/search")
async def search_leads(query: str, db: Session = Depends(get_db)):
    """
    Busca leads por nombre, email o interés
    
    Args:
        query: Término de búsqueda
        
    Returns:
        {
            "success": true,
            "data": [...]
        }
    """
    try:
        logger.info("GET /api/kanban/search", query=query)
        
        results = kanban_service.search_leads(db, query)
        
        return {
            "success": True,
            "data": results
        }
        
    except Exception as e:
        logger.error("Error in search_leads", query=query, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error buscando leads: {str(e)}"
        )

@router.get("/leads/{lead_id}/timeline")
async def get_lead_timeline(lead_id: int, db: Session = Depends(get_db)):
    """
    Obtiene el historial completo del chat de un lead
    Basado en el endpoint de post-venta /tickets/{id}/timeline
    
    Returns:
        {
            "success": true,
            "data": {
                "lead_id": 123,
                "session_id": "abc-123",
                "total_messages": 10,
                "timeline": [
                    {
                        "id": 1,
                        "type": "user_message",
                        "message": "Hola, busco viaje a Europa",
                        "created_by": "Usuario",
                        "created_at": "2025-11-05T22:30:00",
                        "sequence_number": 1
                    },
                    ...
                ]
            }
        }
    """
    try:
        from app.models.lead import Lead
        from app.models.conversation_message import ConversationMessage
        
        logger.info("GET /api/kanban/leads/{lead_id}/timeline", lead_id=lead_id)
        
        # Obtener lead
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        
        if not lead:
            raise HTTPException(
                status_code=404,
                detail=f"Lead {lead_id} no encontrado"
            )
        
        timeline = []
        
        # Obtener mensajes de conversación (por session_id)
        if lead.session_id:
            conversation_messages = db.query(ConversationMessage).filter(
                ConversationMessage.session_id == lead.session_id,
                ConversationMessage.context_type == "pre_sale"
            ).order_by(ConversationMessage.sequence_number).all()
            
            for msg in conversation_messages:
                timeline.append({
                    "id": f"msg_{msg.id}",
                    "type": "conversation_message",
                    "role": msg.role,  # "user" o "assistant"
                    "message": msg.content,
                    "created_at": iso_business(msg.created_at),
                    "sequence_number": msg.sequence_number,
                    "is_user": msg.role == "user",
                    "is_agent": msg.role == "assistant",
                    "metadata": {
                        "has_context": msg.has_context,
                        "sources_used": msg.sources_used,
                        "tokens_used": msg.tokens_used,
                        "response_time_ms": msg.response_time_ms
                    }
                })
        
        # Ordenar por fecha
        timeline.sort(key=lambda x: x["created_at"] if x["created_at"] else "")
        
        # Renumerar
        for i, item in enumerate(timeline, 1):
            item["display_sequence"] = i
        
        logger.info("Lead timeline retrieved",
                   lead_id=lead_id,
                   session_id=lead.session_id,
                   message_count=len(timeline))
        
        return {
            "success": True,
            "data": {
                "lead_id": lead_id,
                "session_id": lead.session_id,
                "total_messages": len(timeline),
                "timeline": timeline
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving lead timeline", lead_id=lead_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo historial del chat: {str(e)}"
        )
