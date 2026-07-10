"""
Endpoints de la IDENTIDAD del negocio (Fase 1).

GET  /api/business-profile        → perfil completo (para el backoffice).
PUT  /api/business-profile        → actualiza la identidad (acción de admin).
GET  /api/public/business-profile → subset seguro para la landing pública (sin auth).
"""
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import business_profile_service
from app.core.admin_auth import require_admin_key
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["BusinessProfile"])


class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    brand_line: Optional[str] = None
    vertical: Optional[str] = None
    agent_display_name: Optional[str] = None
    role_descriptor: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    language: Optional[str] = None
    dialect_style: Optional[str] = None
    city: Optional[str] = None
    region_line: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    primary_currency: Optional[str] = None
    secondary_currency: Optional[str] = None
    facts: Optional[List[str]] = None


@router.get("/business-profile")
async def get_business_profile(db: Session = Depends(get_db)):
    """Perfil completo de identidad del negocio (backoffice)."""
    return business_profile_service.get_profile(db)


@router.put("/business-profile", dependencies=[Depends(require_admin_key)])
async def update_business_profile(payload: BusinessProfileUpdate, db: Session = Depends(get_db)):
    """Actualiza la identidad. Solo envía los campos a cambiar (exclude_unset)."""
    data = payload.model_dump(exclude_unset=True)
    updated = business_profile_service.update_profile(db, data)
    logger.info("BusinessProfile actualizado", fields=list(data.keys()))
    return updated


@router.get("/public/business-profile")
async def get_public_business_profile(db: Session = Depends(get_db)):
    """Subset SEGURO para la landing pública (sin datos internos ni auth)."""
    p = business_profile_service.get_profile(db)
    return {
        "business_name": p.get("business_name"),
        "brand_line": p.get("brand_line"),
        "agent_display_name": p.get("agent_display_name"),
        "city": p.get("city"),
        "region_line": p.get("region_line"),
        "language": p.get("language"),
        "primary_currency": p.get("primary_currency"),
        "secondary_currency": p.get("secondary_currency"),
    }
