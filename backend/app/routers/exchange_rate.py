"""
Router del tipo de cambio USD → ARS.

  GET /api/exchange-rate  → cotización vigente + configuración (backoffice y público)
  PUT /api/exchange-rate  → actualiza modo (auto/manual) y/o el valor manual
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import exchange_rate_service
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/exchange-rate", tags=["ExchangeRate"])


class ExchangeRateUpdate(BaseModel):
    mode: Optional[str] = None                       # "auto" | "manual"
    manual_rate: Optional[float] = Field(default=None, ge=0)


@router.get("")
def get_exchange_rate(db: Session = Depends(get_db)):
    """Cotización vigente + configuración persistida."""
    current = exchange_rate_service.get_current_rate(db)
    config = exchange_rate_service.get_config(db)
    return {"current": current, "config": config.to_dict()}


@router.put("", dependencies=[Depends(require_admin_key)])
def update_exchange_rate(payload: ExchangeRateUpdate, db: Session = Depends(get_db)):
    """Actualiza el modo y/o el valor manual de la cotización.

    Acción CRÍTICA (afecta todos los precios): protegida por X-Admin-Key."""
    config = exchange_rate_service.get_config(db)

    data = payload.model_dump(exclude_unset=True)
    if "mode" in data and data["mode"] is not None:
        if data["mode"] not in ("auto", "manual"):
            raise HTTPException(400, "Modo inválido. Usar 'auto' o 'manual'.")
        config.mode = data["mode"]
    if "manual_rate" in data:
        config.manual_rate = data["manual_rate"]

    db.commit()
    db.refresh(config)
    exchange_rate_service.invalidate_cache()

    logger.info("Exchange rate config updated", mode=config.mode, manual_rate=config.manual_rate)
    current = exchange_rate_service.get_current_rate(db)
    return {"current": current, "config": config.to_dict()}
