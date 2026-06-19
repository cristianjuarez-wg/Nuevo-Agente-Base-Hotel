"""
Router para gestión de alertas proactivas
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from pydantic import BaseModel

from app.models.database import get_db
from app.services.alert_service import alert_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertUpdateRequest(BaseModel):
    """Request para actualizar una alerta"""
    alert_type: str
    is_enabled: bool
    sub_options: Dict = {}
    excluded_tours: List[int] = []


class BulkAlertUpdateRequest(BaseModel):
    """Request para actualizar múltiples alertas"""
    updates: List[AlertUpdateRequest]


@router.get("/definitions")
def get_alert_definitions():
    """Obtiene definiciones de todas las alertas disponibles"""
    try:
        definitions = alert_service.get_alert_definitions()
        return {
            "success": True,
            "definitions": definitions
        }
    except Exception as e:
        logger.error("Error getting alert definitions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings")
def get_alert_settings(db: Session = Depends(get_db)):
    """Obtiene todas las configuraciones de alertas"""
    try:
        settings = alert_service.get_all_settings(db)
        
        # Si no hay settings, inicializar por defecto
        if not settings:
            alert_service.initialize_default_settings(db)
            settings = alert_service.get_all_settings(db)
        
        return {
            "success": True,
            "settings": [s.to_dict() for s in settings]
        }
    except Exception as e:
        logger.error("Error getting alert settings", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/{alert_type}")
def get_alert_setting(alert_type: str, db: Session = Depends(get_db)):
    """Obtiene configuración de una alerta específica"""
    try:
        setting = alert_service.get_setting(alert_type, db)
        if not setting:
            return {
                "success": True,
                "setting": None
            }
        
        return {
            "success": True,
            "setting": setting.to_dict()
        }
    except Exception as e:
        logger.error("Error getting alert setting", alert_type=alert_type, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/{alert_type}")
def update_alert_setting(
    alert_type: str,
    request: AlertUpdateRequest,
    db: Session = Depends(get_db)
):
    """Actualiza configuración de una alerta"""
    try:
        setting = alert_service.update_setting(
            alert_type=alert_type,
            is_enabled=request.is_enabled,
            sub_options=request.sub_options,
            excluded_tours=request.excluded_tours,
            db=db
        )
        
        return {
            "success": True,
            "setting": setting.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error updating alert setting", alert_type=alert_type, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/bulk")
def bulk_update_alert_settings(
    request: BulkAlertUpdateRequest,
    db: Session = Depends(get_db)
):
    """Actualiza múltiples configuraciones de alertas"""
    try:
        updates = [u.dict() for u in request.updates]
        settings = alert_service.bulk_update_settings(updates, db)
        
        return {
            "success": True,
            "settings": [s.to_dict() for s in settings],
            "count": len(settings)
        }
    except Exception as e:
        logger.error("Error bulk updating alert settings", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize")
def initialize_default_settings(db: Session = Depends(get_db)):
    """Inicializa configuraciones por defecto"""
    try:
        alert_service.initialize_default_settings(db)
        settings = alert_service.get_all_settings(db)
        
        return {
            "success": True,
            "message": "Default settings initialized",
            "count": len(settings)
        }
    except Exception as e:
        logger.error("Error initializing default settings", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
