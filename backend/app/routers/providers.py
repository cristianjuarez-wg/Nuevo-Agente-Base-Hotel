"""
Router de Proveedores
Endpoints para gestión de proveedores turísticos
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.models.database import get_db
from app.services.provider_service import ProviderService
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/providers", tags=["providers"])


# ==================== Pydantic Models ====================

class ProviderCreate(BaseModel):
    code: str
    type: str
    name: str
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    whatsapp_country_code: Optional[str] = None
    whatsapp_number: Optional[str] = None
    operates_24_7: bool = False
    response_time: Optional[int] = None
    preferred_contact: str = "phone"
    notes: Optional[str] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    whatsapp_country_code: Optional[str] = None
    whatsapp_number: Optional[str] = None
    operates_24_7: Optional[bool] = None
    response_time: Optional[int] = None
    preferred_contact: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class ProviderContactLog(BaseModel):
    ticket_id: int
    contact_type: str  # call, whatsapp, email
    operator: str
    response_time: Optional[int] = None
    successful: bool = True
    notes: Optional[str] = None


# ==================== Endpoints ====================

@router.get("/")
def list_providers(
    provider_type: Optional[str] = Query(None, description="Filtrar por tipo: hotel, transfer, activity, airline"),
    country: Optional[str] = Query(None, description="Filtrar por país"),
    is_active: Optional[bool] = Query(True, description="Filtrar por activo/inactivo"),
    search: Optional[str] = Query(None, description="Buscar por nombre o código"),
    db: Session = Depends(get_db)
):
    """
    Listar proveedores con filtros
    
    - **provider_type**: hotel, transfer, activity, airline
    - **country**: Código o nombre del país
    - **is_active**: true/false
    - **search**: Buscar por nombre o código
    """
    try:
        service = ProviderService(db)
        
        filters = {
            "type": provider_type,
            "country": country,
            "is_active": is_active,
            "search": search
        }
        
        providers = service.list_providers(filters)
        
        logger.info("Providers listed",
                   count=len(providers),
                   filters=filters)
        
        return {
            "total": len(providers),
            "providers": [p.to_dict() for p in providers]
        }
        
    except Exception as e:
        logger.error("Error listing providers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
def search_providers(
    q: str = Query(..., description="Término de búsqueda"),
    provider_type: Optional[str] = Query(None, description="Filtrar por tipo"),
    db: Session = Depends(get_db)
):
    """
    Búsqueda rápida de proveedores por nombre o código
    
    - **q**: Término de búsqueda
    - **provider_type**: Filtrar por tipo (opcional)
    """
    try:
        service = ProviderService(db)
        providers = service.search_providers(q, provider_type)
        
        return {
            "results": [p.to_dict() for p in providers]
        }
        
    except Exception as e:
        logger.error("Error searching providers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}")
def get_provider(
    provider_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtener detalle completo de un proveedor
    
    Incluye: información básica, contactos, métricas
    """
    try:
        service = ProviderService(db)
        provider = service.get_provider(provider_id)
        
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        # Obtener datos completos
        result = provider.to_dict()
        
        # Agregar contactos
        result["contacts"] = [c.to_dict() for c in provider.contacts]
        
        # Agregar estadísticas
        result["stats"] = service.get_provider_stats(provider_id)
        
        logger.info("Provider retrieved", provider_id=provider_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting provider", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
def create_provider(
    provider_data: ProviderCreate,
    db: Session = Depends(get_db)
):
    """
    Crear nuevo proveedor
    
    Requiere: code, type, name
    """
    try:
        service = ProviderService(db)
        
        # Verificar que no exista el código
        existing = service.get_provider_by_code(provider_data.code)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Provider with code '{provider_data.code}' already exists"
            )
        
        provider = service.create_provider(provider_data.dict())
        
        logger.info("Provider created", provider_id=provider.id)
        
        return {
            "message": "Provider created successfully",
            "provider": provider.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating provider", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{provider_id}")
def update_provider(
    provider_id: int,
    provider_data: ProviderUpdate,
    db: Session = Depends(get_db)
):
    """
    Actualizar proveedor existente
    
    Solo se actualizan los campos enviados
    """
    try:
        service = ProviderService(db)
        
        # Filtrar campos None
        update_data = {k: v for k, v in provider_data.dict().items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data to update")
        
        provider = service.update_provider(provider_id, update_data)
        
        logger.info("Provider updated", provider_id=provider_id)
        
        return {
            "message": "Provider updated successfully",
            "provider": provider.to_dict()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error updating provider", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{provider_id}")
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db)
):
    """
    Desactivar proveedor (soft delete)
    
    No se elimina físicamente, solo se marca como inactivo
    """
    try:
        service = ProviderService(db)
        
        provider = service.update_provider(provider_id, {"is_active": False})
        
        logger.info("Provider deactivated", provider_id=provider_id)
        
        return {
            "message": "Provider deactivated successfully",
            "provider_id": provider_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error deactivating provider", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}/stats")
def get_provider_stats(
    provider_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtener estadísticas del proveedor
    
    Incluye: consultas, problemas, rating, tasa de issues
    """
    try:
        service = ProviderService(db)
        
        provider = service.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        stats = service.get_provider_stats(provider_id)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting provider stats", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider_id}/contact")
def log_provider_contact(
    provider_id: int,
    contact_data: ProviderContactLog,
    db: Session = Depends(get_db)
):
    """
    Registrar contacto con proveedor
    
    Usado cuando un operador contacta al proveedor
    """
    try:
        service = ProviderService(db)
        
        provider = service.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        service.log_provider_contact(
            provider_id=provider_id,
            ticket_id=contact_data.ticket_id,
            contact_type=contact_data.contact_type,
            operator=contact_data.operator,
            response_time=contact_data.response_time,
            successful=contact_data.successful,
            notes=contact_data.notes
        )
        
        # Actualizar métricas
        service.update_provider_metrics(provider_id)
        
        logger.info("Provider contact logged",
                   provider_id=provider_id,
                   ticket_id=contact_data.ticket_id)
        
        return {
            "message": "Contact logged successfully",
            "provider_id": provider_id,
            "ticket_id": contact_data.ticket_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error logging provider contact", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}/history")
def get_provider_history(
    provider_id: int,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Obtener historial de contactos con el proveedor
    
    - **limit**: Número máximo de registros (1-100)
    """
    try:
        service = ProviderService(db)
        
        provider = service.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        history = service.get_provider_contact_history(provider_id, limit)
        
        return {
            "provider_id": provider_id,
            "total": len(history),
            "history": [log.to_dict() for log in history]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting provider history", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider_id}/metrics/update")
def update_provider_metrics(
    provider_id: int,
    db: Session = Depends(get_db)
):
    """
    Actualizar métricas del proveedor manualmente
    
    Normalmente se actualizan automáticamente, pero este endpoint
    permite forzar una actualización
    """
    try:
        service = ProviderService(db)
        
        provider = service.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        service.update_provider_metrics(provider_id)
        
        # Obtener métricas actualizadas
        stats = service.get_provider_stats(provider_id)
        
        logger.info("Provider metrics updated manually", provider_id=provider_id)
        
        return {
            "message": "Metrics updated successfully",
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating provider metrics", provider_id=provider_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
