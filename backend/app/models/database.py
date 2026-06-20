from sqlalchemy import create_engine, Column, String, DateTime, Integer, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.config import settings

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String, unique=True, nullable=False, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="active")  # active/inactive
    uploaded_at = Column(DateTime, default=datetime.now)
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


def get_db():
    """Dependency para obtener sesión de DB"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
