"""
Router de Monitoreo de Vuelos
Endpoints para chequear estado de vuelos
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from app.models.database import get_db
from app.services.flight_monitor_service import FlightMonitorService
from app.core.logging_config import get_logger

# Importar modelos para que SQLAlchemy pueda resolver las relaciones
from app.models.postsale import PackageFlight, SoldPackage
from app.models.provider import Provider
from app.models.flight_tracking import FlightStatusTracking

logger = get_logger(__name__)

router = APIRouter(prefix="/api/flights", tags=["flight_monitoring"])

@router.get("/upcoming")
def get_upcoming_flights(
    hours: int = 48,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Obtiene vuelos próximos de paquetes activos
    
    Args:
        hours: Ventana de tiempo en horas (default 48h)
    """
    try:
        service = FlightMonitorService(db)
        flights = service.get_upcoming_flights(hours=hours)
        
        return {
            "flights": flights,
            "total": len(flights),
            "time_window": f"{hours} hours"
        }
        
    except Exception as e:
        logger.error("Error getting upcoming flights", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check/{flight_id}")
def check_flight(
    flight_id: int,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Chequea un vuelo específico
    
    Args:
        flight_id: ID del vuelo en package_flights
    """
    try:
        service = FlightMonitorService(db)
        result = service.check_flight_on_demand(flight_id)
        
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error checking flight", flight_id=flight_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-all")
def check_all_flights(db: Session = Depends(get_db)) -> Dict:
    """
    Chequea todos los vuelos próximos
    
    Llamado por el botón "Chequear Vuelos" en el frontend
    """
    try:
        service = FlightMonitorService(db)
        results = service.check_all_upcoming_flights()
        
        return results
        
    except Exception as e:
        logger.error("Error checking all flights", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{flight_id}")
def get_flight_history(
    flight_id: int,
    limit: int = 10,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Obtiene histórico de chequeos de un vuelo
    
    Args:
        flight_id: ID del vuelo
        limit: Número máximo de registros
    """
    try:
        from app.models.flight_tracking import FlightStatusTracking
        
        history = db.query(FlightStatusTracking).filter(
            FlightStatusTracking.flight_id == flight_id
        ).order_by(
            FlightStatusTracking.check_timestamp.desc()
        ).limit(limit).all()
        
        return {
            "flight_id": flight_id,
            "history": [h.to_dict() for h in history],
            "total": len(history)
        }
        
    except Exception as e:
        logger.error("Error getting flight history", flight_id=flight_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
