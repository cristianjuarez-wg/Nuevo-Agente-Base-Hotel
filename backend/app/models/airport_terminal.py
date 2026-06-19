"""
Modelo de Terminales de Aeropuertos
Almacena coordenadas GPS de terminales para generar links de Google Maps
Incluye sistema de descubrimiento automático
"""
from sqlalchemy import Column, Integer, String, Numeric, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.models.database import Base


class AirportTerminal(Base):
    """Información de terminales de aeropuertos con coordenadas GPS"""
    __tablename__ = "airport_terminals"
    
    # Identificación
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Aeropuerto
    airport_iata = Column(String(10), nullable=False, index=True)
    airport_name = Column(String(200), nullable=False)
    airport_city = Column(String(100))
    airport_country = Column(String(100))
    
    # Terminal
    terminal_code = Column(String(10), nullable=False)
    terminal_name = Column(String(100))
    
    # Coordenadas GPS
    latitude = Column(Numeric(10, 8), nullable=False)
    longitude = Column(Numeric(11, 8), nullable=False)
    
    # Google Maps
    google_place_id = Column(String(200))
    
    # Metadata de descubrimiento automático
    auto_discovered = Column(Boolean, default=False)
    discovery_method = Column(String(50))  # 'nominatim', 'overpass', 'airport_fallback', 'manual'
    confidence_score = Column(Numeric(3, 2))  # 0.00 a 1.00
    last_verified = Column(DateTime)
    search_attempts = Column(Integer, default=0)
    
    # Información adicional
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "airport_iata": self.airport_iata,
            "airport_name": self.airport_name,
            "airport_city": self.airport_city,
            "airport_country": self.airport_country,
            "terminal_code": self.terminal_code,
            "terminal_name": self.terminal_name,
            "latitude": float(self.latitude) if self.latitude else None,
            "longitude": float(self.longitude) if self.longitude else None,
            "google_place_id": self.google_place_id,
            "auto_discovered": self.auto_discovered,
            "discovery_method": self.discovery_method,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "is_active": self.is_active
        }
    
    def __repr__(self):
        return f"<AirportTerminal {self.airport_iata} Terminal {self.terminal_code}>"


class TerminalDiscoveryLog(Base):
    """Log de búsquedas automáticas de terminales"""
    __tablename__ = "terminal_discovery_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    airport_iata = Column(String(10), nullable=False)
    terminal_code = Column(String(10), nullable=False)
    airport_name = Column(String(200))
    
    # Búsqueda
    search_query = Column(Text)
    method_used = Column(String(50))  # 'nominatim', 'overpass', 'airport_fallback'
    success = Column(Boolean, default=False)
    
    # Resultado
    coordinates_found = Column(Text)  # JSON: {"lat": ..., "lng": ...}
    confidence_score = Column(Numeric(3, 2))
    error_message = Column(Text)
    
    # Metadata
    timestamp = Column(DateTime, server_default=func.now())
    
    def to_dict(self):
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "airport_iata": self.airport_iata,
            "terminal_code": self.terminal_code,
            "method_used": self.method_used,
            "success": self.success,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
