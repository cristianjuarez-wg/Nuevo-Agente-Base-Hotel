"""
Identidad del NEGOCIO — la fuente única de quién es este cliente (Fase 1).

Fila única (id=1, mismo patrón que CentroConfig): marca, voz, ubicación, timezone,
moneda, idioma y "hechos duros" del negocio. Los prompts se COMPONEN desde acá en vez
de tener "Hampton by Hilton Bariloche" / "Bariloche" / "ARS" / voseo hardcodeados.

Distinción con CentroConfig: CentroConfig son INTERRUPTORES de comportamiento (kill
switch); BusinessProfile es la IDENTIDAD del negocio. Conviven como dos singletons.

Nace sembrado con los valores del Hampton (paridad): con el seed de fábrica, el agente
se comporta exactamente como antes de la Fase 1.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func

from app.models.database import Base, engine


class BusinessProfile(Base):
    __tablename__ = "business_profile"

    id = Column(Integer, primary_key=True)  # siempre id=1 (singleton por instancia)

    # ── Identidad ────────────────────────────────────────────────────────────
    business_name = Column(String, nullable=False, default="Hampton by Hilton Bariloche")
    brand_line = Column(String, nullable=True)                 # "el primer Hilton de la Patagonia"
    vertical = Column(String, nullable=False, default="hotel")
    agent_display_name = Column(String, nullable=False, default="Aura")
    # Descriptor del rol del agente en la identidad ("concierge", "asistente", etc.).
    role_descriptor = Column(String, nullable=False, default="concierge")
    # Nombre del restaurante del negocio (para no hardcodear "Hampton's Kitchen House"). F3.3.
    restaurant_name = Column(String, nullable=True, default="Plaza — Hampton's Kitchen House")

    # ── Localización ─────────────────────────────────────────────────────────
    timezone = Column(String, nullable=False, default="America/Argentina/Buenos_Aires")
    locale = Column(String, nullable=False, default="es_AR")   # formato de fecha/número
    language = Column(String, nullable=False, default="es")
    # rioplatense_voseo | es_neutro | es_tuteo | en
    dialect_style = Column(String, nullable=False, default="rioplatense_voseo")
    city = Column(String, nullable=True, default="Bariloche")
    region_line = Column(String, nullable=True)                # color local para el prompt
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    # ── Moneda ───────────────────────────────────────────────────────────────
    primary_currency = Column(String, nullable=False, default="USD")     # fuente de verdad de precios
    secondary_currency = Column(String, nullable=True, default="ARS")    # None = monomoneda

    # ── Hechos duros del negocio (reemplaza "no hay spa ni sauna" hardcodeado) ──
    facts = Column(JSON, nullable=False, default=list)

    # ── Contacto (para fallbacks del agente: "contactanos al ..."). Fase 3.5. ──
    contact_phone = Column(String, nullable=True)              # "+54 294-474-6200"
    contact_email = Column(String, nullable=True)              # "info@hamptonbariloche.com"

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "business_name": self.business_name,
            "brand_line": self.brand_line,
            "vertical": self.vertical,
            "agent_display_name": self.agent_display_name,
            "role_descriptor": self.role_descriptor,
            "restaurant_name": self.restaurant_name,
            "timezone": self.timezone,
            "locale": self.locale,
            "language": self.language,
            "dialect_style": self.dialect_style,
            "city": self.city,
            "region_line": self.region_line,
            "lat": self.lat,
            "lng": self.lng,
            "primary_currency": self.primary_currency,
            "secondary_currency": self.secondary_currency,
            "facts": self.facts or [],
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Crear la tabla de forma explícita (mismo patrón que CentroConfig / StaffMember).
Base.metadata.create_all(bind=engine, tables=[BusinessProfile.__table__])

# Columnas aditivas (Fase 3.5): en una DB que ya tenía la tabla, agregarlas si faltan.
try:
    from sqlalchemy import text as _text
    with engine.begin() as _conn:
        cols = {r[1] for r in _conn.execute(_text("PRAGMA table_info(business_profile)"))} \
            if engine.dialect.name == "sqlite" else set()
        if engine.dialect.name == "sqlite":
            if "contact_phone" not in cols:
                _conn.execute(_text("ALTER TABLE business_profile ADD COLUMN contact_phone VARCHAR"))
            if "contact_email" not in cols:
                _conn.execute(_text("ALTER TABLE business_profile ADD COLUMN contact_email VARCHAR"))
            if "restaurant_name" not in cols:
                _conn.execute(_text("ALTER TABLE business_profile ADD COLUMN restaurant_name VARCHAR"))
except Exception:  # noqa: BLE001 — best-effort; en Postgres/prod lo maneja Alembic
    pass
