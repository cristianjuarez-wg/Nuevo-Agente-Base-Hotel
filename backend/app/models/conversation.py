"""
Modelo para tracking de conversaciones y sus timestamps
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.models.database import Base
from datetime import datetime

class Conversation(Base):
    """Registro de conversaciones para análisis temporal"""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), unique=True, index=True)
    
    # 🆕 Vinculación con Contact (NUEVO - VISIÓN 360°)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True, index=True)
    
    # 🆕 Resumen de la conversación (NUEVO - VISIÓN 360°)
    conversation_summary = Column(Text, nullable=True)
    
    # 🆕 Tipo de contexto (NUEVO - VISIÓN 360°)
    context_type = Column(String(20), default='pre_sale')  # "pre_sale" | "post_sale"

    # Canal de origen de la conversación: "web" | "whatsapp" (para analíticas por canal).
    channel = Column(String(20), nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_message_at = Column(DateTime, default=datetime.utcnow, index=True)
    ended_at = Column(DateTime, nullable=True)
    
    # Métricas
    message_count = Column(Integer, default=0)
    user_message_count = Column(Integer, default=0)
    agent_message_count = Column(Integer, default=0)
    avg_response_time = Column(Float, default=0.0)  # segundos
    total_duration = Column(Float, default=0.0)  # segundos
    
    # Contexto
    destinations_mentioned = Column(JSON, default=lambda: [])
    topics_discussed = Column(JSON, default=lambda: [])
    documents_consulted = Column(JSON, default=lambda: [])  # PDFs usados en respuestas
    packages_viewed = Column(JSON, default=lambda: [])  # Paquetes mencionados
    
    # Estado
    status = Column(String(50), default="active")  # active, completed, abandoned
    lead_generated = Column(Integer, default=0)  # 0 o 1
    
    # Metadata adicional
    extra_metadata = Column(JSON, default=lambda: {})

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    # 🆕 Relationships (NUEVO - VISIÓN 360°)
    contact = relationship("Contact", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan", lazy="dynamic")
    
    def update_message_count(self, is_user_message: bool = True):
        """Actualiza contadores de mensajes"""
        self.message_count += 1
        if is_user_message:
            self.user_message_count += 1
        else:
            self.agent_message_count += 1
        self.last_message_at = datetime.utcnow()
    
    def calculate_duration(self):
        """Calcula duración total de la conversación"""
        if self.started_at and self.last_message_at:
            self.total_duration = (self.last_message_at - self.started_at).total_seconds()
        return self.total_duration
    
    def add_destination(self, destination: str):
        """Agrega un destino mencionado"""
        if not self.destinations_mentioned:
            self.destinations_mentioned = []
        if destination not in self.destinations_mentioned:
            self.destinations_mentioned.append(destination)
    
    def add_document(self, document_name: str):
        """Agrega un documento consultado"""
        if not self.documents_consulted:
            self.documents_consulted = []
        if document_name not in self.documents_consulted:
            self.documents_consulted.append(document_name)
    
    def add_package(self, package_name: str):
        """Agrega un paquete visto"""
        if not self.packages_viewed:
            self.packages_viewed = []
        if package_name not in self.packages_viewed:
            self.packages_viewed.append(package_name)
    
    def to_dict(self):
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "message_count": self.message_count,
            "user_message_count": self.user_message_count,
            "agent_message_count": self.agent_message_count,
            "avg_response_time": self.avg_response_time,
            "total_duration": self.total_duration,
            "destinations_mentioned": self.destinations_mentioned or [],
            "topics_discussed": self.topics_discussed or [],
            "documents_consulted": self.documents_consulted or [],
            "packages_viewed": self.packages_viewed or [],
            "status": self.status,
            "lead_generated": self.lead_generated,
            "extra_metadata": self.extra_metadata or {}
        }
