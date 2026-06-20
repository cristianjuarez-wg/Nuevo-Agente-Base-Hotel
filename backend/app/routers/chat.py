from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ClearHistoryResponse,
    GreetingResponse,
    AgentStatsResponse,
    DestinationsResponse,
    GeographyAnalysis,
    SessionInfo
)
from app.models.database import get_db
from app.services.agent_service import agent_service
from app.services.rag_service import rag_service
from app.services.metrics_service import metrics_service
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.rate_limit import limiter, CHAT_RATE_LIMIT
import asyncio
import time
from datetime import datetime

CHAT_TIMEOUT_SECONDS = 60

# Marca de arranque del proceso, para reportar uptime en /stats.
_SERVICE_START = time.monotonic()


def _format_uptime(seconds: float) -> str:
    """Formatea un lapso en segundos como 'Xd Yh Zm Ws' (omitiendo las unidades en 0)."""
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Imagen de respaldo cuando una habitación no tiene foto cargada.
_ROOM_FALLBACK_IMG = "/fotos/habitacion-vista-lago.jpg"


def _date_picker_card() -> dict:
    """Tarjeta de selección de fechas + huéspedes que el front renderiza como controles."""
    return {
        "type": "date_picker",
        "title": "Elegí las fechas de tu estadía",
        "action": {
            "kind": "send_message",
            "label": "Ver disponibilidad",
            # El front compone el message real con las fechas elegidas.
        },
    }


# Señales en la respuesta del agente de que está pidiendo fechas/huéspedes.
_DATE_REQUEST_HINTS = (
    "fecha", "check-in", "check in", "checkin", "qué día", "que dia",
    "cuándo", "cuando", "disponibilidad para",
)


def _should_offer_datepicker(response_text: str, tools_used: list, has_room_cards: bool) -> bool:
    """Decide si adjuntar el selector de fechas.

    Lo ofrecemos cuando el agente está PIDIENDO fechas: no mostró habitaciones en este
    turno (no llamó a consultar_disponibilidad) y su texto menciona fechas/check-in.
    Así el usuario elige con el picker en vez de tipear.
    """
    if has_room_cards:
        return False
    if "consultar_disponibilidad" in (tools_used or []):
        return False
    text = (response_text or "").lower()
    return any(h in text for h in _DATE_REQUEST_HINTS)


def _build_room_cards(rooms_offered: list) -> list:
    """Arma tarjetas de habitación a partir de las habitaciones que ofreció la tool.

    Determinístico: sale de los datos reales de disponibilidad, no del LLM. Cada tarjeta
    lleva lo necesario para renderizar en el chat (imagen, tipo, precios, capacidad) y la
    acción 'reservar' (que el front convierte en un mensaje al chat).
    """
    cards = []
    for r in rooms_offered or []:
        images = r.get("images") or []
        image = images[0] if images else _ROOM_FALLBACK_IMG
        cards.append({
            "type": "room",
            "title": r.get("room_type"),
            "description": r.get("description"),
            "image": image,
            "price_usd": r.get("total_price_usd"),
            "price_ars": r.get("total_price_ars"),
            "price_usd_night": r.get("base_price_usd"),
            "nights": r.get("nights"),
            "capacity": r.get("capacity"),
            "bed_config": r.get("bed_config"),
            "view": r.get("view"),
            "units_available": r.get("units_available"),
            "action": {
                "kind": "send_message",
                "label": "Reservar esta habitación",
                "message": f"Quiero reservar la habitación {r.get('room_type')}",
            },
        })
    return cards

