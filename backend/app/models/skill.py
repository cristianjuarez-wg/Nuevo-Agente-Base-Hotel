"""
Skills y políticas — el modelo de tres capas del Centro (CENTRO_EMPLEADO_DIGITAL.md §2.5/§6).

  Skill       = PLANTILLA de capacidad (horizontal). Define QUÉ parámetros existen
                (`parameter_schema`) y sus TECHOS DUROS (`parameter_limits`).
  AgentSkill  = INSTANCIA. Asigna una skill a un agente con SUS valores
                (`policy_values`), validados y recortados al techo server-side.

Invariante de seguridad (§2.5): `AgentSkill.policy_values` NUNCA puede superar
`Skill.parameter_limits`. El servidor valida y recorta — el cliente configura
dentro de un corral. No es configuración: es regla estructural del modelo.

Formato de `parameter_schema` (lista de parámetros):
  [{"key": "presupuesto_max_por_dia", "label": "Presupuesto máx por día (USD)",
    "type": "number", "default": 50}, ...]
  type ∈ number | percent | text | bool
Formato de `parameter_limits` (techos por key, opcional):
  {"presupuesto_max_por_dia": {"ceiling": 100}}
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from datetime import datetime

from app.models.database import Base, engine


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(60), nullable=False, unique=True, index=True)   # "coordinar_transfer"
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    # kind: "function" (adosable, con toggle on/off) | "flow" (flujo principal del rol:
    # NO se apaga — solo se configura; el apagado global es el kill switch del Centro).
    kind = Column(String(20), nullable=False, default="function")
    vertical = Column(String(40), nullable=False, default="core")        # core | hotel | clinica | ...
    parameter_schema = Column(JSON, nullable=True, default=list)         # qué parámetros existen
    parameter_limits = Column(JSON, nullable=True, default=dict)         # techos duros (no editables)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.now)
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "kind": self.kind or "function",
            "vertical": self.vertical,
            "parameter_schema": self.parameter_schema or [],
            "parameter_limits": self.parameter_limits or {},
            "is_active": self.is_active,
        }


class AgentSkill(Base):
    __tablename__ = "agent_skills"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    skill_id = Column(Integer, nullable=False, index=True)
    policy_values = Column(JSON, nullable=True, default=dict)   # valores del agente (recortados al techo)
    enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.now)
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "skill_id": self.skill_id,
            "policy_values": self.policy_values or {},
            "enabled": self.enabled,
        }


# Crear las tablas de forma explícita (mismo patrón que los demás modelos del hotel).
Base.metadata.create_all(bind=engine, tables=[Skill.__table__, AgentSkill.__table__])
