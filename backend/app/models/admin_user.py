"""
Usuario del BACKOFFICE (Fase 2.5) — auth real con password hasheada + roles.

Reemplaza el esquema anterior de "clave compartida X-Admin-Key" (fail-open si estaba
vacía). Cada operador tiene su usuario; la sesión se maneja con JWT (ver core/security/auth).

Roles:
  - admin:    acceso total (incluye Sistema/Usage/config sensible).
  - operador: operación diaria (sin las vistas de sistema).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.models.database import Base, engine


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)   # bcrypt
    role = Column(String(20), nullable=False, default="admin")  # admin | operador
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que CentroConfig / BusinessProfile).
Base.metadata.create_all(bind=engine, tables=[AdminUser.__table__])
