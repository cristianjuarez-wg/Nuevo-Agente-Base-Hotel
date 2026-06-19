"""
Modelo de Tracking de Vuelos
Almacena histórico de chequeos y cambios detectados
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.database import Base

class FlightStatusTracking(Base):
    """Histórico de chequeos de estado de vuelos"""
    __tablename__ = "flight_status_tracking"
    
    # Identificación
    id = Column(Integer, primary_key=True)
    flight_id = Column(Integer, ForeignKey('package_flights.id', ondelete='CASCADE'), nullable=False)
    
    # Timestamp
    check_timestamp = Column(DateTime, default=datetime.utcnow)
    checked_by = Column(String(50), default='manual')  # 'manual', 'agent_query', 'scheduled'
    
    # Identificación del vuelo
    flight_iata = Column(String(10))
    flight_number = Column(String(10))
    airline_name = Column(String(100))
    flight_date = Column(Date)
    
    # Estado
    flight_status = Column(String(50))  # scheduled, active, landed, cancelled, etc.
    
    # Salida
    departure_airport = Column(String(200))
    departure_iata = Column(String(10))
    departure_terminal = Column(String(10))
    departure_gate = Column(String(10))
    departure_scheduled = Column(DateTime)
    departure_estimated = Column(DateTime)
    departure_actual = Column(DateTime)
    departure_delay = Column(Integer, default=0)
    
    # Llegada
    arrival_airport = Column(String(200))
    arrival_iata = Column(String(10))
    arrival_terminal = Column(String(10))
    arrival_gate = Column(String(10))
    arrival_baggage = Column(String(10))
    arrival_scheduled = Column(DateTime)
    arrival_estimated = Column(DateTime)
    arrival_actual = Column(DateTime)
    arrival_delay = Column(Integer, default=0)
    
    # Cambios detectados
    has_changes = Column(Boolean, default=False)
    changes_detected = Column(Text)  # JSON con lista de cambios
    change_severity = Column(String(20), default='low')  # low, medium, high, critical
    
    # Notificaciones simuladas
    notifications_simulated = Column(Text)  # JSON con notificaciones que se habrían enviado
    ticket_created = Column(Boolean, default=False)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'))
    
    # Metadata
    raw_api_response = Column(Text)  # JSON completo de la API
    
    # Relaciones
    flight = relationship("PackageFlight")
    ticket = relationship("SupportTicket")
    
    def to_dict(self):
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "flight_id": self.flight_id,
            "check_timestamp": self.check_timestamp.isoformat() if self.check_timestamp else None,
            "checked_by": self.checked_by,
            "flight_status": self.flight_status,
            "has_changes": self.has_changes,
            "change_severity": self.change_severity,
            "departure_delay": self.departure_delay,
            "arrival_delay": self.arrival_delay,
            "ticket_created": self.ticket_created,
            "ticket_id": self.ticket_id
        }
