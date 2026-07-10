from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from app.routers import chat, documents, admin, leads, analytics, reservations, hotel_tickets, usage, knowledge, whatsapp, instagram, promotions, chat_themes, exchange_rate, rooms_admin, contacts, staff, management_knowledge, demo, restaurant, kanban, conversations, checkin, agents, business_profile
from app.config import settings
from app.core.security.rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from app.models.schemas import HealthResponse, HealthStatus, ServiceHealth
from app.services.vector_store import get_vector_store
from app.services.agent_service import agent_service
from app.core.observability.logging_config import setup_logging, get_logger
from app.core.agent_profile import profile_manager
import time
from datetime import datetime

# Configurar logging al inicio
setup_logging()
logger = get_logger(__name__)

# Variable global para tracking de inicio
app_start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación"""
    # Startup
    logger.info("🚀 Hampton Bariloche Concierge API starting up",
               environment="production" if not settings.DEBUG else "development",
               log_level=settings.LOG_LEVEL)
    
    try:
        # Migraciones livianas (columnas agregadas tras el primer release).
        from app.models.database import run_light_migrations
        run_light_migrations()

        # Centro del Empleado Digital: crear la tabla `agents` y sembrar los 3 agentes
        # de fábrica (Aura/Asesor/Operaciones) de forma idempotente.
        from app.models import agent as _agent_model  # noqa: F401  (registra la tabla)
        from app.models import training_document as _training_doc_model  # noqa: F401
        from app.models import skill as _skill_model  # noqa: F401
        from app.models import centro_config as _centro_config_model  # noqa: F401
        from app.models import business_profile as _business_profile_model  # noqa: F401
        from app.models.database import SessionLocal
        from app.services.agent_directory import seed_agents
        from app.services.skill_service import seed_skills
        from app.services.training_service import seed_training_defaults
        from app.services import business_profile_service
        _seed_db = SessionLocal()
        try:
            seed_agents(_seed_db)
            seed_skills(_seed_db)
            seed_training_defaults(_seed_db)
            # Identidad del negocio (Fase 1): siembra id=1 con los valores del Hampton
            # si no existe. Paridad: el agente se comporta igual con estos defaults.
            business_profile_service.ensure_seeded(_seed_db)
        finally:
            _seed_db.close()

        # Verificar componentes críticos
        vector_store = get_vector_store()
        doc_count = len(vector_store.get_all_sources())
        logger.info("Vector store initialized", documents_count=doc_count)
        
        profile_info = profile_manager.get_profile_info()
        logger.info("Agent profile loaded", 
                   profile_name=profile_info.get("profile_name"),
                   agent_name=profile_info.get("agent_name"))
        
        logger.info("✅ Hampton Bariloche Concierge API startup completed successfully")
        
    except Exception as e:
        logger.error("❌ Startup error", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Hampton Bariloche Concierge API shutting down")

# Crear aplicación FastAPI
app = FastAPI(
    title="Hampton Bariloche Concierge API",
    description="API del concierge virtual del Hampton by Hilton Bariloche (RAG + agente)",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Rate limiter por IP (slowapi). Necesita registrarse en app.state.
app.state.limiter = limiter

# Middleware CORS — orígenes configurados vía ALLOWED_ORIGINS en .env
_cors_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers globales
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Maneja errores de validación de Pydantic"""
    logger.warning("Validation error",
                  path=request.url.path,
                  method=request.method,
                  errors=exc.errors())
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Datos de entrada inválidos",
            "details": exc.errors(),
            "message": "Por favor, verifica los datos enviados y vuelve a intentar."
        }
    )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Maneja el límite de peticiones por IP (429) con mensaje en español."""
    logger.warning("Rate limit exceeded",
                  path=request.url.path,
                  client_ip=request.client.host if request.client else None,
                  detail=str(exc.detail))

    return JSONResponse(
        status_code=429,
        content={
            "error": "Demasiadas solicitudes",
            "message": "Estás enviando mensajes muy rápido. Por favor, esperá un momento e intentá de nuevo.",
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Maneja excepciones HTTP"""
    logger.warning("HTTP exception",
                  path=request.url.path,
                  method=request.method,
                  status_code=exc.status_code,
                  detail=exc.detail)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": f"Error {exc.status_code}",
            # `detail` es la clave estándar de FastAPI y la que lee el frontend;
            # `message` se mantiene por compatibilidad con consumidores previos.
            "detail": exc.detail,
            "message": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Maneja excepciones no capturadas"""
    logger.error("Unhandled exception",
                path=request.url.path,
                method=request.method,
                error=str(exc),
                error_type=type(exc).__name__)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "message": "Ocurrió un error inesperado. Por favor, contacta al soporte si el problema persiste.",
            "timestamp": datetime.now().isoformat()
        }
    )

# Middleware para logging de requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log de todas las requests"""
    start_time = time.time()
    
    # Procesar request
    response = await call_next(request)
    
    # Log de la request
    process_time = time.time() - start_time
    
    logger.info("HTTP request",
               method=request.method,
               path=request.url.path,
               status_code=response.status_code,
               process_time=f"{process_time:.3f}s",
               client_ip=request.client.host if request.client else None)
    
    # Agregar header de tiempo de procesamiento
    response.headers["X-Process-Time"] = str(process_time)
    
    return response

