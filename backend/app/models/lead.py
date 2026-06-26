"""
Modelos de datos para el sistema de leads
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from app.models.database import Base
from typing import Dict, Optional
from app.utils.timezone_utils import now_argentina, iso_argentina

class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    
    # 🆕 Vinculación con Contact (NUEVO - VISIÓN 360°)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True, index=True)
    
    # Canal de origen del lead: "whatsapp" | "web". Se deriva del session_id al crear.
    channel = Column(String(20), nullable=True)
    # Preparatorias para distinguir leads generados por humanos (teléfono/mostrador) a
    # futuro. Hoy todo lead lo genera Aura; no se setean aún.
    generated_by = Column(String(20), nullable=True)   # default conceptual: "aura"
    created_by = Column(String(120), nullable=True)    # autor humano (futuro)

    # Información de contacto
    name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    
    # Clasificación del lead
    lead_type = Column(String(20), nullable=False)  # CALIENTE, TIBIO, FRIO
    interest_score = Column(Integer, nullable=False)  # 1-10
    obstacle = Column(String(50), nullable=True)  # precio, fechas, tiempo, etc.
    contact_readiness = Column(Boolean, default=False)
    
    # Interés en viajes
    main_interest = Column(String(500), nullable=True)  # Destino principal
    secondary_interests = Column(JSON, nullable=True)  # Lista de otros destinos
    travel_context = Column(Text, nullable=True)  # Contexto completo de la conversación
    
    # Metadatos
    created_at = Column(DateTime, default=now_argentina)
    updated_at = Column(DateTime, default=now_argentina, onupdate=now_argentina)
    status = Column(String(20), default="active")  # active, contacted, converted, inactive

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    # Kanban fields
    kanban_stage = Column(String(20), default="new")  # new, contacted, won, lost
    notes = Column(Text, nullable=True)  # Notas del vendedor
    last_status_change = Column(DateTime, default=now_argentina)  # Última vez que cambió de estado
    
    # Análisis adicional
    suggested_response_tone = Column(String(50), nullable=True)
    next_action = Column(String(100), nullable=True)
    reasoning = Column(Text, nullable=True)
    
    # 🆕 Campos para eventos temporales
    event_name = Column(String(200), nullable=True)  # "Formula 1", "Mundial 2026"
    event_type = Column(String(100), nullable=True)  # "sporting_event", "festival"
    event_countries = Column(Text, nullable=True)  # JSON string de países
    event_year = Column(String(10), nullable=True)  # "2025", "2026"
    is_event_lead = Column(Boolean, default=False)  # Flag para identificar
    
    # 🆕 Relationship (NUEVO - VISIÓN 360°)
    contact = relationship("Contact", back_populates="leads")
    # Bitácora de actividad del lead (seguimiento humano + acciones de Aura).
    events = relationship("LeadEvent", back_populates="lead",
                          cascade="all, delete-orphan", order_by="LeadEvent.created_at")

    def origin(self) -> Dict:
        """Origen unificado del lead (mismo vocabulario que las reservas)."""
        from app.core.origin import origin_from_channel
        return origin_from_channel(self.channel, self.generated_by or "aura")

    def to_dict(self) -> Dict:
        """Convierte el lead a diccionario"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "contact_info": {
                "name": self.name,
                "last_name": self.last_name,
                "phone": self.phone,
                "email": self.email
            },
            "classification": {
                "lead_type": self.lead_type,
                "interest_score": self.interest_score,
                "obstacle": self.obstacle,
                "contact_readiness": self.contact_readiness
            },
            "travel_interest": {
                "main_interest": self.main_interest,
                "secondary_interests": self.secondary_interests,
                "travel_context": self.travel_context
            },
            "metadata": {
                "created_at": iso_argentina(self.created_at, source="ar"),
                "updated_at": iso_argentina(self.updated_at, source="ar"),
                "status": self.status,
                "channel": self.channel,
                "origin": self.origin(),
                "suggested_response_tone": self.suggested_response_tone,
                "next_action": self.next_action,
                "reasoning": self.reasoning
            },
            "kanban": {
                "stage": self.kanban_stage,
                "notes": self.notes,
                "last_status_change": iso_argentina(self.last_status_change, source="ar")
            },
            "event_info": {
                "is_event_lead": self.is_event_lead,
                "event_name": self.event_name,
                "event_type": self.event_type,
                "event_countries": self.event_countries,
                "event_year": self.event_year
            }
        }
    
    def update_from_analysis(self, analysis: Dict, travel_context: str = ""):
        """Actualiza el lead basado en nuevo análisis"""
        # PISO DE NO-DEGRADACIÓN: el interés de un lead es ACUMULATIVO durante la charla.
        # Cada turno re-analiza solo el último mensaje, así que un mensaje neutro o de cierre
        # ("Mi nombre es Rodrigo", "gracias, lo consulto") parece frío y degradaría a un lead
        # que ya mostró interés (vio precios, dio fechas). El score solo sube o se mantiene:
        # tomamos el máximo entre lo que el lead ya tenía y lo que dice este turno, y el tipo
        # acompaña al score que prevalece (no dejamos score 8 con tipo FRIO).
        new_score = analysis.get('interest_score', self.interest_score)
        new_type = analysis.get('lead_type', self.lead_type)
        prev_score = self.interest_score or 0
        if (new_score or 0) >= prev_score:
            self.interest_score = new_score
            self.lead_type = new_type
        # else: el turno daría un score menor → conservamos score y tipo previos (el pico).
        self.obstacle = analysis.get('obstacle', self.obstacle)
        self.contact_readiness = analysis.get('contact_readiness', self.contact_readiness)
        
        # 🆕 PRESERVAR main_interest: Solo actualizar si el nuevo es más específico
        new_interest = analysis.get('main_interest')
        if new_interest:
            # Lista de valores genéricos que NO deben sobrescribir un destino específico
            generic_interests = [
                'consulta sobre viajes',
                'consulta general',
                'información general',
                'pregunta general',
                'viaje',
                'viajes'
            ]
            
            # Si el nuevo interés NO es genérico, actualizar
            if new_interest.lower() not in generic_interests:
                self.main_interest = new_interest
            # Si el nuevo es genérico pero NO hay nada guardado, guardar
            elif not self.main_interest:
                self.main_interest = new_interest
            # Si el nuevo es genérico y YA hay algo específico, NO sobrescribir
            # (mantener el valor actual)
        
        # Acumular secondary_interests sin perder los anteriores
        new_secondary = analysis.get('secondary_interests')
        if isinstance(new_secondary, list) and new_secondary:
            existing = self.secondary_interests or []
            merged = list(dict.fromkeys(existing + new_secondary))  # deduplica, preserva orden
            self.secondary_interests = merged[:5]  # máximo 5

        if travel_context:
            self.travel_context = travel_context

        self.suggested_response_tone = analysis.get('suggested_response_tone')
        self.next_action = analysis.get('next_action')
        self.reasoning = analysis.get('reasoning')
        self.updated_at = now_argentina()
    
    def add_contact_info(self, name: str = None, last_name: str = None, phone: str = None, email: str = None):
        """Agrega información de contacto al lead"""
        if name:
            self.name = name
        if last_name:
            self.last_name = last_name
        if phone:
            self.phone = phone
        if email:
            self.email = email
        # Si el lead ya tiene datos completos, ya no es necesario solicitarlos
        if self.is_complete_lead():
            self.contact_readiness = False
        self.updated_at = now_argentina()
    
    def is_complete_lead(self) -> bool:
        """Verifica si el lead tiene información de contacto completa"""
        # Criterio mínimo: nombre + (teléfono O email)
        has_name = bool(self.name)
        has_contact = bool(self.phone) or bool(self.email)
        return has_name and has_contact
    
    def is_ideal_lead(self) -> bool:
        """Verifica si el lead tiene información de contacto ideal"""
        # Criterio ideal: nombre + apellido + teléfono + email
        return bool(self.name and self.last_name and self.phone and self.email)
    
    def get_completeness_score(self) -> float:
        """Calcula score de completitud del lead (0-1)"""
        fields = [self.name, self.last_name, self.phone, self.email]
        filled_fields = sum(1 for field in fields if field)
        return filled_fields / len(fields)
    
    def get_priority_score(self) -> float:
        """Calcula score de prioridad para el lead"""
        base_score = self.interest_score
        
        # Bonificaciones por tipo de lead
        if self.lead_type == "CALIENTE":
            base_score += 3
        elif self.lead_type == "TIBIO":
            base_score += 1
        
        # Bonificación por tener contacto
        if self.is_complete_lead():
            base_score += 2
        
        # Bonificación por estar listo para contacto
        if self.contact_readiness:
            base_score += 1
        
        return min(base_score, 10.0)  # Máximo 10
    
    # Métodos para Kanban
    def update_kanban_stage(self, new_stage: str):
        """Actualiza el estado del kanban"""
        valid_stages = ["new", "contacted", "won", "lost"]
        if new_stage not in valid_stages:
            raise ValueError(f"Invalid stage: {new_stage}. Must be one of {valid_stages}")
        
        self.kanban_stage = new_stage
        self.last_status_change = now_argentina()
        self.updated_at = now_argentina()
    
    def add_note(self, note: str):
        """Agrega una nota al lead"""
        if self.notes:
            self.notes += f"\n\n---\n{now_argentina().strftime('%Y-%m-%d %H:%M')}: {note}"
        else:
            self.notes = f"{now_argentina().strftime('%Y-%m-%d %H:%M')}: {note}"
        self.updated_at = now_argentina()
    
    def get_display_name(self) -> str:
        """Obtiene el nombre para mostrar"""
        if self.name and self.last_name:
            return f"{self.name} {self.last_name}"
        elif self.name:
            return self.name
        else:
            return f"Lead #{self.id}"
    
    def get_time_since_creation(self) -> str:
        """Obtiene tiempo desde creación en formato legible"""
        if not self.created_at:
            return "Desconocido"
        
        delta = now_argentina() - self.created_at
        
        if delta.days > 0:
            return f"Hace {delta.days} día{'s' if delta.days > 1 else ''}"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"Hace {hours} hora{'s' if hours > 1 else ''}"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"Hace {minutes} minuto{'s' if minutes > 1 else ''}"
        else:
            return "Justo ahora"


