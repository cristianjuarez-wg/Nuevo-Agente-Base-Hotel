"""
Configuración del tipo de cambio USD → ARS (singleton, fila id=1).

El precio de las habitaciones se guarda en USD (fuente de verdad) y el ARS se
calcula al vuelo con la cotización vigente. El operador elige desde el backoffice
si la cotización es automática (dólar oficial venta, vía dolarapi) o manual (un
valor fijo). Si la API automática falla, se usa la última cotización cacheada;
si nunca hubo, el DEFAULT_RATE.
"""
from datetime import datetime

from sqlalchemy import Column, Integer, Float, String, DateTime

from app.models.database import Base, engine
from app.utils.timezone_utils import utcnow_naive

# Fallback final si el modo es auto, la API falla y nunca hubo cache.
DEFAULT_RATE = 1050.0


class ExchangeRateConfig(Base):
    """Configuración de cotización USD→ARS (fila única id=1)."""
    __tablename__ = "exchange_rate_config"

    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String, nullable=False, default="auto")   # "auto" | "manual"
    manual_rate = Column(Float, nullable=True)              # valor fijo cuando mode="manual"
    cached_rate = Column(Float, nullable=True)              # última cotización automática exitosa
    cached_at = Column(DateTime, nullable=True)            # cuándo se cacheó
    source = Column(String, nullable=True)                # etiqueta de la fuente
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def to_dict(self):
        return {
            "id": self.id,
            "mode": self.mode,
            "manual_rate": self.manual_rate,
            "cached_rate": self.cached_rate,
            "cached_at": self.cached_at.isoformat() if self.cached_at else None,
            "source": self.source,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


Base.metadata.create_all(bind=engine, tables=[ExchangeRateConfig.__table__])
