from sqlalchemy import create_engine, Column, String, DateTime, Integer, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.config import settings
from app.utils.timezone_utils import utcnow_naive

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String, unique=True, nullable=False, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="active")  # active/inactive
    uploaded_at = Column(DateTime, default=utcnow_naive)
    chunks_count = Column(Integer)
    file_size = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "filename": self.filename,
            "status": self.status,
            "uploaded_at": self.uploaded_at.isoformat(),
            "chunks_count": self.chunks_count,
            "file_size": self.file_size
        }

# En Render DATABASE_URL apunta a PostgreSQL; localmente usa SQLite.
# PostgreSQL de Render usa el scheme "postgres://" (legacy); SQLAlchemy requiere "postgresql://".
_db_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)

# PostgreSQL necesita pool_pre_ping para reconectar tras idle; SQLite no lo soporta.
_engine_kwargs = {"pool_pre_ping": True} if _db_url.startswith("postgresql") else {}
engine = create_engine(_db_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Crear tablas
Base.metadata.create_all(bind=engine)


def ensure_column(table: str, column: str, ddl_type: str) -> None:
    """Agrega una columna si la tabla ya existe sin ella (migración liviana e idempotente).

    create_all() crea tablas nuevas pero NO altera tablas existentes. Para columnas
    añadidas después (ej. leads.channel), este helper hace un ALTER TABLE solo si falta.
    Funciona en SQLite y PostgreSQL. Si la tabla aún no existe, no hace nada (create_all
    ya la habrá creado con la columna).
    """
    try:
        inspector = inspect(engine)
        if table not in inspector.get_table_names():
            return
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column in existing:
            return
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
    except Exception:
        # Una migración fallida no debe impedir el arranque; se loguea en otra capa.
        pass


def run_light_migrations() -> None:
    """Migraciones livianas de columnas agregadas tras el primer release.

    Se invoca desde el startup de la app (lifespan), cuando todos los modelos ya
    están importados y sus tablas creadas, para que el ALTER aplique a tablas reales.
    """
    ensure_column("leads", "channel", "VARCHAR(20)")
    ensure_column("chat_themes", "effect", "VARCHAR(20)")
    ensure_column("rooms", "status", "VARCHAR(20)")
    # Identidad 360°: vincular reserva → contacto + trazabilidad a la conversación.
    ensure_column("bookings", "contact_id", "INTEGER")
    ensure_column("bookings", "session_id", "VARCHAR(255)")
    # Habitación física asignada a la reserva (Fase 2: unidades numeradas).
    ensure_column("bookings", "room_unit_id", "INTEGER")
    # Origen de dos dimensiones (preparatorias para carga humana futura).
    ensure_column("bookings", "generated_by", "VARCHAR(20)")
    ensure_column("bookings", "created_by", "VARCHAR(120)")
    ensure_column("leads", "generated_by", "VARCHAR(20)")
    ensure_column("leads", "created_by", "VARCHAR(120)")
    # Canal de la conversación (web/whatsapp) para analíticas segmentadas.
    ensure_column("conversations", "channel", "VARCHAR(20)")
    # Perfil extensible del huésped (gustos, servicios, familia) en JSON.
    ensure_column("contacts", "preferences", "TEXT")
    # Promociones aplicables al precio: mínimo de noches para elegibilidad.
    ensure_column("promotions", "min_nights", "INTEGER")
    # Reserva con promo aplicada: nombre de la promo y precio sin descuento (trazabilidad).
    ensure_column("bookings", "promo_name", "VARCHAR(120)")
    ensure_column("bookings", "full_price_usd", "FLOAT")
    # Marcador de datos de demostración (generados por el seed) para poder limpiarlos solos.
    ensure_column("contacts", "is_demo", "BOOLEAN")
    ensure_column("bookings", "is_demo", "BOOLEAN")
    ensure_column("hotel_tickets", "is_demo", "BOOLEAN")
    ensure_column("leads", "is_demo", "BOOLEAN")
    ensure_column("conversations", "is_demo", "BOOLEAN")
    ensure_column("conversation_messages", "is_demo", "BOOLEAN")
    ensure_column("staff_members", "is_demo", "BOOLEAN")
    # Fase 4 — "empleado digital": área del staff + ciclo operativo del ticket.
    ensure_column("staff_members", "area", "VARCHAR(20)")
    ensure_column("hotel_tickets", "assigned_staff_id", "INTEGER")
    ensure_column("hotel_tickets", "assigned_area", "VARCHAR(20)")
    ensure_column("hotel_tickets", "origin", "VARCHAR(20)")
    ensure_column("hotel_tickets", "resolution_note", "TEXT")
    ensure_column("hotel_tickets", "resolved_by_staff_id", "INTEGER")
    ensure_column("hotel_tickets", "guest_validated", "INTEGER")
    # is_demo en hijos del restaurante/tickets (para que "Limpiar demo" sea explícito; el
    # reset-all ya los borra por tabla). Antes solo se borraban por cascada del padre.
    ensure_column("ticket_events", "is_demo", "BOOLEAN")
    ensure_column("order_items", "is_demo", "BOOLEAN")
    ensure_column("voucher_items", "is_demo", "BOOLEAN")
    # Centro del Empleado Digital — config del "parte de fin de día" por agente (Etapa 2).
    ensure_column("agents", "daily_report", "TEXT")
    # Fase A (flujos): tipo de skill — "flow" (flujo principal) | "function" (adosable).
    ensure_column("skills", "kind", "VARCHAR(20)")
    _backfill("skills", "kind", "function")
    # Fase E (entrenamiento estructurado): categoría + campos + estado por documento.
    ensure_column("training_documents", "category", "VARCHAR(30)")
    ensure_column("training_documents", "data", "TEXT")
    ensure_column("training_documents", "active", "BOOLEAN")
    ensure_column("training_documents", "is_default", "BOOLEAN")
    _backfill("training_documents", "active", "1")
    # Backfill: las filas creadas antes de agregar la columna quedan en NULL.
    _backfill("rooms", "status", "active")
    _backfill("staff_members", "area", "general")
    _backfill("hotel_tickets", "origin", "guest")
    # Conversaciones previas a la columna: asumimos canal web (no había WhatsApp).
    _backfill("conversations", "channel", "web")
    # Tablas del restaurante (menu/pedidos/folio): garantizar creación con todas las
    # dependencias ya importadas (las FKs a contacts/bookings necesitan esas tablas).
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    # hotel_tickets.booking_id pasó a nullable (pedidos de visitante sin reserva).
    # Cubrimos ambos motores: SQLite recrea la tabla; Postgres (Render) usa ALTER COLUMN.
    _make_nullable_sqlite("hotel_tickets", "booking_id")
    _make_nullable_postgres("hotel_tickets", "booking_id")


def _make_nullable_sqlite(table: str, column: str) -> None:
    """Vuelve nullable una columna NOT NULL en SQLite (que no soporta ALTER COLUMN).

    Idempotente: si la columna ya es nullable o la tabla no existe, no hace nada.
    Recrea la tabla con el esquema actual del modelo (que ya define la columna nullable)
    y copia los datos. Solo aplica a SQLite; en Postgres se usaría ALTER COLUMN.
    """
    try:
        if engine.dialect.name != "sqlite":
            return
        inspector = inspect(engine)
        if table not in inspector.get_table_names():
            return
        cols = inspector.get_columns(table)
        target = next((c for c in cols if c["name"] == column), None)
        if not target or target.get("nullable", True):
            return  # ya es nullable
        # Recrear la tabla con el esquema del modelo (booking_id ya es nullable).
        tbl = Base.metadata.tables.get(table)
        if tbl is None:
            return
        col_names = ", ".join(c["name"] for c in cols)
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {table} RENAME TO {table}_old'))
            tbl.create(bind=conn)
            conn.execute(text(f'INSERT INTO {table} ({col_names}) SELECT {col_names} FROM {table}_old'))
            conn.execute(text(f'DROP TABLE {table}_old'))
    except Exception:
        # Una migración fallida no debe impedir el arranque.
        pass


def _make_nullable_postgres(table: str, column: str) -> None:
    """Vuelve nullable una columna NOT NULL en PostgreSQL (Render) con ALTER COLUMN.

    Idempotente: si la columna ya es nullable o la tabla no existe, no hace nada.
    Solo aplica a Postgres (en SQLite usamos _make_nullable_sqlite, que recrea la tabla).
    """
    try:
        if not engine.dialect.name.startswith("postgres"):
            return
        inspector = inspect(engine)
        if table not in inspector.get_table_names():
            return
        target = next((c for c in inspector.get_columns(table) if c["name"] == column), None)
        if not target or target.get("nullable", True):
            return  # ya es nullable
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL'))
    except Exception:
        # Una migración fallida no debe impedir el arranque.
        pass


def _backfill(table: str, column: str, value: str) -> None:
    """Asigna `value` a las filas donde `column` quedó NULL (tras un ALTER ADD COLUMN)."""
    try:
        inspector = inspect(engine)
        if table not in inspector.get_table_names():
            return
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing:
            return
        with engine.begin() as conn:
            conn.execute(
                text(f"UPDATE {table} SET {column} = :v WHERE {column} IS NULL"),
                {"v": value},
            )
    except Exception:
        pass


def get_db():
    """Dependency para obtener sesión de DB"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
