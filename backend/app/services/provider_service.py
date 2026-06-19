"""
Servicio de Gestión de Proveedores
"""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime
from app.models.provider import Provider, ProviderContact, ProviderInteractionLog
from app.models.postsale import TicketInteraction
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ProviderService:
    """Servicio para gestionar proveedores"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== CRUD Operations ====================
    
    def create_provider(self, provider_data: dict) -> Provider:
        """Crear nuevo proveedor"""
        try:
            provider = Provider(
                provider_code=provider_data["code"],
                provider_type=provider_data["type"],
                provider_name=provider_data["name"],
                country=provider_data.get("country"),
                city=provider_data.get("city"),
                address=provider_data.get("address"),
                timezone=provider_data.get("timezone"),
                primary_phone_country_code=provider_data.get("phone_country_code"),
                primary_phone_number=provider_data.get("phone_number"),
                primary_email=provider_data.get("email"),
                whatsapp_country_code=provider_data.get("whatsapp_country_code"),
                whatsapp_number=provider_data.get("whatsapp_number"),
                operates_24_7=provider_data.get("operates_24_7", False),
                response_time_minutes=provider_data.get("response_time"),
                preferred_contact_method=provider_data.get("preferred_contact", "phone"),
                notes=provider_data.get("notes")
            )
            
            self.db.add(provider)
            self.db.commit()
            self.db.refresh(provider)
            
            logger.info("Provider created", provider_id=provider.id, name=provider.provider_name)
            return provider
            
        except Exception as e:
            self.db.rollback()
            logger.error("Error creating provider", error=str(e))
            raise
    
    def get_provider(self, provider_id: int) -> Optional[Provider]:
        """Obtener proveedor por ID"""
        return self.db.query(Provider).filter(Provider.id == provider_id).first()
    
    def get_provider_by_code(self, code: str) -> Optional[Provider]:
        """Obtener proveedor por código"""
        return self.db.query(Provider).filter(Provider.provider_code == code).first()
    
    def update_provider(self, provider_id: int, data: dict) -> Provider:
        """Actualizar proveedor"""
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider {provider_id} not found")
        
        # Actualizar campos
        for key, value in data.items():
            if hasattr(provider, key):
                setattr(provider, key, value)
        
        provider.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(provider)
        
        logger.info("Provider updated", provider_id=provider_id)
        return provider
    
    def list_providers(self, filters: dict = None) -> List[Provider]:
        """Listar proveedores con filtros"""
        query = self.db.query(Provider)
        
        if filters:
            if filters.get("type"):
                query = query.filter(Provider.provider_type == filters["type"])
            
            if filters.get("country"):
                query = query.filter(Provider.country == filters["country"])
            
            if filters.get("is_active") is not None:
                query = query.filter(Provider.is_active == filters["is_active"])
            
            if filters.get("search"):
                search = f"%{filters['search']}%"
                query = query.filter(
                    (Provider.provider_name.ilike(search)) |
                    (Provider.provider_code.ilike(search))
                )
        
        return query.order_by(Provider.provider_name).all()
    
    # ==================== Búsqueda ====================
    
    def search_providers(self, query: str, provider_type: str = None) -> List[Provider]:
        """Búsqueda por nombre/código"""
        search = f"%{query}%"
        q = self.db.query(Provider).filter(
            (Provider.provider_name.ilike(search)) |
            (Provider.provider_code.ilike(search))
        )
        
        if provider_type:
            q = q.filter(Provider.provider_type == provider_type)
        
        return q.filter(Provider.is_active == True).limit(10).all()
    
    # ==================== Métricas ====================
    
    def update_provider_metrics(self, provider_id: int):
        """Actualizar métricas del proveedor"""
        provider = self.get_provider(provider_id)
        if not provider:
            return
        
        # Contar consultas (interactions auto-resueltas)
        consultations = self.db.query(TicketInteraction).filter(
            TicketInteraction.provider_id == provider_id,
            TicketInteraction.auto_resolved == True
        ).count()
        
        # Contar problemas (interactions escaladas)
        issues = self.db.query(TicketInteraction).filter(
            TicketInteraction.provider_id == provider_id,
            TicketInteraction.requires_escalation == True
        ).count()
        
        # Calcular tasa de problemas
        total = consultations + issues
        issue_rate = (issues / total * 100) if total > 0 else 0
        
        # Calcular rating (5.0 - issue_rate/20)
        quality_rating = max(1.0, 5.0 - (issue_rate / 20))
        
        # Actualizar
        provider.total_consultations = consultations
        provider.total_issues = issues
        provider.issue_rate = issue_rate
        provider.quality_rating = quality_rating
        provider.updated_at = datetime.utcnow()
        
        self.db.commit()
        
        logger.info("Provider metrics updated",
                   provider_id=provider_id,
                   consultations=consultations,
                   issues=issues,
                   rating=quality_rating)
    
    def get_provider_stats(self, provider_id: int) -> dict:
        """Obtener estadísticas del proveedor"""
        provider = self.get_provider(provider_id)
        if not provider:
            return {}
        
        return {
            "provider_id": provider_id,
            "name": provider.provider_name,
            "type": provider.provider_type,
            "total_consultations": provider.total_consultations,
            "total_issues": provider.total_issues,
            "issue_rate": float(provider.issue_rate) if provider.issue_rate else 0.0,
            "quality_rating": float(provider.quality_rating) if provider.quality_rating else 5.0,
            "response_time_avg": provider.response_time_minutes,
            "operates_24_7": provider.operates_24_7
        }
    
    # ==================== Contacto ====================
    
    def log_provider_contact(self, provider_id: int, ticket_id: int, 
                            contact_type: str, operator: str, 
                            response_time: int = None, successful: bool = True,
                            notes: str = None):
        """Registrar contacto con proveedor"""
        log = ProviderInteractionLog(
            provider_id=provider_id,
            ticket_id=ticket_id,
            interaction_type=contact_type,
            contacted_by=operator,
            response_time_minutes=response_time,
            was_successful=successful,
            notes=notes
        )
        
        self.db.add(log)
        self.db.commit()
        
        logger.info("Provider contact logged",
                   provider_id=provider_id,
                   ticket_id=ticket_id,
                   type=contact_type)
    
    def get_provider_contact_history(self, provider_id: int, limit: int = 50) -> List[ProviderInteractionLog]:
        """Obtener historial de contactos"""
        return self.db.query(ProviderInteractionLog).filter(
            ProviderInteractionLog.provider_id == provider_id
        ).order_by(ProviderInteractionLog.created_at.desc()).limit(limit).all()
