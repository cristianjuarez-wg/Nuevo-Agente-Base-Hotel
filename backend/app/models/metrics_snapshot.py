"""
Modelo para almacenar snapshots de métricas para análisis de tendencias
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON
from app.models.database import Base
from datetime import datetime
from app.utils.timezone_utils import utcnow_naive

class MetricsSnapshot(Base):
    """Snapshot diario de métricas del sistema"""
    __tablename__ = "metrics_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime, default=utcnow_naive, index=True)
    period_type = Column(String(20), default="daily")  # daily, hourly, monthly
    
    # Métricas de conversaciones
    total_conversations = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    active_sessions = Column(Integer, default=0)
    avg_response_time = Column(Float, default=0.0)
    avg_conversation_duration = Column(Float, default=0.0)
    
    # Métricas de leads
    total_leads = Column(Integer, default=0)
    active_leads = Column(Integer, default=0)
    leads_calientes = Column(Integer, default=0)
    leads_tibios = Column(Integer, default=0)
    leads_frios = Column(Integer, default=0)
    leads_with_contact = Column(Integer, default=0)
    leads_ready_contact = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)
    
    # Métricas de contenido
    popular_destinations = Column(JSON, default=dict)
    
    # Metadata adicional
    extra_metadata = Column(JSON, default=dict)
    
    def to_dict(self):
        """Convierte el snapshot a diccionario"""
        return {
            "id": self.id,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "period_type": self.period_type,
            "conversations": {
                "total": self.total_conversations,
                "messages": self.total_messages,
                "active_sessions": self.active_sessions,
                "avg_response_time": self.avg_response_time,
                "avg_duration": self.avg_conversation_duration
            },
            "leads": {
                "total": self.total_leads,
                "active": self.active_leads,
                "by_type": {
                    "calientes": self.leads_calientes,
                    "tibios": self.leads_tibios,
                    "frios": self.leads_frios
                },
                "with_contact": self.leads_with_contact,
                "ready_contact": self.leads_ready_contact,
                "conversion_rate": self.conversion_rate
            },
            "content": {
                "popular_destinations": self.popular_destinations
            },
            "extra_metadata": self.extra_metadata
        }
