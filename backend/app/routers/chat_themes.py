"""
Router de TEMAS VISUALES del chat (Fase 4).

Expone dos grupos de endpoints:
  GET  /api/chat/theme           — tema activo HOY (usado por el widget público)
  GET  /api/chat-themes/         — lista todos (backoffice)
  POST /api/chat-themes/         — crear tema
  PUT  /api/chat-themes/{id}     — editar tema
  PATCH /api/chat-themes/{id}/status — activar/desactivar/pinear
  DELETE /api/chat-themes/{id}   — eliminar tema

Lógica de activación (por prioridad):
  1. Si hay un tema con status="pinned" → ese siempre gana.
  2. Si hay temas con status="active" → elige el que coincida con hoy (mes/día dentro del rango).
  3. Ninguno → devuelve null (el widget usa sus colores default).

El rango puede cruzar el año nuevo (ej: dic-10 → ene-10):
  se detecta comparando active_from > active_until y se aplica lógica de wrap-around.
"""
from typing import Optional
from datetime import datetime
from app.utils.timezone_utils import utcnow_naive

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.chat_theme import ChatTheme
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

# Dos prefijos en el mismo router
router = APIRouter(tags=["ChatThemes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ThemePayload(BaseModel):
    name: str
    emoji: Optional[str] = None
    description: Optional[str] = None
    active_from_month: Optional[int] = None
    active_from_day: Optional[int] = None
    active_until_month: Optional[int] = None
    active_until_day: Optional[int] = None
    header_bg: Optional[str] = None
    header_text: Optional[str] = None
    accent_color: Optional[str] = None
    bubble_bg: Optional[str] = None
    fab_bg: Optional[str] = None
    fab_text: Optional[str] = None
    effect: Optional[str] = "none"     # "none" | "snow" | "snow_gold" | "leaves" | "bunny"
    status: Optional[str] = "active"   # "active" | "pinned" | "inactive"


class StatusUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Lógica de selección del tema activo
# ---------------------------------------------------------------------------
def _in_range(theme: ChatTheme, today: datetime) -> bool:
    """True si hoy cae dentro del rango mes/día del tema."""
    fm, fd = theme.active_from_month, theme.active_from_day
    um, ud = theme.active_until_month, theme.active_until_day

    # Si no tiene rango definido, está activo siempre que el status sea active/pinned.
    if not all([fm, fd, um, ud]):
        return True

    # Comparamos como (mes, día) enteros
    start = (fm, fd)
    end = (um, ud)
    now = (today.month, today.day)

    if start <= end:
        # Rango dentro del mismo año (ej: 07-01 → 08-31)
        return start <= now <= end
    else:
        # Rango cruza el año nuevo (ej: 12-01 → 01-15)
        return now >= start or now <= end


def get_active_theme(db: Session) -> Optional[ChatTheme]:
    today = datetime.now()  # hora de pared local: el rango del tema es (mes, día), no UTC

    # Prioridad 1: pinned (ignoramos fechas — el cliente lo activó manualmente)
    pinned = db.query(ChatTheme).filter(ChatTheme.status == "pinned").first()
    if pinned:
        return pinned

    # Prioridad 2: active + dentro del rango de fechas
    candidates = db.query(ChatTheme).filter(ChatTheme.status == "active").all()
    for t in candidates:
        if _in_range(t, today):
            return t

    return None


# ---------------------------------------------------------------------------
# Endpoint público del widget
# ---------------------------------------------------------------------------
@router.get("/api/chat/theme")
def current_theme(db: Session = Depends(get_db)):
    """Devuelve el tema visual activo hoy (o null si no hay ninguno)."""
    theme = get_active_theme(db)
    return {"theme": theme.to_dict() if theme else None}


# ---------------------------------------------------------------------------
# CRUD backoffice
# ---------------------------------------------------------------------------
def _deactivate_others(db: Session, keep_id) -> None:
    """Desactiva todos los temas excepto `keep_id` (solo uno habilitado a la vez)."""
    query = db.query(ChatTheme)
    if keep_id is not None:
        query = query.filter(ChatTheme.id != keep_id)
    for other in query.all():
        if other.status != "inactive":
            other.status = "inactive"
            other.updated_at = utcnow_naive()


@router.get("/api/chat-themes/", dependencies=[Depends(require_admin_key)])
def list_themes(db: Session = Depends(get_db)):
    themes = db.query(ChatTheme).order_by(ChatTheme.created_at.desc()).all()
    return {"themes": [t.to_dict() for t in themes], "total": len(themes)}


@router.post("/api/chat-themes/", dependencies=[Depends(require_admin_key)])
def create_theme(payload: ThemePayload, db: Session = Depends(get_db)):
    theme = ChatTheme(**payload.model_dump())
    # Si nace activo o fijado, desactiva al resto.
    if theme.status in ("active", "pinned"):
        _deactivate_others(db, keep_id=None)
    db.add(theme)
    db.commit()
    db.refresh(theme)
    logger.info("ChatTheme created", id=theme.id, name=theme.name)
    return theme.to_dict()


@router.put("/api/chat-themes/{theme_id}", dependencies=[Depends(require_admin_key)])
def update_theme(theme_id: int, payload: ThemePayload, db: Session = Depends(get_db)):
    t = db.query(ChatTheme).filter(ChatTheme.id == theme_id).first()
    if not t:
        raise HTTPException(404, "Tema no encontrado.")
    for field, val in payload.model_dump().items():
        setattr(t, field, val)
    # Si quedó activo o fijado, desactiva al resto.
    if t.status in ("active", "pinned"):
        _deactivate_others(db, keep_id=theme_id)
    t.updated_at = utcnow_naive()
    db.commit()
    db.refresh(t)
    logger.info("ChatTheme updated", id=t.id)
    return t.to_dict()


@router.patch("/api/chat-themes/{theme_id}/status", dependencies=[Depends(require_admin_key)])
def update_status(theme_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    if payload.status not in ("active", "pinned", "inactive"):
        raise HTTPException(400, "Estado inválido.")
    t = db.query(ChatTheme).filter(ChatTheme.id == theme_id).first()
    if not t:
        raise HTTPException(404, "Tema no encontrado.")

    # Solo puede haber UN tema habilitado a la vez: al activar o fijar uno,
    # el resto pasa a inactivo automáticamente.
    if payload.status in ("active", "pinned"):
        _deactivate_others(db, keep_id=theme_id)

    t.status = payload.status
    t.updated_at = utcnow_naive()
    db.commit()
    db.refresh(t)
    return t.to_dict()


@router.delete("/api/chat-themes/{theme_id}", dependencies=[Depends(require_admin_key)])
def delete_theme(theme_id: int, db: Session = Depends(get_db)):
    t = db.query(ChatTheme).filter(ChatTheme.id == theme_id).first()
    if not t:
        raise HTTPException(404, "Tema no encontrado.")
    db.delete(t)
    db.commit()
    logger.info("ChatTheme deleted", id=theme_id)
    return {"deleted": True, "id": theme_id}
