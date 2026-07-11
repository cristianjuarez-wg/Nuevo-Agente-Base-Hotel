"""
Router de ATENCIÓN HUMANA (handoff del agente a una persona).

  GET /api/human-attention  → config + si hay atención disponible AHORA (para el backoffice)
  PUT /api/human-attention  → actualiza enabled / on_call (guardia) / horario (protegido)
"""
from typing import Optional, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import human_attention_service
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/human-attention", tags=["HumanAttention"])


class HumanAttentionUpdate(BaseModel):
    enabled: Optional[bool] = None
    on_call: Optional[bool] = None
    schedule: Optional[Dict] = None   # {"0": {active,from,to}, ...} (0=lunes … 6=domingo)


@router.get("")
def get_human_attention(db: Session = Depends(get_db)):
    """Config de atención humana + disponibilidad actual (calculada en hora local del negocio)."""
    cfg = human_attention_service.get_config(db)
    return {"config": cfg.to_dict(), "available_now": human_attention_service.is_human_available(db)}


@router.put("", dependencies=[Depends(require_admin_key)])
def update_human_attention(payload: HumanAttentionUpdate, db: Session = Depends(get_db)):
    """Actualiza la config de atención humana (solo campos presentes)."""
    data = payload.model_dump(exclude_unset=True)
    updated = human_attention_service.update_config(db, data)
    return {"config": updated, "available_now": human_attention_service.is_human_available(db)}
