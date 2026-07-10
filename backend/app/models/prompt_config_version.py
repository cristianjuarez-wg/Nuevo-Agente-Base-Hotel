"""
Versionado de la configuración de prompts del cliente (Fase 3.3).

Todo lo que el cliente puede cambiar y que afecta al prompt del agente (tono, política,
directivas de entrenamiento, flow variant, facts del negocio) se snapshotea acá. Cada guardado
desde el backoffice crea una versión nueva; "volver a una versión anterior" = activar un snapshot
viejo. El composer del prompt lee SIEMPRE la versión activa (o el estado en vivo si no hay
ninguna, para compatibilidad).

Singleton lógico de "versión activa": a lo sumo una fila con active=True.
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON

from app.models.database import Base, engine


class PromptConfigVersion(Base):
    __tablename__ = "prompt_config_versions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    author = Column(String(120), nullable=True)          # email del admin que guardó (si se sabe)
    label = Column(String(200), nullable=True)           # nombre legible ("Tono más formal", ...)
    # Snapshot COMPLETO de lo que afecta el prompt, para poder reconstruir la config exacta:
    #   { "facts": [...], "flow_variant": "...", "training": [ {agent_id, category, data, ...} ] }
    payload = Column(JSON, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "author": self.author,
            "label": self.label,
            "active": self.active,
            "payload": self.payload or {},
        }


# Crea la tabla si no existe (patrón del resto de modelos del proyecto; idempotente).
Base.metadata.create_all(bind=engine, tables=[PromptConfigVersion.__table__])
