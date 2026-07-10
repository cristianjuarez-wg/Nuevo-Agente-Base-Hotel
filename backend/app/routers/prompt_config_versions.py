"""
Endpoints de VERSIONADO de la configuración de prompts del cliente (Fase 3.3).

GET  /api/prompt-config/versions        → lista de versiones (más nueva primero).
GET  /api/prompt-config/versions/active → la versión activa (o null).
POST /api/prompt-config/versions        → crea una versión con el estado actual (snapshot).
POST /api/prompt-config/versions/{id}/restore → rollback a esa versión.

Todo protegido con la auth de admin del backoffice.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import prompt_config_version_service as svc
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/prompt-config", tags=["PromptConfigVersions"])


class SaveVersionBody(BaseModel):
    label: Optional[str] = None
    activate: bool = True


@router.get("/versions", dependencies=[Depends(require_admin_key)])
def list_versions(db: Session = Depends(get_db)):
    return {"versions": svc.list_versions(db)}


@router.get("/versions/active", dependencies=[Depends(require_admin_key)])
def get_active(db: Session = Depends(get_db)):
    return {"active": svc.get_active(db)}


@router.post("/versions", dependencies=[Depends(require_admin_key)])
def save_version(body: SaveVersionBody,
                 authorization: Optional[str] = Header(default=None),
                 db: Session = Depends(get_db)):
    author = _author_from_token(authorization, db)
    return svc.save_version(db, author=author, label=body.label, activate=body.activate)


@router.post("/versions/{version_id}/restore", dependencies=[Depends(require_admin_key)])
def restore_version(version_id: int, db: Session = Depends(get_db)):
    try:
        return svc.restore_version(db, version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _author_from_token(authorization: Optional[str], db: Session) -> Optional[str]:
    """Mejor esfuerzo: si viene un JWT válido, usa el email del admin como autor."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        from app.core.security.auth import require_admin
        user = require_admin(authorization=authorization, db=db)
        return user.email
    except Exception:  # noqa: BLE001
        return None
