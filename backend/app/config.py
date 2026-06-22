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

    # Almacenamiento de imágenes subidas desde el backoffice (repositorio de conocimiento).
    # En Render apuntar al disco persistente: MEDIA_DIR=/data/uploads_img
    MEDIA_DIR: str = "./uploads_img"
    
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
    # El agente del hotel delega siempre en los orquestadores del hotel
    # (hotel_sdk_orchestrator / hotel_postsale_orchestrator) con ruteo por
    # triage_sdk_orchestrator. Flag de documentación de la arquitectura activa.
    USE_AGENTS_SDK_TRIAGE: bool = True     # triage_sdk_orchestrator (ruteo pre/post/casual)

    # WhatsApp (Twilio Sandbox) — canal opcional para la demo.
    # Si las credenciales no están, el webhook queda inactivo y el resto del backend
    # arranca normal (los defaults None evitan romper el entorno local).
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"  # número del sandbox de Twilio
    WHATSAPP_MAX_ROOM_CARDS: int = 3  # cuántas habitaciones (con foto) enviar por WhatsApp

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"  # URL base del backend
    LANDING_URL: str = "http://localhost:5174"  # URL del sitio público (para links del agente)
    
    # Security & Rate Limiting
    MAX_FILE_SIZE_MB: int = 10
    RATE_LIMIT_ENABLED: bool = True
    # Límite por IP en el endpoint del agente (protección contra abuso / gasto descontrolado).
    RATE_LIMIT_PER_MINUTE: int = 20
    RATE_LIMIT_PER_HOUR: int = 300
    
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
        # Ignorar variables de entorno desconocidas en vez de fallar el arranque.
        # Evita que un flag viejo/huérfano en el entorno (ej. en Render) tumbe el
        # backend tras quitar un setting del modelo.
        extra = "ignore"

settings = Settings()