@router.post("/message", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
async def send_message(request: Request, chat_request: ChatRequest, db: Session = Depends(get_db)):
    """Envía mensaje al agente y obtiene respuesta"""
    start_time = time.time()
    
    logger.info("Chat message received",
               session_id=chat_request.session_id,
               message_length=len(chat_request.message))
    
    try:
        # Procesar mensaje con el agente (timeout para evitar esperas indefinidas)
        try:
            result = await asyncio.wait_for(
                agent_service.chat(db, chat_request.message, chat_request.session_id),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("Chat message timed out",
                        session_id=chat_request.session_id,
                        timeout_seconds=CHAT_TIMEOUT_SECONDS)
            return ChatResponse(
                response="Lo siento, la respuesta tardó demasiado. Por favor, intentá de nuevo.",
                has_context=False,
                geography_analysis={},
                error=True,
                error_type="timeout",
                processing_time=f"{CHAT_TIMEOUT_SECONDS}s",
            )
        
        # 🆕 FIX: Corregir nombres de paquetes truncados o incompletos
        import re
        document_sources = result.get("document_sources", [])
        response_text = result["response"]
        
        if document_sources:
            for source in document_sources:
                # Obtener nombre completo del documento
                package_name = source.get("document", "").replace(".pdf", "").replace(".PDF", "")
                
                # Solo procesar paquetes multi-país o con guión
                if " y " in package_name or " - " in package_name:
                    # Extraer la parte de países (antes del guión)
                    countries_part = package_name.split(" - ")[0] if " - " in package_name else package_name
                    
                    # Extraer todos los países del nombre
                    countries = []
                    for part in countries_part.split(" y "):
                        for country in part.split(","):
                            country = country.strip()
                            # Filtrar palabras que no son países
                            if country and not any(word in country.lower() for word in ["todo", "incluido", "desde"]):
                                countries.append(country)
                    
                    # Buscar patrones truncados con CUALQUIERA de los países
                    for country in countries:
                        # Patrón 1: "**País y -**" o "**País y -" (truncado con guión)
                        pattern1 = rf'\*\*{re.escape(country)}\s+y\s+-\s*\*?\*?'
                        # Patrón 2: "**Países**" sin el sufijo (ej: "**Japón y Corea Del Sur**" sin "- Todo Incluido")
                        pattern2 = rf'\*\*{re.escape(countries_part)}\*\*'
                        
                        if re.search(pattern1, response_text, re.IGNORECASE):
                            # Reemplazar truncado con nombre completo
                            response_text = re.sub(pattern1, f'**{package_name}**', response_text, flags=re.IGNORECASE)
                            logger.info("Fixed truncated package name",
                                      from_pattern=f"{country} y -",
                                      to_name=package_name)
                            break
                        elif re.search(pattern2, response_text, re.IGNORECASE) and " - " in package_name:
                            # Reemplazar incompleto con nombre completo
                            response_text = re.sub(pattern2, f'**{package_name}**', response_text, flags=re.IGNORECASE)
                            logger.info("Fixed incomplete package name",
                                      from_pattern=countries_part,
                                      to_name=package_name)
                            break
            
            # Actualizar la respuesta con el nombre corregido
            result["response"] = response_text
        
        # Convertir resultado a formato de respuesta (schema flexible)
        geography_analysis = result.get("geography_analysis", {})

        # SessionInfo ya viene en formato correcto desde agent_service
        session_info_data = result.get("session_info", {})
        session_info = SessionInfo(**session_info_data) if session_info_data else None

        # Tarjetas visuales (Fase 2): derivadas determinísticamente de las habitaciones
        # que la tool consultar_disponibilidad ofreció en este turno.
        cards = _build_room_cards(result.get("rooms_offered", []))

        # Si el agente está pidiendo fechas y no mostró habitaciones, ofrecemos el selector.
        if _should_offer_datepicker(result.get("response", ""),
                                    result.get("tools_used", []),
                                    has_room_cards=bool(cards)):
            cards = [_date_picker_card()]

        processing_time = time.time() - start_time

        response = ChatResponse(
            response=result["response"],
            has_context=result.get("has_context", False),
            geography_analysis=geography_analysis,  # Ahora es Dict
            sources_used=result.get("sources_used"),
            session_info=session_info,
            processing_time=f"{processing_time:.2f}s",
            error=result.get("error", False),
            error_type=result.get("error_type"),
            cards=cards,
        )
        
        logger.info("Chat message processed successfully",
                   session_id=chat_request.session_id,
                   has_context=result.get("has_context", False),
                   processing_time=f"{processing_time:.2f}s")
        
        # Trackear conversación para métricas - SIEMPRE, no solo cuando hay destinos
        try:
            # Extraer destino principal del análisis geográfico
            destination = None
            if geography_analysis:
                countries = geography_analysis.get("countries", [])
                if countries:
                    destination = countries[0]  # Primer país mencionado
            
            # Extraer documentos de las fuentes
            documents = []
            document_sources = result.get("document_sources", [])
            
            if document_sources:
                for source in document_sources:
                    doc_name = source.get("document", "")
                    if doc_name and doc_name not in documents:
                        documents.append(doc_name)
            
            # Extraer paquetes (simplificado - del nombre del documento)
            packages = []
            for doc in documents:
                # Extraer nombre del paquete del nombre del archivo
                # Ej: "Europa Clásica.pdf" -> "Europa Clásica"
                package_name = doc.replace(".pdf", "").replace(".PDF", "")
                if package_name and package_name not in packages:
                    packages.append(package_name)
            
            # ✅ TRACKEAR SIEMPRE - incluso sin destinos o documentos
            metrics_service.track_conversation(
                db,
                session_id=chat_request.session_id,
                is_user_message=True,
                response_time=processing_time,
                destination=destination,
                documents=documents if documents else None,
                packages=packages if packages else None
            )
            
            logger.info("Conversation tracked",
                       session_id=chat_request.session_id,
                       destination=destination,
                       documents_count=len(documents),
                       packages_count=len(packages))
        except Exception as tracking_error:
            logger.warning("Error tracking conversation metrics", error=str(tracking_error))
        
        return response
    
    except Exception as e:
        processing_time = time.time() - start_time
        
        # Log con traceback completo para debugging
        import traceback
        logger.error("Error processing chat message",
                    session_id=chat_request.session_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                    processing_time=f"{processing_time:.2f}s")
        
        # Respuesta de error estructurada
        return ChatResponse(
            response="Lo siento, ocurrió un error procesando tu mensaje. Por favor, intenta nuevamente.",
            has_context=False,
            geography_analysis={},  # Dict vacío en lugar de GeographyAnalysis()
            error=True,
            error_type=type(e).__name__,
            processing_time=f"{processing_time:.2f}s"
        )

@router.post("/clear/{session_id}", response_model=ClearHistoryResponse)
async def clear_conversation(session_id: str):
    """Limpia historial de conversación"""
    try:
        logger.info("Clearing conversation history", session_id=session_id)
        
        # Validar session_id
        if not session_id or len(session_id) < 8:
            raise HTTPException(
                status_code=400,
                detail="Session ID inválido"
            )
        
        result = agent_service.clear_history(session_id)
        
        if result.get("success", False):
            logger.info("Conversation cleared successfully",
                       session_id=session_id,
                       messages_cleared=result.get("messages_cleared", 0))
            
            return ClearHistoryResponse(
                success=True,
                messages_cleared=result.get("messages_cleared", 0),
                message=result.get("message", "Historial limpiado exitosamente"),
                session_id=session_id
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Error limpiando historial")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing conversation",
                    session_id=session_id,
                    error=str(e))
        
        return ClearHistoryResponse(
            success=False,
            messages_cleared=0,
            message=f"Error limpiando historial: {str(e)}",
            session_id=session_id
        )

@router.get("/greeting", response_model=GreetingResponse)
async def get_greeting():
    """Obtiene mensaje de saludo del agente"""
    try:
        logger.debug("Getting agent greeting")
        
        profile_info = profile_manager.get_profile_info()
        
        return GreetingResponse(
            greeting=profile_manager.get_greeting(),
            agent_name=profile_manager.get_agent_name(),
            capabilities=profile_manager.get_capabilities(),
            conversation_starters=profile_manager.get_conversation_starters()
        )
    
    except Exception as e:
        logger.error("Error getting greeting", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo saludo: {str(e)}"
        )

@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """Obtiene información de una sesión específica"""
    try:
        logger.debug("Getting session info", session_id=session_id)
        
        if not session_id or len(session_id) < 8:
            raise HTTPException(
                status_code=400,
                detail="Session ID inválido"
            )
        
        session_info = agent_service.get_session_info(session_id)
        
        return session_info
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting session info",
                    session_id=session_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo información de sesión: {str(e)}"
        )

@router.get("/stats", response_model=AgentStatsResponse)
async def get_agent_stats():
    """Obtiene estadísticas del agente"""
    try:
        logger.debug("Getting agent stats")
        
        stats = agent_service.get_service_stats()
        
        return AgentStatsResponse(
            active_sessions=stats.get("active_sessions", 0),
            total_messages=stats.get("total_messages", 0),
            agent_profile=stats.get("agent_profile", {}),
            openai_config=stats.get("model_config", {}),
            uptime=_format_uptime(time.monotonic() - _SERVICE_START)
        )
    
    except Exception as e:
        logger.error("Error getting agent stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )

@router.get("/destinations", response_model=DestinationsResponse)
async def get_available_destinations():
    """Obtiene destinos disponibles en el sistema"""
    try:
        logger.debug("Getting available destinations")
        
        destinations = await rag_service.get_available_destinations()
        
        if "error" in destinations:
            raise HTTPException(
                status_code=500,
                detail=destinations["error"]
            )
        
        return DestinationsResponse(**destinations)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting destinations", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo destinos: {str(e)}"
        )

@router.get("/health")
async def get_chat_health():
    """Verifica el estado de salud del sistema de chat"""
    try:
        # Verificar RAG service
        rag_health = rag_service.get_service_health()
        
        # Verificar agent service stats
        agent_stats = agent_service.get_service_stats()
        
        # Verificar profile manager
        try:
            profile_info = profile_manager.get_profile_info()
            profile_healthy = True
        except Exception:
            profile_healthy = False
        
        overall_status = "healthy"
        if rag_health.get("status") != "healthy":
            overall_status = "degraded"
        if not profile_healthy:
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "rag_service": rag_health,
            "agent_service": {
                "active_sessions": agent_stats.get("active_sessions", 0),
                "circuit_breaker": agent_stats.get("openai_circuit_breaker", {})
            },
            "profile_manager": {
                "healthy": profile_healthy,
                "current_profile": profile_info.get("profile_name") if profile_healthy else None
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("Error checking chat health", error=str(e))
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
