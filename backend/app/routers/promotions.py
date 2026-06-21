"""
Router de PROMOCIONES del hotel (Fase 3).

CRUD completo para que el cliente gestione promociones y ofertas desde el backoffice.
Cada alta/edición/baja re-ingesta el vector store en caliente (promotions_service),
para que el agente las conozca vía RAG y también vía la tool determinística
`promos_vigentes`.
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.promotions import Promotion
from app.services import promotions_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/promotions", tags=["Promotions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PromotionPayload(BaseModel):
    name: str
    description: str
    conditions: Optional[str] = None
    discount_type: Optional[str] = "other"   # "percentage" | "free_night" | "other"
    discount_value: Optional[float] = None
    min_nights: Optional[int] = None         # estadía mínima para que aplique
    status: Optional[str] = "active"
    valid_from: Optional[str] = None         # ISO string YYYY-MM-DD o YYYY-MM-DDTHH:MM
    valid_until: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str  # "active" | "inactive"


def _parse_date(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    raise HTTPException(400, f"Formato de fecha inválido: '{val}'. Usar YYYY-MM-DD.")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("/")
async def list_promotions(db: Session = Depends(get_db)):
    """Lista todas las promociones (backoffice: incluye inactivas)."""
    promos = db.query(Promotion).order_by(Promotion.created_at.desc()).all()
    return {"promotions": [p.to_dict() for p in promos], "total": len(promos)}


@router.post("/")
async def create_promotion(payload: PromotionPayload, db: Session = Depends(get_db)):
    """Crea una promoción y la re-ingesta al vector store."""
    promo = Promotion(
        name=payload.name.strip(),
        description=payload.description.strip(),
        conditions=(payload.conditions or "").strip() or None,
        discount_type=payload.discount_type or "other",
        discount_value=payload.discount_value,
        min_nights=payload.min_nights,
        status=payload.status or "active",
        valid_from=_parse_date(payload.valid_from),
        valid_until=_parse_date(payload.valid_until),
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    await promotions_service.reingest(promo)
    logger.info("Promotion created", id=promo.id, name=promo.name)
    return promo.to_dict()


@router.put("/{promo_id}")
async def update_promotion(
    promo_id: int, payload: PromotionPayload, db: Session = Depends(get_db)
):
    """Actualiza una promoción y re-ingesta al vector store."""
    promo = db.query(Promotion).filter(Promotion.id == promo_id).first()
    if not promo:
        raise HTTPException(404, "Promoción no encontrada.")

    promo.name = payload.name.strip()
    promo.description = payload.description.strip()
    promo.conditions = (payload.conditions or "").strip() or None
    promo.discount_type = payload.discount_type or "other"
    promo.discount_value = payload.discount_value
    promo.min_nights = payload.min_nights
    promo.status = payload.status or promo.status
    promo.valid_from = _parse_date(payload.valid_from)
    promo.valid_until = _parse_date(payload.valid_until)
    promo.updated_at = datetime.now()

    db.commit()
    db.refresh(promo)
    await promotions_service.reingest(promo)
    logger.info("Promotion updated", id=promo.id, name=promo.name)
    return promo.to_dict()


@router.patch("/{promo_id}/status")
async def update_status(
    promo_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
):
    """Activa o desactiva una promoción."""
    if payload.status not in ("active", "inactive"):
        raise HTTPException(400, "Estado inválido. Usar 'active' o 'inactive'.")
    promo = db.query(Promotion).filter(Promotion.id == promo_id).first()
    if not promo:
        raise HTTPException(404, "Promoción no encontrada.")

    promo.status = payload.status
    promo.updated_at = datetime.now()
    db.commit()
    db.refresh(promo)
    await promotions_service.reingest(promo)
    logger.info("Promotion status updated", id=promo.id, status=promo.status)
    return promo.to_dict()


@router.delete("/{promo_id}")
async def delete_promotion(promo_id: int, db: Session = Depends(get_db)):
    """Elimina una promoción y la quita del vector store."""
    promo = db.query(Promotion).filter(Promotion.id == promo_id).first()
    if not promo:
        raise HTTPException(404, "Promoción no encontrada.")

    await promotions_service.remove_from_index(promo)
    db.delete(promo)
    db.commit()
    logger.info("Promotion deleted", id=promo_id)
    return {"deleted": True, "id": promo_id}
