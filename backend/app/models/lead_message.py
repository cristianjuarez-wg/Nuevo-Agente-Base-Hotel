"""
Modelo para almacenar mensajes de conversación de leads
Basado en TicketInteraction de post-venta
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.database import Base
from datetime import datetime
from app.utils.timezone_utils import utcnow_naive

class LeadMessage(Base):
    """Mensajes de conversación entre usuario y agente para leads"""
    __tablename__ = "lead_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    
    # Tipo de mensaje
    type = Column(String(50), nullable=False)  # user_message, agent_response
    
    # Contenido
    message = Column(Text, nullable=False)
    
    # Metadata
    created_by = Column(String(255), nullable=False)  # Nombre del usuario o "Agente IA"
    created_at = Column(DateTime, default=utcnow_naive, index=True)
    sequence_number = Column(Integer, nullable=False)  # Orden del mensaje en la conversación
    
    def to_dict(self):
        """Convierte a diccionario (mismo formato que TicketInteraction)"""
        return {
            "id": self.id,
            "type": self.type,
            "message": self.message,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sequence_number": self.sequence_number
        }
