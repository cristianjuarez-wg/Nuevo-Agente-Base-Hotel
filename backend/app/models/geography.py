"""
Modelos para mapeo geográfico inteligente
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from app.models.database import Base
from datetime import datetime
from typing import Dict, Optional

class GeographicMapping(Base):
    """
    Mapeos geográficos aprendidos automáticamente
    Solo para landmarks FIJOS (no eventos temporales)
    """
    __tablename__ = "geographic_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Término buscado
    term = Column(String(200), unique=True, index=True, nullable=False)
    normalized_term = Column(String(200), index=True)  # lowercase para búsqueda
    
    # Clasificación
    type = Column(String(50), nullable=False)  # landmark, city, region, natural_wonder
    primary_country = Column(String(100), nullable=False)
    alternative_countries = Column(JSON)  # Lista de países alternativos
    
    # Confianza y validación
    confidence = Column(Float, default=0.0)  # 0.0 - 1.0
    is_validated = Column(Boolean, default=False)
    validated_by = Column(String(100))  # "gpt", "manual", "user_feedback"
    
    # Metadata
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)
    
    # Contexto adicional
    keywords = Column(JSON)  # Palabras clave relacionadas
    reasoning = Column(Text)  # Explicación de GPT sobre el mapeo
    
    # Flag permanente
    is_permanent = Column(Boolean, default=True)  # Siempre True (no eventos temporales)
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "term": self.term,
            "type": self.type,
            "primary_country": self.primary_country,
            "alternative_countries": self.alternative_countries or [],
            "confidence": self.confidence,
            "is_validated": self.is_validated,
            "usage_count": self.usage_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "keywords": self.keywords or [],
            "reasoning": self.reasoning
        }
    
    def increment_usage(self):
        """Incrementa contador de uso"""
        self.usage_count += 1
        self.last_used_at = datetime.utcnow()
    
    def validate(self, validated_by: str = "manual"):
        """Marca como validado"""
        self.is_validated = True
        self.validated_by = validated_by
