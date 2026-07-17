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
  "wa_..." / "ig_..." / "web-..."  → Aura (guest)
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.core.observability.logging_config import get_logger
from app.utils.channel_utils import session_prefixes_for_role as _channel_prefixes_for_role

logger = get_logger(__name__)

# Display de cada rol en el backoffice. Los CANALES se derivan del catálogo de AgentSpec
# (Fase 2.2): una sola fuente de qué canal atiende cada rol; acá solo queda presentación.
_ROLE_DISPLAY = {
    "guest": {"name": "Aura",
              "description": "Concierge del huésped: pre-venta, post-venta y restaurante."},
    "management": {"name": "Asesor",
                   "description": "Consultor de gerencia: BI conversacional y recomendaciones."},
    "staff": {"name": "Operaciones",
              "description": "Empleado digital de operaciones: tickets e incidencias."},
}


def _seed_agents_from_specs() -> list:
    """Agentes de fábrica generados desde las AgentSpec (elimina la duplicación).

    Canales de un rol = unión de los channels de sus specs, en el orden de presentación
    histórico (whatsapp, web). Paridad byte a byte con el seed anterior:
    guest→[whatsapp, web], management→[whatsapp], staff→[whatsapp].
    """
    from app.domains.hotel.agent_specs import SPECS
    channels_by_role: dict = {}
    for spec in SPECS.values():
        channels_by_role.setdefault(spec.display_role, set()).update(spec.channels)
    seeds = []
    for role, display in _ROLE_DISPLAY.items():
        chans = [c for c in ("whatsapp", "web") if c in channels_by_role.get(role, {"whatsapp"})]
        seeds.append({"name": display["name"], "role": role,
                      "channels": chans, "description": display["description"]})
    return seeds


_SEED_AGENTS = _seed_agents_from_specs()


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
    return _channel_prefixes_for_role(role)


def agent_for_session(db: Session, session_id: Optional[str]) -> Optional[Agent]:
    """Devuelve el Agent al que pertenece una sesión (por su prefijo)."""
    role = role_for_session(session_id)
    return db.query(Agent).filter(Agent.role == role).first()
