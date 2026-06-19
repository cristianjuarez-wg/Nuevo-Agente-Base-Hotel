"""
Router para el módulo de Auto-Aprendizaje del agente
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from app.models.database import get_db
from app.services.learning_service import learning_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/learning", tags=["auto-learning"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    max_conversations: int = Field(30, ge=5, le=100)
    force: bool = False


class RejectRequest(BaseModel):
    reason: str = ""


class EvaluateRequest(BaseModel):
    result: str = Field(..., pattern="^(satisfactory|unsatisfactory)$")
    notes: str = ""


class RollbackRequest(BaseModel):
    reason: str = "Rollback manual por el operador"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/audit")
async def trigger_audit(request: AuditRequest, db: Session = Depends(get_db)):
    """Dispara una auditoría de conversaciones para detectar oportunidades de mejora"""
    try:
        result = await learning_service.audit_conversations(
            db=db,
            max_conversations=request.max_conversations,
            force=request.force,
        )
        return result
    except Exception as e:
        logger.error("Error en auditoría", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities")
def list_opportunities(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Lista las oportunidades de mejora detectadas. Filtrar por status opcional."""
    try:
        opportunities = learning_service.get_opportunities(db, status=status, limit=limit, offset=offset)
        return {
            "success": True,
            "opportunities": [o.to_dict() for o in opportunities],
            "total": len(opportunities),
        }
    except Exception as e:
        logger.error("Error listando oportunidades", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    """Obtiene el detalle completo de una oportunidad"""
    opp = learning_service.get_opportunity(db, opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    return {"success": True, "opportunity": opp.to_dict()}


@router.post("/opportunities/{opportunity_id}/approve")
def approve_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    """Aprueba una oportunidad para su implementación"""
    try:
        opp = learning_service.approve_opportunity(db, opportunity_id)
        return {"success": True, "opportunity": opp.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error aprobando oportunidad", opportunity_id=opportunity_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opportunities/{opportunity_id}/reject")
def reject_opportunity(opportunity_id: int, request: RejectRequest, db: Session = Depends(get_db)):
    """Rechaza una oportunidad con razón opcional"""
    try:
        opp = learning_service.reject_opportunity(db, opportunity_id, reason=request.reason)
        return {"success": True, "opportunity": opp.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error rechazando oportunidad", opportunity_id=opportunity_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opportunities/{opportunity_id}/implement")
def implement_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    """Implementa una oportunidad aprobada. Crea snapshot automático de respaldo."""
    try:
        result = learning_service.implement_opportunity(db, opportunity_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error implementando oportunidad", opportunity_id=opportunity_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opportunities/{opportunity_id}/evaluate")
def evaluate_opportunity(opportunity_id: int, request: EvaluateRequest, db: Session = Depends(get_db)):
    """Evalúa el resultado de una implementación. Si es insatisfactorio, hace rollback automático."""
    try:
        result = learning_service.evaluate_implementation(
            db,
            opportunity_id,
            evaluation_result=request.result,
            notes=request.notes,
        )
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error evaluando oportunidad", opportunity_id=opportunity_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opportunities/{opportunity_id}/rollback")
def rollback_opportunity(opportunity_id: int, request: RollbackRequest, db: Session = Depends(get_db)):
    """Revierte una implementación usando el snapshot de respaldo"""
    try:
        result = learning_service.rollback_implementation(db, opportunity_id, reason=request.reason)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error en rollback", opportunity_id=opportunity_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots")
def list_snapshots(limit: int = 30, db: Session = Depends(get_db)):
    """Lista los snapshots de respaldo disponibles"""
    try:
        snapshots = learning_service.get_snapshots(db, limit=limit)
        return {
            "success": True,
            "snapshots": [s.to_dict() for s in snapshots],
            "total": len(snapshots),
        }
    except Exception as e:
        logger.error("Error listando snapshots", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
