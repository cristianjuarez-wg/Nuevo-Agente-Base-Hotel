"""
Planes de acción acordados entre el CEO/dueño y el Asesor de gerencia.

Convierte al asesor en un socio de trabajo de LARGO PLAZO: cuando acuerdan una acción
("subir la ocupación de mayo con tarifas last-minute"), el asesor la registra acá; en
charlas futuras la retoma y hace seguimiento ("¿cómo venimos con eso?"). Aislado por
`owner_session` (el session_id "owner_<tel>") para que cada CEO tenga sus propios planes.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from datetime import datetime

from app.models.database import Base, engine
from app.utils.timezone_utils import utcnow_naive


class ActionPlan(Base):
    __tablename__ = "action_plans"

    id = Column(Integer, primary_key=True, index=True)
    owner_session = Column(String(120), nullable=False, index=True)  # "owner_<telefono>"
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    metric = Column(String(120), nullable=True)        # qué medir, ej. "ocupación mayo"
    status = Column(String(20), nullable=False, default="active")  # active | done | dropped
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
    last_reviewed_at = Column(DateTime, nullable=True)  # última vez que se retomó/actualizó

    def to_dict(self):
        return {
            "id": self.id,
            "owner_session": self.owner_session,
            "title": self.title,
            "description": self.description,
            "metric": self.metric,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que StaffMember).
Base.metadata.create_all(bind=engine, tables=[ActionPlan.__table__])
