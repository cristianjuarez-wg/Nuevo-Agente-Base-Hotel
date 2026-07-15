from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Mensaje del usuario")
    session_id: str = Field(..., min_length=8, max_length=64, description="ID único de sesión")
    language: str = Field("es", description="Idioma de respuesta: es | en | pt | fr")

    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError('El mensaje no puede estar vacío')
        return v.strip()

    @validator('language')
    def validate_language(cls, v):
        v = (v or "es").lower()
        return v if v in {"es", "en", "pt", "fr"} else "es"
    
    @validator('session_id')
    def validate_session_id(cls, v):
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]{8,64}$', v):
            raise ValueError('Session ID debe contener solo letras, números, guiones y guiones bajos')
        return v

class GeographyAnalysis(BaseModel):
    continent: Optional[str] = None
    countries: List[str] = []
    cities: List[str] = []
    requires_mapping: bool = False
    suggested_countries: Optional[List[str]] = None
    continents_mentioned: Optional[List[str]] = None
    
    class Config:
        extra = "allow"  # Permite campos extra sin validar

class SessionInfo(BaseModel):
    exists: bool
    created_at: Optional[str] = None
    last_activity: Optional[str] = None
    message_count: Optional[int] = 0
    history_length: Optional[int] = 0

class ChatResponse(BaseModel):
    response: str
    has_context: bool = True
    geography_analysis: Optional[Dict] = None  # Más flexible
    sources_used: Optional[int] = None
    session_info: Optional[SessionInfo] = None
    processing_time: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    error: bool = False
    error_type: Optional[str] = None
    # Observabilidad: qué tools llamó el agente este turno y por qué agente pasó. El audit ya
    # los registraba, pero el payload los descartaba (salía None). Ahora se exponen.
    tools_used: Optional[List[str]] = None
    agent_key: Optional[str] = None
    
    class Config:
        extra = "allow"  # Permite campos extra sin validar

class DocumentUploadResponse(BaseModel):
    filename: str
    chunks_created: int
    status: str
    message: str
    file_size: Optional[int] = None
    processing_time: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[str]
    total: int

class DocumentDeleteResponse(BaseModel):
    filename: str
    deleted_count: int
    message: str
    collection_size: int

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"

class ServiceHealth(BaseModel):
    healthy: bool
    message: str
    circuit_breaker: Optional[Dict[str, Any]] = None

class HealthResponse(BaseModel):
    status: HealthStatus
    vector_store: ServiceHealth
    geography_service: Optional[Dict[str, Any]] = None
    agent_profile: Optional[Dict[str, Any]] = None
    documents_count: int
    timestamp: datetime = Field(default_factory=datetime.now)

class ClearHistoryResponse(BaseModel):
    success: bool
    messages_cleared: int
    message: str
    session_id: str

class GreetingResponse(BaseModel):
    greeting: str
    agent_name: str
    capabilities: List[str]
    conversation_starters: List[str]

class AgentStatsResponse(BaseModel):
    active_sessions: int
    total_messages: int
    agent_profile: Dict[str, Any]
    openai_config: Dict[str, Any]
    uptime: Optional[str] = None

class DestinationsResponse(BaseModel):
    documents_loaded: int
    sources: List[str]
    continents_available: List[str]
    countries_available: int
    sample_countries: List[str]

class ErrorResponse(BaseModel):
    error: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: Optional[str] = None

# Modelos para validación de archivos
class FileValidation(BaseModel):
    is_valid: bool
    message: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None

# Modelos para configuración del agente
class AgentConfigUpdate(BaseModel):
    profile_name: Optional[str] = None
    agent_name: Optional[str] = None
    greeting_message: Optional[str] = None
    no_info_response: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    
    @validator('temperature')
    def validate_temperature(cls, v):
        if v is not None and (v < 0.0 or v > 2.0):
            raise ValueError('Temperature debe estar entre 0.0 y 2.0')
        return v

class AgentConfigResponse(BaseModel):
    success: bool
    message: str
    current_config: Dict[str, Any]

# Modelos para métricas y estadísticas
class CircuitBreakerStatus(BaseModel):
    state: str
    failure_count: int
    failure_threshold: int
    last_failure_time: Optional[str] = None
    timeout_seconds: int

class SystemMetrics(BaseModel):
    openai_circuit_breaker: CircuitBreakerStatus
    vector_store_circuit_breaker: CircuitBreakerStatus
    active_sessions: int
    total_documents: int
    uptime_seconds: Optional[float] = None

# Modelos para búsqueda y filtrado
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    n_results: Optional[int] = Field(5, ge=1, le=20)
    min_similarity: Optional[float] = Field(0.3, ge=0.0, le=1.0)

class SearchResult(BaseModel):
    text: str
    metadata: Dict[str, Any]
    similarity: float
    source: str

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total_found: int
    query: str
    processing_time: str

class DocumentWithStatus(BaseModel):
    id: int
    doc_id: str
    filename: str
    status: str
    uploaded_at: str
    chunks_count: int
    file_size: Optional[int] = None

class DocumentListWithStatusResponse(BaseModel):
    documents: List[DocumentWithStatus]
    total: int
    active_count: int
    inactive_count: int

class DocumentStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|inactive)$")
