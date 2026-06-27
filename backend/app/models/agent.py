"""
Agente como ENTIDAD DE PRIMERA CLASE — núcleo del "Centro del Empleado Digital".

Hasta ahora el agente era un rol implícito en el código (los orquestadores
guest/owner/staff). Este modelo lo vuelve una entidad con identidad propia: su
legajo, su estado, su rol como atributo (no como identidad). Esto habilita
medir cada agente por separado, entrenarlo y —a futuro— multiplicarlo.

Decisión de diseño (CENTRO_EMPLEADO_DIGITAL.md §2.2): "modelá multiplicable,
mostrá simple". El modelo soporta N agentes por rol desde el día uno; la UI, al
principio, expone uno por rol. El `role` es un atributo del agente, no su PK.

Nota: pre-venta y post-venta NO son dos agentes — son dos contextos del mismo
agente huésped (Aura), separables por `context_type` en las métricas (§10.2).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from datetime import datetime

from app.models.database import Base, engine


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)            # "Aura", "Asesor", "Operaciones"
    # Rol = ATRIBUTO, no identidad: guest | management | staff.
    # (guest cubre pre_sale + post_sale; son contextos del mismo agente, §10.2.)
    role = Column(String(20), nullable=False, default="guest")
    status = Column(String(20), nullable=False, default="active")   # active | paused
    channels = Column(JSON, nullable=True, default=list)            # ["whatsapp", "web"]
    # Vínculo opcional al miembro del staff (owner/staff ya tienen teléfono cargado).
    staff_member_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    # Config del "parte de fin de día" (Etapa 2). Opt-in y por agente:
    #   {"enabled": bool, "recipient_staff_ids": [int, ...]}
    # Default: desactivado y sin destinatarios (el parte se muestra, NO se envía).
    daily_report = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, default=datetime.now)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "channels": self.channels or [],
            "staff_member_id": self.staff_member_id,
            "description": self.description,
            "daily_report": self.daily_report or {"enabled": False, "recipient_staff_ids": []},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que los demás modelos del hotel).
Base.metadata.create_all(bind=engine, tables=[Agent.__table__])
