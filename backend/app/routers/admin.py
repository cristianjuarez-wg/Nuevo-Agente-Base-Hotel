from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.schemas import (
    AgentConfigUpdate,
    AgentConfigResponse,
    SystemMetrics,
    CircuitBreakerStatus
)
from app.core.agent_profile import profile_manager
from app.core.circuit_breaker import openai_circuit_breaker, vector_store_circuit_breaker
from app.services.agent_service import agent_service
from app.services.vector_store import get_vector_store
# from app.services.pattern_manager import pattern_manager  # REMOVED: Pattern approval system eliminated
from app.core.logging_config import get_logger
from app.config import settings
import time
from datetime import datetime

logger = get_logger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Variable global para tracking de uptime
_start_time = time.time()

@router.get("/config")
async def get_current_config():
    """Obtiene la configuración actual del agente"""
    try:
        logger.debug("Getting current agent config")
        
        profile_info = profile_manager.get_profile_info()
        
        config = {
            "agent_profile": profile_info,
            "model_config": {
                "model": settings.OPENAI_MODEL,
                "temperature": settings.OPENAI_TEMPERATURE,
                "max_retries": settings.OPENAI_MAX_RETRIES
            },
            "rag_config": {
                "chunk_size": settings.CHUNK_SIZE,
                "chunk_overlap": settings.CHUNK_OVERLAP,
                "top_k_results": settings.TOP_K_RESULTS
            },
            "security_config": {
                "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
                "rate_limit_enabled": settings.RATE_LIMIT_ENABLED
            }
        }
        
        return config
    
    except Exception as e:
        logger.error("Error getting config", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo configuración: {str(e)}"
        )

@router.post("/config", response_model=AgentConfigResponse)
async def update_agent_config(config_update: AgentConfigUpdate):
    """Actualiza la configuración del agente"""
    try:
        logger.info("Updating agent config", updates=config_update.dict(exclude_none=True))
        
        # Por ahora, solo devolvemos la configuración actual
        # En una implementación completa, aquí se actualizaría la configuración
        current_config = profile_manager.get_profile_info()
        
        # TODO: Implementar actualización real de configuración
        # Esto requeriría modificar el profile_manager para permitir updates dinámicos
        
        return AgentConfigResponse(
            success=True,
            message="Configuración actualizada exitosamente (simulado)",
            current_config=current_config
        )
    
    except Exception as e:
        logger.error("Error updating config", error=str(e))
        return AgentConfigResponse(
            success=False,
            message=f"Error actualizando configuración: {str(e)}",
            current_config={}
        )

@router.get("/metrics", response_model=SystemMetrics)
async def get_system_metrics():
    """Obtiene métricas del sistema"""
    try:
        logger.debug("Getting system metrics")
        
        # Circuit breaker states
        openai_cb_state = openai_circuit_breaker.get_state()
        vector_cb_state = vector_store_circuit_breaker.get_state()
        
        # Agent stats
        agent_stats = agent_service.get_service_stats()
        
        # Vector store stats
        vector_store = get_vector_store()
        vs_stats = vector_store.get_collection_stats()
        
        # Uptime
        uptime_seconds = time.time() - _start_time
        
        return SystemMetrics(
            openai_circuit_breaker=CircuitBreakerStatus(**openai_cb_state),
            vector_store_circuit_breaker=CircuitBreakerStatus(**vector_cb_state),
            active_sessions=agent_stats.get("active_sessions", 0),
            total_documents=vs_stats.get("total_documents", 0),
            uptime_seconds=uptime_seconds
        )
    
    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo métricas: {str(e)}"
        )

@router.post("/circuit-breaker/reset/{service}")
async def reset_circuit_breaker(service: str):
    """Resetea un circuit breaker específico"""
    try:
        logger.info("Resetting circuit breaker", service=service)
        
        if service == "openai":
            openai_circuit_breaker.reset()
            message = "Circuit breaker de OpenAI reseteado"
        elif service == "vector_store":
            vector_store_circuit_breaker.reset()
            message = "Circuit breaker de Vector Store reseteado"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Servicio desconocido: {service}. Opciones: 'openai', 'vector_store'"
            )
        
        logger.info("Circuit breaker reset successful", service=service)
        
        return {
            "success": True,
            "message": message,
            "service": service,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting circuit breaker", service=service, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error reseteando circuit breaker: {str(e)}"
        )

@router.get("/logs/recent")
async def get_recent_logs():
    """Obtiene logs recientes del sistema"""
    try:
        # Esta es una implementación básica
        # En producción, se conectaría a un sistema de logs centralizado
        
        return {
            "message": "Endpoint de logs en desarrollo",
            "note": "En producción, aquí se mostrarían los logs recientes del sistema",
            "suggestion": "Usar herramientas como ELK Stack o similar para logs en producción"
        }
    
    except Exception as e:
        logger.error("Error getting logs", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo logs: {str(e)}"
        )

@router.get("/system/status")
async def get_system_status():
    """Obtiene estado general del sistema"""
    try:
        logger.debug("Getting system status")
        
        # Verificar componentes principales
        components = {}
        
        # Agent service
        try:
            agent_stats = agent_service.get_service_stats()
            components["agent_service"] = {
                "status": "healthy",
                "active_sessions": agent_stats.get("active_sessions", 0)
            }
        except Exception as e:
            components["agent_service"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Vector store
        try:
            vector_store = get_vector_store()
            is_healthy, msg = vector_store.health_check()
            components["vector_store"] = {
                "status": "healthy" if is_healthy else "unhealthy",
                "message": msg
            }
        except Exception as e:
            components["vector_store"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Profile manager
        try:
            profile_info = profile_manager.get_profile_info()
            components["profile_manager"] = {
                "status": "healthy",
                "current_profile": profile_info.get("profile_name")
            }
        except Exception as e:
            components["profile_manager"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Determinar estado general
        unhealthy_components = [k for k, v in components.items() if v["status"] != "healthy"]
        
        if not unhealthy_components:
            overall_status = "healthy"
        elif len(unhealthy_components) < len(components):
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        return {
            "overall_status": overall_status,
            "components": components,
            "unhealthy_components": unhealthy_components,
            "uptime_seconds": time.time() - _start_time,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("Error getting system status", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estado del sistema: {str(e)}"
        )

# ==================== PATTERN MANAGEMENT ENDPOINTS ====================
# REMOVED: Pattern approval system eliminated (2025-11-08)
# Reason: Hybrid Intent Classifier already handles greetings/farewells efficiently
# - Uses local dataset first (free, instant)
# - Falls back to GPT only when needed (~$0.15/month)
# - Manual approval was redundant and unused
# Dataset maintained: data/saludos_despedidas.csv (200 greetings + 220 farewells)
