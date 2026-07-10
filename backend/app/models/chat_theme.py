"""
Modelo ChatTheme — temas visuales estacionales del chat widget.

Cada tema define los tokens de color que se inyectan como CSS variables
en el panel del chat, más un emoji decorativo opcional y el rango de fechas
en que debe activarse automáticamente.

Campos de color (todos HEX o cualquier valor CSS válido):
  header_bg      — fondo del header del chat (ej: "#c41e3a" para Navidad)
  header_text    — texto/iconos del header
  accent_color   — color de acento (burbujas del usuario, botón enviar)
  bubble_bg      — fondo de burbujas del agente (por defecto #f7f4ee = linen)
  fab_bg         — color del botón flotante (FAB)
  fab_text       — texto/iconos del FAB
"""
from datetime import datetime
from app.models.database import Base, engine
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.utils.timezone_utils import utcnow_naive


class ChatTheme(Base):
    __tablename__ = "chat_themes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)           # "Navidad", "Ski & Nieve", etc.
    emoji = Column(String, nullable=True)           # "🎄", "⛷️", "🌊", "🐣"
    description = Column(String, nullable=True)     # texto libre para el backoffice

    # Rango de activación automática (mes/día, sin año — comparación anual)
    active_from_month = Column(Integer, nullable=True)   # 1-12
    active_from_day = Column(Integer, nullable=True)     # 1-31
    active_until_month = Column(Integer, nullable=True)
    active_until_day = Column(Integer, nullable=True)

    # Tokens de color
    header_bg = Column(String, nullable=True)
    header_text = Column(String, nullable=True)
    accent_color = Column(String, nullable=True)
    bubble_bg = Column(String, nullable=True)
    fab_bg = Column(String, nullable=True)
    fab_text = Column(String, nullable=True)

    # Efecto animado sutil sobre el panel del chat:
    #   "none" | "snow" (copos) | "snow_gold" (copos + destellos dorados, Navidad)
    #   "leaves" (hojas/destellos flotando, verano) | "bunny" (conejito intermitente, Pascua)
    effect = Column(String, nullable=True, default="none")

    # Estado — "active" activo (respeta fechas), "pinned" siempre activo, "inactive" off
    status = Column(String, default="active", nullable=False)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "description": self.description,
            "active_from_month": self.active_from_month,
            "active_from_day": self.active_from_day,
            "active_until_month": self.active_until_month,
            "active_until_day": self.active_until_day,
            "header_bg": self.header_bg,
            "header_text": self.header_text,
            "accent_color": self.accent_color,
            "bubble_bg": self.bubble_bg,
            "fab_bg": self.fab_bg,
            "fab_text": self.fab_text,
            "effect": self.effect or "none",
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


Base.metadata.create_all(bind=engine, tables=[ChatTheme.__table__])
