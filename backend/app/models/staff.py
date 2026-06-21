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


class StaffMember(Base):
    __tablename__ = "staff_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(50), nullable=False, unique=True, index=True)  # normalizado (+549...)
    role = Column(String(20), nullable=False, default="staff")  # "owner" | "staff"
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        from app.utils.phone_normalizer import is_whatsapp_capable
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "role": self.role,
            "active": self.active,
            "whatsapp_linked": is_whatsapp_capable(self.phone),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que los modelos del hotel).
Base.metadata.create_all(bind=engine, tables=[StaffMember.__table__])
