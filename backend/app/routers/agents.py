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
from app.models.staff import StaffMember
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


# ── Parte de fin de día (Etapa 2) ────────────────────────────────────────────

class DailyReportConfig(BaseModel):
    enabled: bool = False
    recipient_staff_ids: List[int] = []


def _get_agent_or_404(db: Session, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    return agent


@router.get("/{agent_id}/daily-report")
def get_daily_report(agent_id: int, db: Session = Depends(get_db)):
    """Texto del parte de HOY (calculado on-demand) + la config de envío vigente.

    Siempre disponible: el parte se muestra aunque el envío automático esté apagado.
    """
    agent = _get_agent_or_404(db, agent_id)
    text = agent_performance_service.build_daily_report(db, agent)
    cfg = agent.daily_report or {"enabled": False, "recipient_staff_ids": []}
    return {"text": text, "config": cfg}


@router.put("/{agent_id}/daily-report/config", dependencies=[Depends(require_admin_key)])
def update_daily_report_config(agent_id: int, payload: DailyReportConfig, db: Session = Depends(get_db)):
    """Guarda la config opt-in del parte: activo/inactivo + destinatarios del staff."""
    agent = _get_agent_or_404(db, agent_id)
    # Validar que los destinatarios existan en el equipo.
    valid_ids = []
    for sid in payload.recipient_staff_ids:
        if db.query(StaffMember.id).filter(StaffMember.id == sid).first():
            valid_ids.append(sid)
    agent.daily_report = {"enabled": bool(payload.enabled), "recipient_staff_ids": valid_ids}
    db.commit()
    db.refresh(agent)
    logger.info("Daily report config updated", agent=agent.name, enabled=agent.daily_report["enabled"])
    return agent.daily_report


@router.post("/{agent_id}/daily-report/send", dependencies=[Depends(require_admin_key)])
def send_daily_report_now(agent_id: int, db: Session = Depends(get_db)):
    """Envía el parte AHORA a los destinatarios configurados (disparo manual).

    Funciona aunque el envío automático esté desactivado: el botón manual es independiente.
    Si no hay destinatarios configurados, devuelve 409 para que el frontend lo avise.
    """
    agent = _get_agent_or_404(db, agent_id)
    cfg = agent.daily_report or {}
    staff_ids = cfg.get("recipient_staff_ids") or []
    if not staff_ids:
        raise HTTPException(409, "No hay destinatarios configurados. Configurá el envío primero.")
    return agent_performance_service.send_daily_report(db, agent, staff_ids)


@router.post("/cron/daily-report", dependencies=[Depends(require_admin_key)])
def cron_daily_report(db: Session = Depends(get_db)):
    """Para un cron externo (Render Cron Job / ping): envía el parte de cada agente con
    el envío automático ACTIVADO a sus destinatarios. (El cron real se programa aparte.)"""
    results = []
    agents = db.query(Agent).all()
    for agent in agents:
        cfg = agent.daily_report or {}
        if not cfg.get("enabled"):
            continue
        staff_ids = cfg.get("recipient_staff_ids") or []
        if not staff_ids:
            continue
        results.append(agent_performance_service.send_daily_report(db, agent, staff_ids))
    return {"agents_sent": len(results), "results": results}
