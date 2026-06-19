"""
Modelo de Mensajes de Conversación
Almacena el historial completo de mensajes (PRE-VENTA y POST-VENTA)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, Optional
from app.models.database import Base


class ConversationMessage(Base):
    """
    Mensaje individual en una conversación
    
    Vincula: conversation, lead (opcional), ticket (opcional)
    Contexto: pre_sale o post_sale
    """
    __tablename__ = "conversation_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Vinculación con conversación
    conversation_id = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    
    # Contenido del mensaje
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    
    # Orden y timestamp
    sequence_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Contexto
    context_type = Column(String(20), nullable=False)  # "pre_sale" | "post_sale"
    
    # Metadata opcional (para análisis)
    has_context = Column(Boolean, default=True)
    sources_used = Column(Integer, default=0)
    tokens_used = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    model_used = Column(String(50), nullable=True)
    
    # Vinculación a entidades (opcional)
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True, index=True)
    ticket_id = Column(Integer, nullable=True, index=True)  # ForeignKey a support_tickets si existe
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
    def to_dict(self) -> Dict:
        """Convierte el mensaje a diccionario"""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "context_type": self.context_type,
            "metadata": {
                "has_context": self.has_context,
                "sources_used": self.sources_used,
                "tokens_used": self.tokens_used,
                "response_time_ms": self.response_time_ms,
                "model_used": self.model_used
            },
            "lead_id": self.lead_id,
            "ticket_id": self.ticket_id
        }
    
    def is_user_message(self) -> bool:
        """Verifica si es un mensaje del usuario"""
        return self.role == "user"
    
    def is_agent_message(self) -> bool:
        """Verifica si es un mensaje del agente"""
        return self.role == "assistant"
    
    def get_preview(self, max_length: int = 100) -> str:
        """Obtiene un preview del contenido"""
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."
