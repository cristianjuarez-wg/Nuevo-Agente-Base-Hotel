"""
Configuración global del Centro de Empleados Digitales — el KILL SWITCH.

Fila única (id=1) con el interruptor `use_agent_config`: cuando está APAGADO,
toda la capa de configuración por agente (flujos, perillas, filtrado de tools)
se ignora y los agentes corren con su comportamiento hardcodeado actual — sin
deploy. Es el botón de emergencia de la Fase A (FLUJOS_Y_ESTRATEGIA.md §7).

Nace ENCENDIDO de fábrica: la paridad la garantizan los defaults (con valores
de fábrica el comportamiento es idéntico al actual), no el switch.
"""
from sqlalchemy import Column, Integer, Boolean, DateTime
from sqlalchemy.sql import func

from app.models.database import Base, engine


class CentroConfig(Base):
    __tablename__ = "centro_config"

    id = Column(Integer, primary_key=True)
    use_agent_config = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "use_agent_config": bool(self.use_agent_config),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que los demás modelos).
Base.metadata.create_all(bind=engine, tables=[CentroConfig.__table__])
