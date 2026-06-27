"""
Router del "Centro del Empleado Digital" — agentes como entidad de primera clase.

  GET  /api/agents                     → lista de agentes (para el selector del legajo)
  GET  /api/agents/{id}                → identidad de un agente
  PUT  /api/agents/{id}                → editar identidad/estado (protegido X-Admin-Key)
  GET  /api/agents/{id}/performance    → legajo de desempeño + costo, por período

El desempeño se calcula on-demand (agent_performance_service) reusando
business_metrics y usage; no hay datos duplicados.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.agent import Agent
from app.services import agent_performance_service
from app.core.admin_auth import require_admin_key
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/agents", tags=["Agents"])


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None            # active | paused
    channels: Optional[List[str]] = None
    description: Optional[str] = None


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    """Todos los agentes, ordenados por id."""
    agents = db.query(Agent).order_by(Agent.id.asc()).all()
    return {"agents": [a.to_dict() for a in agents]}


@router.get("/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    return agent.to_dict()


@router.put("/{agent_id}", dependencies=[Depends(require_admin_key)])
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    """Edita la identidad/estado de un agente. El rol no se cambia desde acá (es estructural)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    if payload.name is not None:
        agent.name = payload.name.strip() or agent.name
    if payload.status is not None:
        if payload.status not in ("active", "paused"):
            raise HTTPException(400, "Estado inválido. Usar 'active' o 'paused'.")
        agent.status = payload.status
    if payload.channels is not None:
        agent.channels = payload.channels
    if payload.description is not None:
        agent.description = payload.description.strip() or None
    db.commit()
    db.refresh(agent)
    logger.info("Agent updated", id=agent.id, status=agent.status)
    return agent.to_dict()


@router.get("/{agent_id}/performance")
def get_performance(agent_id: int, period: str = "mes", db: Session = Depends(get_db)):
    """Legajo de desempeño + costo de IA del agente, para el período pedido."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    return agent_performance_service.get_agent_performance(db, agent, period=period)