# Incluir routers
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(leads.router)
app.include_router(kanban.router)
app.include_router(analytics.router)
app.include_router(reservations.router)
app.include_router(hotel_tickets.router)
app.include_router(usage.router)
app.include_router(knowledge.router)
app.include_router(promotions.router)
app.include_router(chat_themes.router)
app.include_router(exchange_rate.router)
app.include_router(rooms_admin.router)
app.include_router(contacts.router)
app.include_router(staff.router)
app.include_router(management_knowledge.router)
app.include_router(demo.router)
app.include_router(restaurant.router)
app.include_router(whatsapp.router)
app.include_router(instagram.router)
app.include_router(conversations.router)
app.include_router(checkin.router)
app.include_router(agents.router)
app.include_router(business_profile.router)

# Montar directorio de vouchers como archivos estáticos
vouchers_dir = Path(__file__).parent.parent / "vouchers"
vouchers_dir.mkdir(exist_ok=True)
app.mount("/vouchers", StaticFiles(directory=str(vouchers_dir)), name="vouchers")

# Montar directorio de medios (imágenes del repositorio de conocimiento).
# En Render, MEDIA_DIR apunta al disco persistente (/data/uploads_img).
media_dir = Path(settings.MEDIA_DIR)
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

# Endpoints principales
@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint principal"""
    try:
        logger.debug("Health check requested")
        
        # Verificar vector store
        vector_store = get_vector_store()
        vs_healthy, vs_msg = vector_store.health_check()
        doc_count = len(vector_store.get_all_sources())
        
        # Verificar agent service
        try:
            agent_stats = agent_service.get_service_stats()
            agent_healthy = True
            agent_msg = f"Agent funcionando. Sesiones activas: {agent_stats.get('active_sessions', 0)}"
        except Exception as e:
            agent_healthy = False
            agent_msg = f"Agent error: {str(e)}"
        
        # Verificar profile manager
        try:
            profile_info = profile_manager.get_profile_info()
            profile_healthy = True
            profile_msg = f"Perfil cargado: {profile_info.get('profile_name')}"
        except Exception as e:
            profile_healthy = False
            profile_msg = f"Profile error: {str(e)}"
        
        # Determinar estado general
        all_healthy = vs_healthy and agent_healthy and profile_healthy
        
        if all_healthy:
            status = HealthStatus.HEALTHY
        elif vs_healthy:  # Al menos vector store funciona
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        
        return HealthResponse(
            status=status,
            vector_store=ServiceHealth(
                healthy=vs_healthy,
                message=vs_msg
            ),
            geography_service={
                "healthy": True,  # Geography service es local, siempre funciona
                "continents_count": len(profile_manager.current_profile.get("capabilities", [])),
                "message": "Servicio de geografía funcionando"
            },
            agent_profile={
                "healthy": profile_healthy,
                "message": profile_msg
            },
            documents_count=doc_count
        )
    
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        
        return HealthResponse(
            status=HealthStatus.UNHEALTHY,
            vector_store=ServiceHealth(
                healthy=False,
                message=f"Error en health check: {str(e)}"
            ),
            documents_count=0
        )

@app.get("/info")
async def get_app_info():
    """Información general de la aplicación"""
    uptime_seconds = time.time() - app_start_time
    
    return {
        "name": "Hampton Bariloche Concierge",
        "version": "1.1.0",
        "description": "Concierge virtual del Hampton by Hilton Bariloche con sistema RAG",
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": f"{uptime_seconds/3600:.1f} horas",
        "environment": "development" if settings.DEBUG else "production",
        "features": [
            "Sistema RAG con ChromaDB",
            "Análisis geográfico inteligente",
            "Procesamiento de PDFs",
            "Circuit breakers y retry logic",
            "Logging estructurado",
            "API REST completa"
        ],
        "endpoints": {
            "health": "/",
            "docs": "/docs",
            "chat": "/api/chat",
            "documents": "/api/documents",
            "admin": "/api/admin",
            "leads": "/api/leads",
            "analytics": "/api/analytics",
            "kanban": "/api/kanban"
        }
    }

@app.get("/version")
async def get_version():
    """Versión de la aplicación"""
    return {
        "version": "1.1.0",
        "build_date": "2024-10-14",
        "python_version": "3.11+",
        "framework": "FastAPI",
        "ai_model": settings.OPENAI_MODEL
    }

# Endpoint para métricas básicas (compatible con Prometheus)
@app.get("/metrics")
async def get_metrics():
    """Métricas básicas en formato texto"""
    try:
        # Obtener estadísticas
        vector_store = get_vector_store()
        doc_count = len(vector_store.get_all_sources())
        
        agent_stats = agent_service.get_service_stats()
        active_sessions = agent_stats.get("active_sessions", 0)
        
        uptime = time.time() - app_start_time
        
        # Formato básico de métricas
        metrics = f"""# HELP travel_agent_documents_total Total documents in vector store
# TYPE travel_agent_documents_total gauge
travel_agent_documents_total {doc_count}

# HELP travel_agent_active_sessions Active chat sessions
# TYPE travel_agent_active_sessions gauge
travel_agent_active_sessions {active_sessions}

# HELP travel_agent_uptime_seconds Application uptime in seconds
# TYPE travel_agent_uptime_seconds counter
travel_agent_uptime_seconds {uptime}
"""
        
        return Response(content=metrics, media_type="text/plain")
    
    except Exception as e:
        logger.error("Error generating metrics", error=str(e))
        return Response(content="# Error generating metrics\n", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Hampton Bariloche Concierge API",
               host=settings.HOST,
               port=settings.PORT,
               debug=settings.DEBUG)
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None  # Usar nuestro logging personalizado
    )
