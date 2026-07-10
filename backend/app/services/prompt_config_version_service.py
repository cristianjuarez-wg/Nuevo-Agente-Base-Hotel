"""
Servicio de versionado de la configuración de prompts del cliente (Fase 3.3).

Captura un snapshot de TODO lo que el cliente edita y que afecta al prompt (training docs
activos + facts del negocio + flow variant), lo guarda como una versión, y permite activar una
versión previa (rollback). No cambia cómo el composer arma el prompt hoy: es una capa de
historial + reproducibilidad. Reconstruir la config al activar una versión es una operación
explícita (restore) para no sorprender.
"""
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models.prompt_config_version import PromptConfigVersion
from app.models.training_document import TrainingDocument
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


def _capture_payload(db: Session) -> dict:
    """Arma el snapshot del estado ACTUAL que afecta al prompt."""
    # Training docs activos (tono, política, objeciones, etc.) — lo que el cliente editó.
    docs = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.active == True)  # noqa: E712
        .order_by(TrainingDocument.id.asc())
        .all()
    )
    training = [
        {
            "agent_id": d.agent_id,
            "skill_id": d.skill_id,
            "title": d.title,
            "category": d.category,
            "data": d.data or {},
            "content": d.content,
            "is_default": d.is_default,
        }
        for d in docs
    ]
    # Facts + flow variant del BusinessProfile.
    facts, flow_variant = [], None
    try:
        from app.services import business_profile_service
        profile = business_profile_service.get_profile(db)
        facts = profile.get("facts", []) or []
        flow_variant = profile.get("flow_variant")
    except Exception:  # noqa: BLE001
        pass
    return {"training": training, "facts": facts, "flow_variant": flow_variant}


def save_version(db: Session, author: Optional[str] = None,
                 label: Optional[str] = None, activate: bool = True) -> dict:
    """Crea una versión nueva con el snapshot del estado actual. Si activate=True (default),
    la marca activa y desactiva las demás — es la 'foto' de lo que está corriendo ahora."""
    payload = _capture_payload(db)
    version = PromptConfigVersion(author=author, label=label, payload=payload, active=False)
    db.add(version)
    db.flush()
    if activate:
        _set_active(db, version.id)
    db.commit()
    db.refresh(version)
    logger.info("Prompt config version saved", version_id=version.id, active=version.active,
                training_docs=len(payload["training"]))
    return version.to_dict()


def list_versions(db: Session, limit: int = 50) -> List[dict]:
    rows = (
        db.query(PromptConfigVersion)
        .order_by(PromptConfigVersion.created_at.desc(), PromptConfigVersion.id.desc())
        .limit(limit)
        .all()
    )
    return [r.to_dict() for r in rows]


def get_active(db: Session) -> Optional[dict]:
    row = db.query(PromptConfigVersion).filter(
        PromptConfigVersion.active == True).first()  # noqa: E712
    return row.to_dict() if row else None


def _set_active(db: Session, version_id: int) -> None:
    """Marca una versión como la activa y desactiva el resto (a lo sumo una activa)."""
    db.query(PromptConfigVersion).filter(
        PromptConfigVersion.active == True).update(  # noqa: E712
        {"active": False}, synchronize_session=False)
    db.query(PromptConfigVersion).filter(
        PromptConfigVersion.id == version_id).update(
        {"active": True}, synchronize_session=False)


def restore_version(db: Session, version_id: int) -> dict:
    """Rollback: aplica el snapshot de una versión previa al estado en vivo y la marca activa.

    Reconstruye los TrainingDocument activos desde el payload (borra los activos actuales
    no-default y recrea los de la versión) y restaura facts/flow_variant en el BusinessProfile.
    """
    version = db.query(PromptConfigVersion).filter(
        PromptConfigVersion.id == version_id).first()
    if not version:
        raise ValueError(f"No existe la versión {version_id}")
    payload = version.payload or {}

    # 1) Restaurar training docs: desactivar los activos actuales (no-default) y recrear.
    db.query(TrainingDocument).filter(
        TrainingDocument.active == True,  # noqa: E712
        TrainingDocument.is_default == False,  # noqa: E712
    ).update({"active": False}, synchronize_session=False)
    for t in payload.get("training", []):
        if t.get("is_default"):
            continue  # los de fábrica ya existen; no se recrean
        db.add(TrainingDocument(
            agent_id=t.get("agent_id"), skill_id=t.get("skill_id"),
            title=t.get("title") or "restaurado", category=t.get("category"),
            data=t.get("data") or {}, content=t.get("content"),
            source="text", active=True, is_default=False,
        ))

    # 2) Restaurar facts / flow_variant.
    try:
        from app.services import business_profile_service
        business_profile_service.update_profile(db, {"facts": payload.get("facts", [])})
    except Exception:  # noqa: BLE001
        pass

    # 3) Marcar esta versión como activa.
    _set_active(db, version_id)
    db.commit()
    logger.info("Prompt config version restored", version_id=version_id)
    return version.to_dict()
