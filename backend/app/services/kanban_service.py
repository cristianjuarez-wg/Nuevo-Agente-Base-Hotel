"""
Servicio para gestión del Kanban de leads
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.models.lead import Lead
from app.core.logging_config import get_logger
from datetime import datetime

logger = get_logger(__name__)

class KanbanService:
    """Servicio para operaciones del Kanban"""
    
    VALID_STAGES = ["new", "contacted", "won", "lost"]
    
    def get_leads_by_stage(self, db: Session) -> Dict[str, List[Dict]]:
        """
        Obtiene todos los leads organizados por estado del kanban
        
        Returns:
            Dict con leads agrupados por estado
        """
        try:
            logger.info("Fetching leads for kanban board")
            
            # Obtener solo leads con nombre Y (email O teléfono)
            leads = db.query(Lead).filter(
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).order_by(desc(Lead.created_at)).all()
            
            # Organizar por estado
            leads_by_stage = {
                "new": [],
                "contacted": [],
                "won": [],
                "lost": []
            }
            
            for lead in leads:
                stage = lead.kanban_stage or "new"
                if stage in leads_by_stage:
                    leads_by_stage[stage].append(self._format_lead_card(lead))
            
            logger.info("Leads fetched successfully",
                       total=len(leads),
                       new=len(leads_by_stage["new"]),
                       contacted=len(leads_by_stage["contacted"]),
                       won=len(leads_by_stage["won"]),
                       lost=len(leads_by_stage["lost"]))
            
            return leads_by_stage
            
        except Exception as e:
            logger.error("Error fetching kanban leads", error=str(e))
            raise
    
    def _format_lead_card(self, lead: Lead) -> Dict:
        """Formatea un lead para mostrar en tarjeta del kanban"""
        return {
            "id": lead.id,
            "name": lead.name,
            "last_name": lead.last_name,
            "display_name": lead.get_display_name(),
            "email": lead.email,
            "phone": lead.phone,
            "main_interest": lead.main_interest,
            "lead_type": lead.lead_type,
            "interest_score": lead.interest_score,
            "priority_score": lead.get_priority_score(),
            "time_since_creation": lead.get_time_since_creation(),
            "has_contact": lead.is_complete_lead(),
            "contact_readiness": lead.contact_readiness,
            "kanban_stage": lead.kanban_stage,
            "created_at": lead.created_at.isoformat() if lead.created_at else None
        }
    
    def get_lead_detail(self, db: Session, lead_id: int) -> Optional[Dict]:
        """
        Obtiene el detalle completo de un lead
        
        Args:
            db: Sesión de base de datos
            lead_id: ID del lead
            
        Returns:
            Dict con información completa del lead o None si no existe
        """
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            
            if not lead:
                logger.warning("Lead not found", lead_id=lead_id)
                return None
            
            logger.info("Lead detail fetched", lead_id=lead_id)
            return lead.to_dict()
            
        except Exception as e:
            logger.error("Error fetching lead detail", lead_id=lead_id, error=str(e))
            raise
    
    def update_lead_stage(self, db: Session, lead_id: int, new_stage: str) -> bool:
        """
        Actualiza el estado del kanban de un lead
        
        Args:
            db: Sesión de base de datos
            lead_id: ID del lead
            new_stage: Nuevo estado (new, contacted, interested, won, lost)
            
        Returns:
            True si se actualizó correctamente
        """
        try:
            if new_stage not in self.VALID_STAGES:
                raise ValueError(f"Invalid stage: {new_stage}")
            
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            
            if not lead:
                logger.warning("Lead not found for update", lead_id=lead_id)
                return False
            
            old_stage = lead.kanban_stage
            lead.update_kanban_stage(new_stage)
            
            db.commit()
            
            logger.info("Lead stage updated",
                       lead_id=lead_id,
                       old_stage=old_stage,
                       new_stage=new_stage)
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error("Error updating lead stage",
                        lead_id=lead_id,
                        new_stage=new_stage,
                        error=str(e))
            raise
    
    def add_lead_note(self, db: Session, lead_id: int, note: str) -> bool:
        """
        Agrega una nota a un lead
        
        Args:
            db: Sesión de base de datos
            lead_id: ID del lead
            note: Texto de la nota
            
        Returns:
            True si se agregó correctamente
        """
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            
            if not lead:
                logger.warning("Lead not found for note", lead_id=lead_id)
                return False
            
            lead.add_note(note)
            db.commit()
            
            logger.info("Note added to lead", lead_id=lead_id)
            return True
            
        except Exception as e:
            db.rollback()
            logger.error("Error adding note to lead",
                        lead_id=lead_id,
                        error=str(e))
            raise
    
    def get_kanban_stats(self, db: Session) -> Dict:
        """
        Obtiene estadísticas del kanban
        
        Returns:
            Dict con estadísticas mejoradas
        """
        try:
            # ✅ CORREGIDO: Solo contar leads válidos (con nombre Y contacto)
            # Mismo filtro que get_leads_by_stage para que coincidan los números
            total_leads = db.query(func.count(Lead.id)).filter(
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).scalar()
            
            # Contar por estado (solo leads válidos)
            stage_counts = {}
            for stage in self.VALID_STAGES:
                count = db.query(func.count(Lead.id)).filter(
                    Lead.name.isnot(None),
                    ((Lead.email.isnot(None)) | (Lead.phone.isnot(None))),
                    Lead.kanban_stage == stage
                ).scalar()
                stage_counts[stage] = count
            
            # ✅ Leads activos (new + contacted) - CORREGIDO: eliminado "interested" que no existe
            active_leads = stage_counts.get("new", 0) + stage_counts.get("contacted", 0)
            
            # ✅ Leads cerrados (won + lost)
            closed_leads = stage_counts.get("won", 0) + stage_counts.get("lost", 0)
            
            # ✅ Conversión real: ventas ganadas / total de leads
            conversion_rate = 0
            if total_leads > 0:
                conversion_rate = round((stage_counts.get("won", 0) / total_leads) * 100, 1)
            
            # ✅ Tasa de éxito: ventas ganadas / leads cerrados
            success_rate = 0
            if closed_leads > 0:
                success_rate = round((stage_counts.get("won", 0) / closed_leads) * 100, 1)
            
            stats = {
                "total_leads": total_leads,
                "by_stage": stage_counts,
                "active_leads": active_leads,
                "closed_leads": closed_leads,
                "conversion_rate": conversion_rate,  # won / total (ej: 2/42 = 4.8%)
                "success_rate": success_rate  # won / cerrados (ej: 2/2 = 100%)
            }
            
            logger.info("Kanban stats calculated", 
                       total=total_leads,
                       active=active_leads,
                       closed=closed_leads,
                       conversion=conversion_rate,
                       success=success_rate)
            return stats
            
        except Exception as e:
            logger.error("Error calculating kanban stats", error=str(e))
            raise
    
    def search_leads(self, db: Session, query: str) -> List[Dict]:
        """
        Busca leads por nombre, email o interés
        
        Args:
            db: Sesión de base de datos
            query: Término de búsqueda
            
        Returns:
            Lista de leads que coinciden
        """
        try:
            search_term = f"%{query}%"
            
            leads = db.query(Lead).filter(
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None))),
                ((Lead.name.ilike(search_term)) |
                 (Lead.email.ilike(search_term)) |
                 (Lead.main_interest.ilike(search_term)))
            ).order_by(desc(Lead.created_at)).all()
            
            logger.info("Lead search completed",
                       query=query,
                       results=len(leads))
            
            return [self._format_lead_card(lead) for lead in leads]
            
        except Exception as e:
            logger.error("Error searching leads", query=query, error=str(e))
            raise
    
    def filter_leads_by_score(self, db: Session, min_score: int) -> List[Dict]:
        """
        Filtra leads por score mínimo
        
        Args:
            db: Sesión de base de datos
            min_score: Score mínimo
            
        Returns:
            Lista de leads filtrados
        """
        try:
            leads = db.query(Lead).filter(
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None))),
                Lead.interest_score >= min_score
            ).order_by(desc(Lead.interest_score)).all()
            
            logger.info("Leads filtered by score",
                       min_score=min_score,
                       results=len(leads))
            
            return [self._format_lead_card(lead) for lead in leads]
            
        except Exception as e:
            logger.error("Error filtering leads", error=str(e))
            raise

# Instancia global del servicio
kanban_service = KanbanService()