class LeadEvent(Base):
    """Bitácora de actividad de un lead: quién hizo qué (mismo patrón que TicketEvent).

    Mezcla las ACCIONES de Aura (resumidas en una línea: "Ofreció disponibilidad", "Confirmó
    la reserva") con el SEGUIMIENTO humano (un staffer deja un comentario). Permite ver la
    historia del lead dentro de su card y alimenta la observabilidad del agente.
    """
    __tablename__ = "lead_events"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    # Quién originó la acción: "aura" (el agente) | "human" (equipo desde el backoffice) | "system".
    actor_type = Column(String(20), nullable=False, default="aura")
    actor_name = Column(String(120), nullable=True)   # legible (ej. "Aura", "Recepción", el staffer)
    action = Column(String(50), nullable=False)        # availability_shown | booking_confirmed | contact_requested | reengaged | seguimiento | resumen
    summary = Column(String(255), nullable=True)       # one-liner mostrable ("Ofreció disponibilidad")
    note = Column(Text, nullable=True)                 # texto libre (seguimiento humano / resumen IA)
    created_at = Column(DateTime, default=now_argentina, index=True)

    lead = relationship("Lead", back_populates="events")

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "actor_type": self.actor_type,
            "actor_name": self.actor_name,
            "action": self.action,
            "summary": self.summary,
            "note": self.note,
            "created_at": iso_argentina(self.created_at),
        }
