"""
Modelo de PROMOCIONES del hotel (Fase 3).

El cliente carga y gestiona promociones desde el backoffice. Cada cambio se re-ingesta
automáticamente al vector store (ver services/promotions_service.py) para que el agente
las conozca. Además, la tool determinística `promos_vigentes` lee esta tabla directamente
y devuelve datos exactos — sin pasar por RAG difuso.

Vigencia: una promo está vigente si status == "active" y, si tiene fechas, el momento
actual está dentro del rango [valid_from, valid_until]. Fechas nulas = sin límite.
"""
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Boolean
from datetime import datetime

from app.models.database import Base, engine
from app.utils.timezone_utils import utcnow_naive


class Promotion(Base):
    """Promoción o oferta especial del hotel."""
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)                    # "Promo 4x3", "Stay & Park"
    description = Column(Text, nullable=False)               # Texto descriptivo completo
    conditions = Column(Text, nullable=True)                 # Restricciones / requisitos
    discount_type = Column(String, nullable=False, default="other")
    # "percentage"  → discount_value = % de descuento (ej. 20.0)
    # "free_night"  → discount_value = noches bonificadas (ej. 1 en 4x3, 2 en 7x5)
    # "other"       → descuento libre (ej. "estacionamiento incluido")
    discount_value = Column(Float, nullable=True)

    # Mínimo de noches para que la promo aplique (4x3 → 4, 7x5 → 7). Null = sin mínimo.
    # Para free_night/percentage define la condición de elegibilidad por estadía.
    min_nights = Column(Integer, nullable=True)

    status = Column(String, nullable=False, default="active", index=True)
    # "active" | "inactive"

    valid_from = Column(DateTime, nullable=True)             # Null = sin límite de inicio
    valid_until = Column(DateTime, nullable=True)            # Null = sin fecha de vencimiento

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    @property
    def doc_source(self) -> str:
        """Identificador determinístico para ChromaDB (borrar/re-agregar chunks)."""
        return f"kb-promo-{self.id}"

    def to_ingest_text(self) -> str:
        """Texto legible que se chunkea e ingesta al vector store."""
        parts = [f"Promoción: {self.name}", self.description]
        if self.discount_type == "percentage" and self.discount_value is not None:
            parts.append(f"Descuento: {self.discount_value:.0f}% de descuento.")
        elif self.discount_type == "free_night" and self.discount_value is not None:
            bonif = int(self.discount_value)
            parts.append(f"Noches bonificadas: {bonif} noche(s) gratis incluida(s).")
        if self.min_nights:
            parts.append(f"Estadía mínima: {self.min_nights} noche(s).")
        if self.conditions:
            parts.append(f"Condiciones: {self.conditions}")
        if self.valid_from or self.valid_until:
            rango = []
            if self.valid_from:
                rango.append(f"desde {self.valid_from.strftime('%d/%m/%Y')}")
            if self.valid_until:
                rango.append(f"hasta {self.valid_until.strftime('%d/%m/%Y')}")
            parts.append(f"Vigencia: {', '.join(rango)}.")
        return "\n\n".join(parts)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "conditions": self.conditions,
            "discount_type": self.discount_type,
            "discount_value": self.discount_value,
            "min_nights": self.min_nights,
            "status": self.status,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


Base.metadata.create_all(
    bind=engine,
    tables=[Promotion.__table__],
)
