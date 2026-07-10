"""
Personal del hotel con su rol — base del agente MULTI-ROL.

Permite que el agente de WhatsApp distinga quién escribe: un huésped, un miembro del
staff (housekeeping/mantenimiento/recepción) o el dueño. Cada rol habilita capacidades
distintas (el dueño consulta BI; el staff cierra tickets; el huésped reserva/consulta).

Identidad por teléfono normalizado (mismo formato que Contact.phone_number).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime

from app.models.database import Base, engine
from app.utils.timezone_utils import utcnow_naive


class StaffMember(Base):
    __tablename__ = "staff_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(50), nullable=False, unique=True, index=True)  # normalizado (+549...)
    role = Column(String(20), nullable=False, default="staff")  # "owner" | "staff"
    # Área operativa: define a qué staff se asignan los tickets de servicio del huésped
    # (el agente clasifica el problema y enruta al área correcta). Editable desde backoffice.
    area = Column(String(20), nullable=False, default="general")  # mantenimiento | recepcion | housekeeping | general
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow_naive)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "role": self.role,
            "area": self.area,
            "active": self.active,
            # Para el equipo asumimos que el número cargado es su WhatsApp (regla de negocio).
            "whatsapp_linked": True,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que los modelos del hotel).
Base.metadata.create_all(bind=engine, tables=[StaffMember.__table__])
