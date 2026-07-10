"""
Documento de ENTRENAMIENTO de un agente — la "capacitación" del empleado digital.

Distinto del Conocimiento del negocio (KnowledgeEntry, capa Negocio): el
entrenamiento moldea *cómo se comporta* el agente (tono, protocolos, políticas
de marca) y vive en la capa Agente (CENTRO_EMPLEADO_DIGITAL.md §9.4). Se asigna
a UN agente puntual (§2.4): dos agentes del mismo rol pueden entrenarse distinto.

Etapa 3 = vínculo en datos (§7.2 etapa a): el documento queda asociado al agente
con su texto extraído, pero el filtrado en el retrieval (RAG por skill/agente) es
una etapa posterior. Por eso acá NO se ingesta al vector store global: se evita
que el tono de un protocolo se filtre en respuestas que no le corresponden.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from datetime import datetime

from app.models.database import Base, engine
from app.utils.timezone_utils import utcnow_naive


class TrainingDocument(Base):
    __tablename__ = "training_documents"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=False, index=True)     # a qué agente entrena
    skill_id = Column(Integer, nullable=True)                  # opcional: acota a una skill (§7.2)
    title = Column(String(200), nullable=False)
    source = Column(String(20), nullable=False, default="text")  # form | pdf | markdown | text
    filename = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)                      # texto libre (docs legado)
    # Entrenamiento ESTRUCTURADO (Fase E): el cliente llena CAMPOS, nunca texto libre
    # al prompt. El texto inyectable lo renderiza nuestra plantilla fija (training_service).
    category = Column(String(30), nullable=True, index=True)   # tono_marca | objeciones | ...
    data = Column(JSON, nullable=True, default=dict)           # campos del formulario
    active = Column(Boolean, nullable=False, default=True)     # si influye (cuando haya inyección)
    is_default = Column(Boolean, nullable=False, default=False)  # plantilla de fábrica (no se borra)
    created_at = Column(DateTime, default=utcnow_naive)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "skill_id": self.skill_id,
            "title": self.title,
            "source": self.source,
            "filename": self.filename,
            "category": self.category,
            "data": self.data or {},
            "active": bool(self.active),
            "is_default": bool(self.is_default),
            # Resumen corto para la lista (no devolvemos todo el texto por defecto).
            "excerpt": (self.content or "")[:160],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que los demás modelos del hotel).
Base.metadata.create_all(bind=engine, tables=[TrainingDocument.__table__])
