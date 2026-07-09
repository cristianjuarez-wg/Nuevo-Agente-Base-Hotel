"""
Modelo de Contacto - Vista 360° del Cliente
Unifica información de PRE-VENTA y POST-VENTA
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, Optional
from app.models.database import Base


class Contact(Base):
    """
    Contacto unificado (Lead o Cliente)
    
    Identificador principal: phone_number (normalizado)
    Vincula: conversations, leads, sold_packages
    """
    __tablename__ = "contacts"
    
    # ID principal
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identificadores naturales (CRÍTICO: normalización)
    phone_number = Column(String(50), unique=True, nullable=False, index=True)
    phone_country_code = Column(String(5), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    
    # Información personal
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    
    # Timestamps
    first_contact_date = Column(DateTime, default=datetime.utcnow, index=True)
    last_interaction_date = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Métricas agregadas (actualizadas automáticamente)
    total_conversations = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    leads_generated = Column(Integer, default=0)
    purchases_made = Column(Integer, default=0)
    tickets_created = Column(Integer, default=0)
    
    # Resumen IA
    ai_summary = Column(Text, nullable=True)
    last_summary_update = Column(DateTime, nullable=True)
    
    # Estado y clasificación
    contact_type = Column(String(20), default='lead')  # 'lead', 'customer', 'both'
    is_active = Column(Boolean, default=True)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    # Perfil extensible del huésped (gustos, servicios usados, familia, tags) como JSON.
    # Se persiste sobre TEXT (ver migración) y se serializa con json.dumps/loads.
    preferences = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships (se definirán cuando se importen los otros modelos)
    conversations = relationship("Conversation", back_populates="contact", lazy="dynamic")
    leads = relationship("Lead", back_populates="contact", lazy="dynamic")
    
    def to_dict(self) -> Dict:
        """Convierte el contacto a diccionario"""
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "phone_country_code": self.phone_country_code,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name or self.get_display_name(),
            "first_contact_date": self.first_contact_date.isoformat() if self.first_contact_date else None,
            "last_interaction_date": self.last_interaction_date.isoformat() if self.last_interaction_date else None,
            "metrics": {
                "total_conversations": self.total_conversations,
                "total_messages": self.total_messages,
                "leads_generated": self.leads_generated,
                "purchases_made": self.purchases_made,
                "tickets_created": self.tickets_created
            },
            "ai_summary": self.ai_summary,
            "last_summary_update": self.last_summary_update.isoformat() if self.last_summary_update else None,
            "contact_type": self.contact_type,
            "is_active": self.is_active
        }
    
    def get_display_name(self) -> str:
        """Obtiene el nombre para mostrar"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.email:
            return self.email.split('@')[0]
        else:
            return f"Contacto #{self.id}"
    
    def update_full_name(self):
        """Actualiza el campo full_name calculado"""
        self.full_name = self.get_display_name()
    
    def increment_conversations(self):
        """Incrementa contador de conversaciones"""
        self.total_conversations += 1
        self.last_interaction_date = datetime.utcnow()
    
    def increment_messages(self, count: int = 1):
        """Incrementa contador de mensajes"""
        self.total_messages += count
        self.last_interaction_date = datetime.utcnow()
    
    def increment_leads(self):
        """Incrementa contador de leads"""
        self.leads_generated += 1
        self.last_interaction_date = datetime.utcnow()
        
        # Actualizar tipo si es necesario
        if self.contact_type == 'customer':
            self.contact_type = 'both'
        elif not self.contact_type or self.contact_type == '':
            self.contact_type = 'lead'
    
    def increment_purchases(self):
        """Incrementa contador de compras"""
        self.purchases_made += 1
        self.last_interaction_date = datetime.utcnow()
        
        # Actualizar tipo: si compró, es cliente
        self.contact_type = 'customer'
    
    def increment_tickets(self):
        """Incrementa contador de tickets"""
        self.tickets_created += 1
        self.last_interaction_date = datetime.utcnow()
    
    def needs_summary_update(self) -> bool:
        """
        Verifica si necesita actualizar el resumen IA
        
        Criterios:
        - Nunca tuvo resumen
        - Hace más de 7 días del último resumen Y hubo actividad
        """
        if not self.ai_summary or not self.last_summary_update:
            return True
        
        days_since_summary = (datetime.utcnow() - self.last_summary_update).days
        if days_since_summary >= 7 and self.last_interaction_date > self.last_summary_update:
            return True
        
        return False
