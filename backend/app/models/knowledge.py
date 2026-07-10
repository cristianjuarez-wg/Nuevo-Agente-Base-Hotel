"""
Modelos del REPOSITORIO DE CONOCIMIENTO del hotel (Fase 1).

El cliente (dueño del hotel) carga y edita aquí su información — políticas, datos de
pago/transferencia, servicios, FAQ, lugares/excursiones — desde el backoffice. Cada
cambio se re-ingesta automáticamente al vector store (ver services/knowledge_service.py),
de modo que el agente la toma en caliente, sin redeploy.

Dos entidades:
  - KnowledgeEntry: información estructurada por categoría (formularios guiados).
  - Place:          lugares / excursiones / puntos de interés (con imagen + link de Maps).

Ambas exponen:
  - `doc_source`: identificador determinístico (string) usado como `source`/`filename`
    de los chunks en ChromaDB, para poder borrar/re-agregar con precisión.
  - `to_ingest_text()`: el texto legible que se chunkea e ingesta al RAG.
  - `to_dict()`: payload para la API/backoffice.

Reutilizan el `Base`/`engine` de models/database.py (misma BD; SQLite local / PostgreSQL
en Render). Las tablas se crean con create_all(tables=[...]) explícito, igual que hotel.py.
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON, Boolean, text
from datetime import datetime

from app.models.database import Base, engine
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


# Categorías válidas para las entradas estructuradas (formularios del backoffice).
KNOWLEDGE_CATEGORIES = (
    "pagos",        # medios de pago, datos de transferencia (CBU/alias/titular/banco)
    "checkin",      # horarios de check-in / check-out, early/late
    "cancelacion",  # política de cancelación / no-show / modificaciones
    "mascotas",     # política de mascotas / niños / fumadores
    "servicios",    # servicios e instalaciones (desayuno, wifi, gym, cochera...)
    "faq",          # preguntas frecuentes (pares pregunta/respuesta en `data`)
    "general",      # información libre que no encaja en las anteriores
)

PLACE_CATEGORIES = (
    "excursion",
    "gastronomia",
    "atraccion",
    "transporte",
    "hotel",
)


def _payment_accounts(data: dict) -> list:
    """Normaliza las cuentas bancarias de la entry de pagos.

    Soporta el formato nuevo (data['cuentas'] = [ {titular, banco, cbu, alias, moneda,
    default}, ... ]) y el viejo (campos sueltos titular/banco/cbu/alias en la raíz, que se
    trata como una única cuenta default). Devuelve la lista ordenada con la default primero.
    """
    cuentas = data.get("cuentas")
    if not cuentas:
        # Retrocompat: campos sueltos en la raíz = una sola cuenta.
        if any(data.get(k) for k in ("titular", "banco", "cbu", "alias")):
            cuentas = [{
                "titular": data.get("titular"),
                "banco": data.get("banco"),
                "cbu": data.get("cbu"),
                "alias": data.get("alias"),
                "moneda": data.get("moneda"),
                "default": True,
            }]
        else:
            cuentas = []
    # Ordenar: la default primero.
    return sorted(cuentas, key=lambda c: not c.get("default"))


class KnowledgeEntry(Base):
    """Información estructurada del hotel, cargada por categoría desde el backoffice."""
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False, index=True)   # ver KNOWLEDGE_CATEGORIES
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)                   # texto libre de la entrada
    # Campos estructurados según categoría. Ej pagos:
    #   {"cbu": "...", "alias": "...", "titular": "...", "banco": "...", "medios": ["Transferencia", "Tarjeta"]}
    # Ej faq: {"items": [{"q": "...", "a": "..."}, ...]}
    data = Column(JSON, nullable=True, default=dict)
    status = Column(String, nullable=False, default="active", index=True)  # active / inactive

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def doc_source(self) -> str:
        """Identificador determinístico para los chunks de esta entrada en ChromaDB."""
        return f"kb-entry-{self.id}"

    def to_ingest_text(self) -> str:
        """Arma el texto legible que se ingesta al RAG (title + content + data legible)."""
        parts = [self.title.strip()] if self.title else []
        if self.content:
            parts.append(self.content.strip())

        data = self.data or {}
        if self.category == "pagos":
            medios = data.get("medios") or []
            if medios:
                parts.append("Medios de pago aceptados: " + ", ".join(medios) + ".")
            for cuenta in _payment_accounts(data):
                bits = []
                if cuenta.get("titular"):
                    bits.append(f"Titular: {cuenta['titular']}")
                if cuenta.get("banco"):
                    bits.append(f"Banco: {cuenta['banco']}")
                if cuenta.get("moneda"):
                    bits.append(f"Moneda: {cuenta['moneda']}")
                if cuenta.get("cbu"):
                    bits.append(f"CBU: {cuenta['cbu']}")
                if cuenta.get("alias"):
                    bits.append(f"Alias: {cuenta['alias']}")
                if bits:
                    etiqueta = "Cuenta principal" if cuenta.get("default") else "Cuenta"
                    parts.append(f"{etiqueta} para transferencia — " + "; ".join(bits) + ".")
        elif self.category == "faq":
            for item in data.get("items", []):
                q = (item.get("q") or "").strip()
                a = (item.get("a") or "").strip()
                if q or a:
                    parts.append(f"Pregunta: {q}\nRespuesta: {a}")
        else:
            # Para el resto, volcamos pares clave/valor simples si los hay.
            for k, v in data.items():
                if isinstance(v, (str, int, float)) and str(v).strip():
                    parts.append(f"{k}: {v}")

        return "\n\n".join(p for p in parts if p)

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "data": self.data or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Place(Base):
    """Lugar / excursión / punto de interés. Nace con imagen + Maps para Fase 2 (tarjetas)."""
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, default="atraccion", index=True)  # ver PLACE_CATEGORIES
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)     # URL (pegada o subida vía /upload-image)
    maps_url = Column(String, nullable=True)      # link de Google Maps
    address = Column(String, nullable=True)
    price_info = Column(String, nullable=True)    # texto libre, ej "Desde USD 50"
    status = Column(String, nullable=False, default="active", index=True)

    # Comercios amigos (acuerdos del hotel): contacto + descuento. Nullables para
    # no afectar a los lugares/excursiones existentes que no son comercios.
    phone = Column(String, nullable=True)         # teléfono de contacto
    whatsapp = Column(String, nullable=True)      # número de WhatsApp (solo dígitos / +54...)
    discount = Column(String, nullable=True)      # texto libre, ej "15% en efectivo"
    is_partner = Column(Boolean, nullable=False, default=False, index=True)  # comercio amigo / con acuerdo

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def doc_source(self) -> str:
        return f"kb-place-{self.id}"

    def to_ingest_text(self) -> str:
        parts = [self.name.strip()] if self.name else []
        if self.description:
            parts.append(self.description.strip())
        if self.is_partner:
            parts.append("Comercio amigo del hotel (con acuerdo para huéspedes).")
        if self.discount:
            parts.append(f"Descuento para huéspedes: {self.discount}")
        if self.address:
            parts.append(f"Dirección: {self.address}")
        if self.price_info:
            parts.append(f"Precio: {self.price_info}")
        if self.phone:
            parts.append(f"Teléfono: {self.phone}")
        if self.whatsapp:
            parts.append(f"WhatsApp: {self.whatsapp}")
        if self.maps_url:
            parts.append(f"Ubicación en Google Maps: {self.maps_url}")
        return "\n\n".join(p for p in parts if p)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "image_url": self.image_url,
            "maps_url": self.maps_url,
            "address": self.address,
            "price_info": self.price_info,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
            "discount": self.discount,
            "is_partner": bool(self.is_partner),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Crear SOLO estas tablas de forma explícita (mismo patrón que hotel.py), sin disparar
# el create_all global que dependería de que todos los modelos del proyecto estén importados.
Base.metadata.create_all(
    bind=engine,
    tables=[KnowledgeEntry.__table__, Place.__table__],
)


def _ensure_place_partner_columns() -> None:
    """Agrega de forma idempotente las columnas de 'comercio amigo' a `places`.

    `create_all` crea tablas nuevas pero NO altera tablas ya existentes. En entornos
    donde `places` ya estaba creada (ej. Render/Postgres), las columnas phone/whatsapp/
    discount/is_partner no existirían. Este ALTER las agrega si faltan. Compatible con
    SQLite (sin IF NOT EXISTS) y Postgres (con IF NOT EXISTS), atrapando errores por
    columna ya presente.
    """
    is_sqlite = engine.dialect.name == "sqlite"
    # (columna, tipo SQL). El tipo es genérico y válido en ambos motores.
    columns = [
        ("phone", "VARCHAR"),
        ("whatsapp", "VARCHAR"),
        ("discount", "VARCHAR"),
        ("is_partner", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE"),
    ]
    with engine.begin() as conn:
        for name, sql_type in columns:
            if is_sqlite:
                # SQLite no soporta ADD COLUMN IF NOT EXISTS: intentamos y si ya existe falla.
                try:
                    conn.execute(text(f"ALTER TABLE places ADD COLUMN {name} {sql_type}"))
                except Exception:
                    pass  # columna ya existe
            else:
                try:
                    conn.execute(
                        text(f"ALTER TABLE places ADD COLUMN IF NOT EXISTS {name} {sql_type}")
                    )
                except Exception as e:
                    logger.warning("No se pudo agregar columna a places",
                                   column=name, error=str(e))


_ensure_place_partner_columns()
