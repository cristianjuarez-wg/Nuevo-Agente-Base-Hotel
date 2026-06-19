"""
Modelos de Proveedores
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, DECIMAL, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict
from app.utils.timezone_utils import now_argentina
from app.models.database import Base


class Provider(Base):
    """Proveedor de servicios turísticos"""
    __tablename__ = "providers"
    
    id = Column(Integer, primary_key=True)
    provider_code = Column(String(50), unique=True, nullable=False)
    provider_type = Column(String(50), nullable=False)  # hotel, transfer, activity, airline
    provider_name = Column(String(200), nullable=False)
    
    # Ubicación
    country = Column(String(100))
    city = Column(String(100))
    address = Column(Text)
    timezone = Column(String(50))
    
    # Contacto Principal
    primary_phone_country_code = Column(String(5))
    primary_phone_number = Column(String(50))
    primary_email = Column(String(255))
    
    # WhatsApp
    whatsapp_country_code = Column(String(5))
    whatsapp_number = Column(String(50))
    
    # Operación
    operates_24_7 = Column(Boolean, default=False)
    response_time_minutes = Column(Integer)
    preferred_contact_method = Column(String(50))  # phone, whatsapp, email
    
    # Métricas (calculadas automáticamente)
    quality_rating = Column(DECIMAL(3,2), default=5.0)
    total_bookings = Column(Integer, default=0)
    total_issues = Column(Integer, default=0)
    total_consultations = Column(Integer, default=0)
    issue_rate = Column(DECIMAL(5,2), default=0.0)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_argentina)
    updated_at = Column(DateTime, default=now_argentina, onupdate=now_argentina)
    
    # Relationships
    contacts = relationship("ProviderContact", back_populates="provider", cascade="all, delete-orphan")
    interactions_log = relationship("ProviderInteractionLog", back_populates="provider")
    
    def to_dict(self) -> Dict:
        """Convertir a diccionario"""
        return {
            "id": self.id,
            "code": self.provider_code,
            "type": self.provider_type,
            "name": self.provider_name,
            "country": self.country,
            "city": self.city,
            "address": self.address,
            "timezone": self.timezone,
            "phone": self.get_formatted_phone(),
            "phone_raw": self.primary_phone_number,
            "phone_country_code": self.primary_phone_country_code,
            "email": self.primary_email,
            "whatsapp": self.get_formatted_whatsapp(),
            "whatsapp_raw": self.whatsapp_number,
            "whatsapp_country_code": self.whatsapp_country_code,
            "operates_24_7": self.operates_24_7,
            "response_time": self.response_time_minutes,
            "preferred_contact": self.preferred_contact_method,
            "rating": float(self.quality_rating) if self.quality_rating else 5.0,
            "total_bookings": self.total_bookings,
            "total_issues": self.total_issues,
            "total_consultations": self.total_consultations,
            "issue_rate": float(self.issue_rate) if self.issue_rate else 0.0,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_formatted_phone(self) -> str:
        """Obtener teléfono formateado"""
        if self.primary_phone_country_code and self.primary_phone_number:
            return f"{self.primary_phone_country_code} {self.primary_phone_number}"
        return None
    
    def get_formatted_whatsapp(self) -> str:
        """Obtener WhatsApp formateado (sin espacios para links)"""
        if self.whatsapp_country_code and self.whatsapp_number:
            # Remover espacios y caracteres especiales para WhatsApp links
            clean_number = self.whatsapp_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            return f"{self.whatsapp_country_code}{clean_number}"
        return None


class ProviderContact(Base):
    """Contacto adicional de un proveedor"""
    __tablename__ = "provider_contacts"
    
    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey('providers.id', ondelete='CASCADE'), nullable=False)
    contact_type = Column(String(50), nullable=False)  # emergency, reservations, billing, general
    contact_name = Column(String(200))
    contact_position = Column(String(100))
    
    # Contacto
    phone_country_code = Column(String(5))
    phone_number = Column(String(50))
    whatsapp_number = Column(String(50))
    email = Column(String(255))
    
    # Metadata
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_argentina)
    
    # Relationship
    provider = relationship("Provider", back_populates="contacts")
    
    def to_dict(self) -> Dict:
        """Convertir a diccionario"""
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "type": self.contact_type,
            "name": self.contact_name,
            "position": self.contact_position,
            "phone": f"{self.phone_country_code} {self.phone_number}" if self.phone_country_code else None,
            "whatsapp": self.whatsapp_number,
            "email": self.email,
            "is_primary": self.is_primary,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class ProviderInteractionLog(Base):
    """Log de interacciones con proveedores"""
    __tablename__ = "provider_interactions_log"
    
    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=False)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'))
    interaction_type = Column(String(50))  # call, whatsapp, email, consultation
    contacted_by = Column(String(100))  # operator name
    response_time_minutes = Column(Integer)
    was_successful = Column(Boolean)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_argentina)
    
    # Relationships
    provider = relationship("Provider", back_populates="interactions_log")
    
    def to_dict(self) -> Dict:
        """Convertir a diccionario"""
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "ticket_id": self.ticket_id,
            "type": self.interaction_type,
            "contacted_by": self.contacted_by,
            "response_time": self.response_time_minutes,
            "successful": self.was_successful,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
