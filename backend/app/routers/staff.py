"""
Router de administración del EQUIPO del hotel (backoffice).

CRUD de StaffMember: personal y dueño con su rol. El agente de WhatsApp usa estos
registros para distinguir quién escribe (huésped / staff / dueño) y rutear al agente
correcto. El teléfono se guarda normalizado (mismo formato que Contact.phone_number).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.staff import StaffMember
from app.utils.phone_normalizer import normalize_phone, phones_match
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/staff", tags=["Staff"])

_VALID_ROLES = {"owner", "staff"}
_VALID_AREAS = {"mantenimiento", "recepcion", "housekeeping", "general"}


def _find_duplicate(db: Session, phone: str, exclude_id: Optional[int] = None):
    """Devuelve un StaffMember cuyo teléfono coincide (tolerante al "9"), o None."""
    members = db.query(StaffMember).all()
    for m in members:
        if exclude_id is not None and m.id == exclude_id:
            continue
        if phones_match(m.phone, phone):
            return m
    return None


class StaffPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=6, max_length=50)
    role: str = Field("staff")
    area: str = Field("general")  # mantenimiento | recepcion | housekeeping | general
    active: bool = True


class StatusUpdate(BaseModel):
    active: bool


@router.get("")
def list_staff(db: Session = Depends(get_db)):
    """Lista todo el equipo (owner + staff), ordenado por rol y nombre."""
    members = (
        db.query(StaffMember)
        .order_by(StaffMember.role.asc(), StaffMember.name.asc())
        .all()
    )
    return {"staff": [m.to_dict() for m in members]}


@router.post("")
def create_staff(payload: StaffPayload, db: Session = Depends(get_db)):
    """Da de alta un miembro del equipo. Normaliza el teléfono y valida el rol."""
    role = payload.role if payload.role in _VALID_ROLES else "staff"
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Teléfono inválido.")
    # Duplicado tolerante: el mismo número con/sin el "9" no debe entrar dos veces.
    dup = _find_duplicate(db, phone)
    if dup:
        raise HTTPException(
            status_code=409,
            detail=f"Ese número ya está cargado como «{dup.name}».",
        )
    area = payload.area if payload.area in _VALID_AREAS else "general"
    member = StaffMember(name=payload.name.strip(), phone=phone, role=role, area=area, active=payload.active)
    db.add(member)
    db.commit()
    db.refresh(member)
    logger.info("Staff member created", id=member.id, role=role)
    return {"staff": member.to_dict()}


@router.put("/{member_id}")
def update_staff(member_id: int, payload: StaffPayload, db: Session = Depends(get_db)):
    """Edita un miembro del equipo."""
    member = db.query(StaffMember).filter(StaffMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Miembro no encontrado.")
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Teléfono inválido.")
    # Otro miembro con el mismo teléfono (tolerante al "9") → conflicto.
    dup = _find_duplicate(db, phone, exclude_id=member_id)
    if dup:
        raise HTTPException(
            status_code=409,
            detail=f"Ese número ya está cargado como «{dup.name}».",
        )
    member.name = payload.name.strip()
    member.phone = phone
    member.role = payload.role if payload.role in _VALID_ROLES else member.role
    member.area = payload.area if payload.area in _VALID_AREAS else member.area
    member.active = payload.active
    db.commit()
    db.refresh(member)
    return {"staff": member.to_dict()}


@router.patch("/{member_id}/status")
def set_staff_status(member_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    """Activa/desactiva un miembro sin borrarlo (un inactivo se trata como huésped)."""
    member = db.query(StaffMember).filter(StaffMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Miembro no encontrado.")
    member.active = payload.active
    db.commit()
    return {"staff": member.to_dict()}


@router.delete("/{member_id}")
def delete_staff(member_id: int, db: Session = Depends(get_db)):
    """Elimina un miembro del equipo."""
    member = db.query(StaffMember).filter(StaffMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Miembro no encontrado.")
    db.delete(member)
    db.commit()
    return {"success": True, "message": f"Miembro {member_id} eliminado"}
