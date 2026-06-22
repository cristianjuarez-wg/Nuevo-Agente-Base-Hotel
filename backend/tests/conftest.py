import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Usar BD en memoria para tests (nunca toca documents.db)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("FLIGHTAPI_API_KEY", "test-flight-key")
os.environ.setdefault("SQLITE_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CHROMA_PERSIST_DIRECTORY", "/tmp/chroma_test")

# Importar TODOS los modelos antes de tocar app.main: algunos módulos (ej. hotel.py)
# llaman create_all sobre tablas con FK a otras (staff_members) que solo resuelven si
# el modelo ya está registrado. `staff` debe ir ANTES que `hotel` (que referencia
# staff_members) — por eso se importa explícito primero, antes del barrido alfabético.
import importlib
import pkgutil
import app.models.staff  # noqa: F401 — registra staff_members antes que hotel.py
import app.models as _models_pkg
for _mod in pkgutil.iter_modules(_models_pkg.__path__):
    importlib.import_module(f"app.models.{_mod.name}")

from app.main import app
from app.models.database import Base, get_db

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
