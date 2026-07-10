"""
Router para gestión de leads
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.services.lead_service import lead_service
from app.core.observability.logging_config import get_logger
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel

logger = get_logger(__name__)
router = APIRouter(prefix="/api/leads", tags=["Leads"])

class LeadStatusUpdate(BaseModel):
    status: Literal["active", "contacted", "converted", "inactive", "new"]

class LeadFieldsUpdate(BaseModel):
    name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class LeadFollowUpCreate(BaseModel):
    note: str
    actor_name: Optional[str] = None  # quién deja el seguimiento (staffer); default "Backoffice"

class LeadResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict] = None

@router.get("/stats")
async def get_lead_stats():
    """Obtiene estadísticas generales de leads"""
    try:
        stats = lead_service.get_lead_stats()
        
        logger.info("Lead stats retrieved", **stats)
        
        return {
            "success": True,
            "data": stats
        }
    
    except Exception as e:
        logger.error("Error getting lead stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )

@router.get("/active")
async def get_active_leads(limit: int = 50, include_unnamed: bool = False,
                           include_converted: bool = False):
    """Obtiene leads ordenados por prioridad.

    `include_unnamed=true` suma los contactos crudos (teléfono sin nombre, ej. un número de
    WhatsApp que consultó). Por defecto solo los calificados (con nombre).
    `include_converted=true` suma los leads ya convertidos/ganados (que reservaron); por defecto
    solo los `active`. La lista del backoffice lo usa para mostrar TODO (como el tablero).
    """
    try:
        leads = lead_service.get_active_leads(
            limit=limit, include_unnamed=include_unnamed, include_converted=include_converted,
        )

        # Indicador "tiene WhatsApp": el lead nos escribió por ese canal (dato real, no
        # heurística). El canal se derivó del session_id "wa_" al crear el lead.
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            channel = (lead.get("metadata") or {}).get("channel")
            if channel is None:
                channel = "whatsapp" if str(lead.get("session_id", "")).startswith("wa_") else None
            lead["whatsapp_linked"] = (channel == "whatsapp")

        logger.info("Active leads retrieved", count=len(leads))
        
        return {
            "success": True,
            "data": {
                "leads": leads,
                "count": len(leads)
            }
        }
    
    except Exception as e:
        logger.error("Error getting active leads", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo leads activos: {str(e)}"
        )

@router.get("/type/{lead_type}")
async def get_leads_by_type(lead_type: str):
    """Obtiene leads por tipo (CALIENTE, TIBIO, FRIO)"""
    try:
        if lead_type.upper() not in ['CALIENTE', 'TIBIO', 'FRIO']:
            raise HTTPException(
                status_code=400,
                detail="Tipo de lead inválido. Debe ser: CALIENTE, TIBIO o FRIO"
            )
        
        leads = lead_service.get_leads_by_type(lead_type.upper())
        
        logger.info("Leads by type retrieved", 
                   lead_type=lead_type.upper(),
                   count=len(leads))
        
        return {
            "success": True,
            "data": {
                "lead_type": lead_type.upper(),
                "leads": leads,
                "count": len(leads)
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting leads by type", 
                    lead_type=lead_type,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo leads por tipo: {str(e)}"
        )

@router.get("/ready-for-contact")
async def get_leads_ready_for_contact():
    """Obtiene leads listos para ser contactados"""
    try:
        leads = lead_service.get_leads_ready_for_contact()
        
        logger.info("Leads ready for contact retrieved", count=len(leads))
        
        return {
            "success": True,
            "data": {
                "leads": leads,
                "count": len(leads),
                "message": f"Encontrados {len(leads)} leads listos para contactar"
            }
        }
    
    except Exception as e:
        logger.error("Error getting leads ready for contact", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo leads para contactar: {str(e)}"
        )

@router.get("/session/{session_id}")
async def get_lead_by_session(session_id: str):
    """Obtiene lead por session_id"""
    try:
        lead = lead_service.get_lead_by_session(session_id)
        
        if not lead:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró lead para la sesión: {session_id}"
            )
        
        logger.info("Lead by session retrieved", session_id=session_id)
        
        return {
            "success": True,
            "data": lead
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting lead by session", 
                    session_id=session_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo lead: {str(e)}"
        )

@router.patch("/{lead_id}")
async def update_lead(lead_id: int, payload: LeadFieldsUpdate):
    """Edita los datos de contacto de un lead (nombre, apellido, email, teléfono)."""
    try:
        updated = lead_service.update_lead_fields(lead_id, payload.model_dump(exclude_unset=True))
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Lead con ID {lead_id} no encontrado")
        logger.info("Lead updated", lead_id=lead_id)
        return {"success": True, "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating lead", lead_id=lead_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Error actualizando lead: {str(e)}")

@router.get("/{lead_id}/events")
async def get_lead_events(lead_id: int, db: Session = Depends(get_db)):
    """Bitácora de actividad del lead (acciones de Aura + seguimientos humanos), cronológica."""
    from app.models.lead import Lead, LeadEvent
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} no encontrado")
    events = (
        db.query(LeadEvent)
        .filter(LeadEvent.lead_id == lead_id)
        .order_by(LeadEvent.created_at.asc(), LeadEvent.id.asc())
        .all()
    )
    return {"success": True, "data": {"lead_id": lead_id, "events": [e.to_dict() for e in events]}}


@router.post("/{lead_id}/events")
async def add_lead_followup(lead_id: int, payload: LeadFollowUpCreate, db: Session = Depends(get_db)):
    """Agrega un SEGUIMIENTO humano a la bitácora del lead (con autor + fecha/hora)."""
    from app.models.lead import Lead
    from app.services import lead_events_service as les
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} no encontrado")
    note = (payload.note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="El seguimiento no puede estar vacío")
    ev = les.log_lead_event(
        db, lead_id, action="seguimiento", actor_type="human",
        actor_name=(payload.actor_name or "Backoffice"), note=note,
    )
    logger.info("Lead follow-up added", lead_id=lead_id)
    return {"success": True, "data": ev.to_dict() if ev else None}


@router.post("/{lead_id}/summarize")
async def summarize_lead(lead_id: int, db: Session = Depends(get_db)):
    """Genera bajo demanda un resumen IA de la charla del lead y lo agrega a la bitácora.
    Barato (modelo económico) y respeta el freno de gasto; best-effort."""
    from app.models.lead import Lead
    from app.services import lead_events_service as les
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} no encontrado")
    ev = await les.generate_ai_summary(db, lead_id)
    if ev is None:
        return {"success": False, "message": "No se pudo generar el resumen (sin charla o presupuesto excedido)."}
    return {"success": True, "data": ev.to_dict()}


@router.patch("/{lead_id}/status")
async def update_lead_status(lead_id: int, status_update: LeadStatusUpdate):
    """Actualiza el status de un lead"""
    try:
        valid_statuses = ["active", "contacted", "converted", "inactive"]
        
        if status_update.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Status inválido. Debe ser uno de: {', '.join(valid_statuses)}"
            )
        
        success = lead_service.update_lead_status(lead_id, status_update.status)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Lead con ID {lead_id} no encontrado"
            )
        
        logger.info("Lead status updated", 
                   lead_id=lead_id,
                   new_status=status_update.status)
        
        return {
            "success": True,
            "message": f"Status del lead {lead_id} actualizado a '{status_update.status}'"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating lead status", 
                    lead_id=lead_id,
                    status=status_update.status,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error actualizando status del lead: {str(e)}"
        )

@router.delete("/{lead_id}")
async def delete_lead(lead_id: int):
    """Elimina un lead por su ID."""
    try:
        success = lead_service.delete_lead(lead_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Lead con ID {lead_id} no encontrado"
            )

        logger.info("Lead deleted", lead_id=lead_id)

        return {
            "success": True,
            "message": f"Lead {lead_id} eliminado"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting lead", lead_id=lead_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando lead: {str(e)}"
        )

@router.get("/export/csv")
async def export_leads_csv():
    """Exporta leads a formato CSV (para futuras implementaciones)"""
    try:
        # Por ahora retornamos los datos en JSON
        # En el futuro se puede implementar exportación real a CSV
        leads = lead_service.get_active_leads(limit=1000)
        
        return {
            "success": True,
            "message": "Exportación disponible en formato JSON",
            "data": {
                "leads": leads,
                "total": len(leads),
                "export_format": "json",
                "note": "Implementación CSV pendiente"
            }
        }
    
    except Exception as e:
        logger.error("Error exporting leads", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error exportando leads: {str(e)}"
        )

@router.get("/dashboard")
async def get_leads_dashboard():
    """Obtiene datos para dashboard de leads"""
    try:
        # Estadísticas generales
        stats = lead_service.get_lead_stats()
        
        # Leads prioritarios (top 10)
        priority_leads = lead_service.get_active_leads(limit=10)
        
        # Leads listos para contactar
        ready_leads = lead_service.get_leads_ready_for_contact()
        
        dashboard_data = {
            "stats": stats,
            "priority_leads": priority_leads[:10],
            "ready_for_contact": ready_leads[:5],
            "summary": {
                "total_active": stats.get("active_leads", 0),
                "high_priority": len([l for l in priority_leads if l.get("classification", {}).get("lead_type") == "CALIENTE"]),
                "with_contact": stats.get("with_complete_contact", 0),
                "conversion_rate": round(stats.get("conversion_rate", 0), 1)
            }
        }
        
        logger.info("Dashboard data retrieved", 
                   total_leads=stats.get("active_leads", 0))
        
        return {
            "success": True,
            "data": dashboard_data
        }
    
    except Exception as e:
        logger.error("Error getting dashboard data", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo datos del dashboard: {str(e)}"
        )
