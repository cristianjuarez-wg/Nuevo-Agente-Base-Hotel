"""
Configuración de ATENCIÓN HUMANA (singleton, fila id=1).

Define si el hotel tiene una persona disponible para tomar conversaciones en vivo (handoff del
agente a un humano), y cuándo. El agente solo OFRECE pasar con una persona si hay atención
disponible AHORA — no promete un handoff que nadie va a tomar.

Disponibilidad = enabled AND (on_call  OR  la hora local cae dentro de la franja de hoy).
  - enabled: interruptor maestro de la función.
  - on_call: "hay alguien de guardia ahora", sin importar la hora (override del horario).
  - schedule: por día de semana (0=lunes … 6=domingo) → {active, from, to} en "HH:MM".

Los horarios se interpretan en HORA LOCAL del negocio (BusinessProfile.timezone), vía now_business().
"""
from sqlalchemy import Column, Integer, Boolean, JSON, DateTime

from app.models.database import Base, engine
from app.utils.timezone_utils import utcnow_naive


def _default_schedule() -> dict:
    """Horario de fábrica: lun-vie 9-18, sáb/dom cerrado (0=lunes … 6=domingo)."""
    laboral = {"active": True, "from": "09:00", "to": "18:00"}
    cerrado = {"active": False, "from": "09:00", "to": "18:00"}
    return {str(d): dict(laboral) for d in range(5)} | {"5": dict(cerrado), "6": dict(cerrado)}


class HumanAttentionConfig(Base):
    """Config de atención humana para el handoff (fila única id=1)."""
    __tablename__ = "human_attention_config"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)   # interruptor maestro
    on_call = Column(Boolean, nullable=False, default=False)   # guardia: hay alguien AHORA
    schedule = Column(JSON, nullable=False, default=_default_schedule)  # {"0": {active,from,to}, ...}
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def to_dict(self):
        return {
            "id": self.id,
            "enabled": bool(self.enabled),
            "on_call": bool(self.on_call),
            "schedule": self.schedule or _default_schedule(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


Base.metadata.create_all(bind=engine, tables=[HumanAttentionConfig.__table__])
