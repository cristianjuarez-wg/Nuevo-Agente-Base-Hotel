"""
Router de consumo de tokens / costo USD del agente y configuración de topes.

Sin auth, consistente con el resto del backoffice actual. Importar este módulo
(vía include_router en main.py) también registra el modelo AgentBudgetConfig y
asegura la creación de su tabla por Base.metadata.create_all.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.agent_budget import AgentBudgetConfig  # noqa: F401 (registra la tabla)
from app.services import usage_service
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/usage", tags=["Usage"])


class BudgetConfigUpdate(BaseModel):
    """Payload para actualizar los topes de gasto. Campos opcionales."""
    daily_limit_usd: Optional[float] = Field(default=None, ge=0)
    monthly_limit_usd: Optional[float] = Field(default=None, ge=0)
    enabled: Optional[bool] = None


@router.get("/summary")
async def get_summary(db: Session = Depends(get_db)):
    """Resumen de consumo (tokens y USD) de hoy y del mes, con desglose por modelo."""
    try:
        return usage_service.get_usage_summary(db)
    except Exception as e:
        logger.error("Error getting usage summary", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo consumo: {str(e)}")


@router.get("/config")
async def get_config(db: Session = Depends(get_db)):
    """Configuración actual de topes de gasto."""
    try:
        return usage_service.get_budget_config(db).to_dict()
    except Exception as e:
        logger.error("Error getting budget config", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo configuración: {str(e)}")


@router.put("/config", dependencies=[Depends(require_admin_key)])
async def update_config(payload: BudgetConfigUpdate, db: Session = Depends(get_db)):
    """Actualiza los topes de gasto (diario / mensual) y el switch de enforcement.

    Acción CRÍTICA: protegida por X-Admin-Key (si hay ADMIN_KEY configurada)."""
    try:
        config = usage_service.get_budget_config(db)

        data = payload.model_dump(exclude_unset=True)
        if "daily_limit_usd" in data:
            config.daily_limit_usd = data["daily_limit_usd"]
        if "monthly_limit_usd" in data:
            config.monthly_limit_usd = data["monthly_limit_usd"]
        if "enabled" in data and data["enabled"] is not None:
            config.enabled = data["enabled"]

        db.commit()
        db.refresh(config)

        # Forzar recalcular el enforcement en el próximo mensaje.
        usage_service.invalidate_budget_cache()

        logger.info("Budget config updated",
                    daily=config.daily_limit_usd,
                    monthly=config.monthly_limit_usd,
                    enabled=config.enabled)
        return config.to_dict()
    except Exception as e:
        db.rollback()
        logger.error("Error updating budget config", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error actualizando configuración: {str(e)}")
