from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    # API Keys
    OPENAI_API_KEY: str
    FLIGHTAPI_API_KEY: Optional[str] = None
    WEATHER_API_KEY: Optional[str] = None

    # CORS — en producción usar dominios específicos, ej: "https://app.midominio.com,https://admin.midominio.com"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    
    # Base de datos: SQLite local por defecto; en Render se sobreescribe con PostgreSQL.
    DATABASE_URL: str = "sqlite:///./hotel.db"

    # Alias legacy — apunta a DATABASE_URL para no romper imports existentes.
    SQLITE_DATABASE_URL: str = "sqlite:///./hotel.db"
    
    # ChromaDB
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"
    CHROMA_COLLECTION_NAME: str = "travel_documents"
    
    # OpenAI Config
    OPENAI_MODEL: str = "gpt-4o"  # Modelo principal para generación de respuestas
    OPENAI_MODEL_CLASSIFIER: str = "gpt-4o-mini"  # Modelo económico para clasificación de intención
    OPENAI_MODEL_FAST: str = "gpt-4o-mini"  # Modelo rápido para tareas auxiliares (reemplaza gpt-3.5-turbo deprecado)
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_TEMPERATURE: float = 0.3
    
    # RAG Config
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 8
    
    # Agent Config
    AGENT_PROFILE_PATH: str = "./data/agent_profiles/turismo.json"
    GEOGRAPHY_DATA_PATH: str = "./data/geography.json"

    # Arquitectura del agente sobre el OpenAI Agents SDK (camino de producción).
    # En P4 se retiraron los orquestadores caseros y los clasificadores legacy, por lo
    # que el SDK es el único camino: chat() delega siempre en estos orquestadores.
    # Los flags se conservan como documentación de la arquitectura activa y como punto
    # único para tracing/diagnóstico; ya no alternan entre dos implementaciones.
    USE_AGENTS_SDK_PREVENTA: bool = True   # agent_sdk_orchestrator (pre-venta)
    USE_AGENTS_SDK_POSTVENTA: bool = True  # postsale_sdk_orchestrator (post-venta)
    USE_AGENTS_SDK_TRIAGE: bool = True     # triage_sdk_orchestrator (ruteo pre/post/casual)

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"  # URL base del backend
    
    # Security & Rate Limiting
    MAX_FILE_SIZE_MB: int = 10
    RATE_LIMIT_ENABLED: bool = True
    
    # Retry & Circuit Breaker
    OPENAI_MAX_RETRIES: int = 3
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
