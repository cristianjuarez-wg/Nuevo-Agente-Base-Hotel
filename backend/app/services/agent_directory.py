"""
Directorio de agentes: seed de los agentes existentes + atribución sesión → agente.

Hoy hay 3 agentes "virtuales" (roles) que este módulo formaliza como filas de la
tabla `agents`:
  - Aura (role=guest)        → atiende huésped por web y WhatsApp (pre + post venta)
  - Asesor (role=management) → consultor de gerencia (owner)
  - Operaciones (role=staff) → empleado digital de operaciones

La ATRIBUCIÓN de lo que ocurre a un agente se hace SIN migrar esquema: se lee el
prefijo del `session_id` (asignado en agent_router.py), evitando agregar una FK
`agent_id` hasta que una feature concreta lo pida (CENTRO_EMPLEADO_DIGITAL.md §8).

  session_id            → agente
  "owner_..."           → Asesor (management)
  "staff_..."           → Operaciones (staff)
  "wa_..." / "web-..."  → Aura (guest)
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

# Definición de los agentes "de fábrica" del hotel. role es el atributo de identidad.
_SEED_AGENTS = [
    {"name": "Aura", "role": "guest", "channels": ["whatsapp", "web"],
     "description": "Concierge del huésped: pre-venta, post-venta y restaurante."},
    {"name": "Asesor", "role": "management", "channels": ["whatsapp"],
     "description": "Consultor de gerencia: BI conversacional y recomendaciones."},
    {"name": "Operaciones", "role": "staff", "channels": ["whatsapp"],
     "description": "Empleado digital de operaciones: tickets e incidencias."},
]


def seed_agents(db: Session) -> None:
    """Da de alta los agentes de fábrica si no existen (idempotente).

    Se llama en el startup. No duplica: si ya hay un agente con ese `role`, lo deja.
    """
    try:
        for spec in _SEED_AGENTS:
            exists = db.query(Agent).filter(Agent.role == spec["role"]).first()
            if exists:
                continue
            db.add(Agent(
                name=spec["name"],
                role=spec["role"],
                status="active",
                channels=spec["channels"],
                description=spec["description"],
            ))
        db.commit()
    except Exception as e:  # noqa: BLE001
        # Un fallo del seed no debe impedir el arranque.
        logger.warning("No se pudo sembrar la tabla de agentes", error=str(e))
        db.rollback()


def role_for_session(session_id: Optional[str]) -> str:
    """Deduce el rol del agente a partir del prefijo del session_id."""
    sid = session_id or ""
    if sid.startswith("owner_"):
        return "management"
    if sid.startswith("staff_"):
        return "staff"
    # "wa_" (huésped por WhatsApp) y "web-" (huésped por web) → Aura.
    return "guest"


def session_prefixes_for_role(role: str) -> list[str]:
    """Prefijos de session_id que pertenecen a un rol (para filtrar consumo/métricas)."""
    if role == "management":
        return ["owner_"]
    if role == "staff":
        return ["staff_"]
    # guest: WhatsApp del huésped (wa_) + web (web-).
    return ["wa_", "web-", "web_"]


def agent_for_session(db: Session, session_id: Optional[str]) -> Optional[Agent]:
    """Devuelve el Agent al que pertenece una sesión (por su prefijo)."""
    role = role_for_session(session_id)
    return db.query(Agent).filter(Agent.role == role).first()
