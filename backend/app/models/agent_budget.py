"""
Modelo de configuración de topes de gasto del agente.

Fila única (singleton, id=1) con los límites de gasto en USD que el operador
configura desde el backoffice. Cuando el gasto acumulado (hoy o este mes) supera
el límite activo, el agente deja de llamar a OpenAI (ver usage_service).

Un límite en `None` significa "sin tope" para ese período.
"""
from sqlalchemy import Column, Integer, Float, Boolean, DateTime
from sqlalchemy.sql import func

from app.models.database import Base


class AgentBudgetConfig(Base):
    """Topes de gasto del agente (fila única id=1)."""
    __tablename__ = "agent_budget_config"

    id = Column(Integer, primary_key=True, index=True)
    daily_limit_usd = Column(Float, nullable=True)    # None = sin tope diario
    monthly_limit_usd = Column(Float, nullable=True)  # None = sin tope mensual
    enabled = Column(Boolean, default=False)          # master switch del enforcement
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "daily_limit_usd": self.daily_limit_usd,
            "monthly_limit_usd": self.monthly_limit_usd,
            "enabled": bool(self.enabled),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
