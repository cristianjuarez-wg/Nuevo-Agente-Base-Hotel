"""
Router de DATOS DE DEMOSTRACIÓN (control desde el backoffice).

  GET  /api/demo/status    → conteos de datos demo actuales
  POST /api/demo/populate  → regenera el dataset demo (limpia lo demo y crea fresco)
  POST /api/demo/clear     → borra solo los datos demo

Todo opera sobre registros marcados is_demo=True; nunca toca datos reales ni la config.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import demo_data_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/demo", tags=["Demo"])


@router.get("/status")
def demo_status(db: Session = Depends(get_db)):
    """Cuántos registros demo hay hoy."""
    return demo_data_service.counts(db)


@router.post("/populate")
def demo_populate(db: Session = Depends(get_db)):
    """Regenera el dataset demo (limpia lo demo previo y crea uno fresco con fechas de hoy)."""
    try:
        created = demo_data_service.populate(db)
        return {"ok": True, "created": created}
    except Exception as e:
        logger.error("Demo populate failed", error=str(e))
        raise HTTPException(500, f"No se pudo generar la demo: {e}")


@router.post("/clear")
def demo_clear(db: Session = Depends(get_db)):
    """Borra solo los datos marcados como demo."""
    try:
        deleted = demo_data_service.clear(db)
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        logger.error("Demo clear failed", error=str(e))
        raise HTTPException(500, f"No se pudo limpiar la demo: {e}")
