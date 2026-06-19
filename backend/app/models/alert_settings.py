"""
Modelo para configuración de alertas proactivas
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from .database import Base

class AlertSettings(Base):
    """Configuración de alertas proactivas del sistema"""
    __tablename__ = "alert_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(50), nullable=False, unique=True)  # ej: "welcome_voucher"
    category = Column(String(50), nullable=False)  # pre_trip, during_trip, post_trip, operational, emergency
    is_enabled = Column(Boolean, default=False)
    sub_options = Column(JSON, default=dict)  # Opciones granulares
    excluded_tours = Column(JSON, default=list)  # IDs de tours excluidos
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "category": self.category,
            "is_enabled": self.is_enabled,
            "sub_options": self.sub_options or {},
            "excluded_tours": self.excluded_tours or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
