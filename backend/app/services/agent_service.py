from app.core.openai_client import get_async_openai
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.utils.timezone_utils import now_argentina
from app.services.rag_service import rag_service
from app.services.lead_service import lead_service
from app.services.conversation_state_manager import conversation_state_manager
from app.core.agent_profile import profile_manager
from app.core.circuit_breaker import openai_circuit_breaker
from app.core.logging_config import get_logger
from app.core.sdk_usage import usage_from_completion
from app.services import usage_service
from app.prompts.generation_prompts import CASUAL_RESPONSE_SYSTEM
import time
import uuid
from datetime import datetime, timezone
import re

# 🆕 Imports para módulo post-venta
from app.services.postsale_service import PostSaleService

# 🆕 Imports para Visión 360°
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

logger = get_logger(__name__)

class AgentService:
    # Patrones de código de reserva (post-venta). Centralizados para que el detector
    # de post-venta y el guard de conversación casual usen exactamente la misma lógica.
    BOOKING_CODE_PATTERNS = [
        r'\bHTL-[A-Z0-9]{4}\b',        # HTL-7F3A (formato real de reservas del hotel)
    ]

    # Frases sociales centralizadas. Usadas en: _detect_postsale_context (guard de
    # saludos), _classify_first_message (fallback), y detección de despedidas en chat().
    # Actualizar acá las afecta a los tres lugares sin tocar nada más.
    _GREETING_PHRASES: frozenset = frozenset({
        "hola", "buenas", "hi", "hello", "hey", "buen dia", "buenos dias",
        "buenas tardes", "buenas noches", "que tal", "qué tal",
    })
    _FAREWELL_PHRASES: frozenset = frozenset({
        "chau", "adios", "adiós", "hasta luego", "bye", "nos vemos",
        "hasta pronto", "gracias por todo", "fue un placer", "hasta la vista",
    })
    # Unión: cualquier frase social (saludo o despedida) usada como guard en post-venta.
    _SOCIAL_PHRASES: frozenset = _GREETING_PHRASES | _FAREWELL_PHRASES | frozenset({
        "gracias", "muchas gracias", "gracias!", "chau gracias", "chau, gracias",
    })

    # Límite de historial en memoria. La rehidratación desde BD usa el mismo valor
    # para no perder mensajes en reinicios del servidor.
    _MAX_HISTORY_MESSAGES: int = 50

    def _contains_booking_code(self, message: str) -> bool:
        """True si el mensaje contiene un patrón de código de reserva."""
        upper = message.upper()
        return any(re.search(p, upper) for p in self.BOOKING_CODE_PATTERNS)

    def __init__(self):
        try:
            self.client = get_async_openai()
            self.conversation_history: Dict[str, List[Dict]] = {}
            self.session_metadata: Dict[str, Dict] = {}

            logger.info("Agent service initialized",
                       model=settings.OPENAI_MODEL,
                       temperature=settings.OPENAI_TEMPERATURE)
        except Exception as e:
            logger.error("Error initializing agent service", error=str(e))
            raise
    
    def _get_or_create_history(self, session_id: str, db: Session = None) -> List[Dict]:
        """Obtiene o crea historial de conversación.
        En cache-miss intenta rehidratar desde la BD para sobrevivir reinicios del servidor."""
        if session_id not in self.conversation_history:
            rehydrated = []
            if db is not None:
                try:
                    messages = (
                        db.query(ConversationMessage)
                        .filter(ConversationMessage.session_id == session_id)
                        .order_by(ConversationMessage.sequence_number)
                        .limit(self._MAX_HISTORY_MESSAGES)
                        .all()
                    )
                    rehydrated = [{"role": m.role, "content": m.content} for m in messages]
                    if rehydrated:
                        logger.info("Conversation history rehydrated from DB",
                                    session_id=session_id,
                                    messages_loaded=len(rehydrated))
                except Exception as e:
                    logger.warning("Could not rehydrate history from DB",
                                   session_id=session_id, error=str(e))

            self.conversation_history[session_id] = rehydrated
            self.session_metadata[session_id] = {
                "created_at": now_argentina(),
                "message_count": len(rehydrated),
                "last_activity": now_argentina()
            }
            if not rehydrated:
                logger.info("New conversation session created", session_id=session_id)

        return self.conversation_history[session_id]
    
    def _save_message_to_db(
        self,
        db: Session,
        session_id: str,
        role: str,
        content: str,
        context_type: str = 'pre_sale',
        tokens_used: int = None,
        response_time_ms: int = None,
        model_used: str = None
    ):
        """
        🆕 VISIÓN 360°: Guarda un mensaje en la base de datos
        
        Args:
            db: Sesión de base de datos
            session_id: ID de sesión
            role: 'user' o 'assistant'
            content: Contenido del mensaje
            context_type: 'pre_sale' o 'post_sale'
            tokens_used: Tokens utilizados (opcional)
            response_time_ms: Tiempo de respuesta en ms (opcional)
            model_used: Modelo utilizado (opcional)
        """
        try:
            # Buscar o crear conversación
            conversation = db.query(Conversation).filter(
                Conversation.session_id == session_id
            ).first()
            
            if not conversation:
                # Canal derivado del session_id (mismo criterio que Lead.channel).
                channel = "whatsapp" if session_id.startswith("wa_") else "web"
                conversation = Conversation(
                    session_id=session_id,
                    context_type=context_type,
                    channel=channel,
                )
                db.add(conversation)
                db.flush()  # Para obtener el ID
                logger.info("New conversation created in DB",
                           session_id=session_id,
                           channel=channel,
                           conversation_id=conversation.id)
            
            # Obtener número de secuencia
            last_message = db.query(ConversationMessage).filter(
                ConversationMessage.conversation_id == conversation.id
            ).order_by(ConversationMessage.sequence_number.desc()).first()
            
            sequence_number = (last_message.sequence_number + 1) if last_message else 1
            
            # Crear mensaje
            message = ConversationMessage(
                conversation_id=conversation.id,
                session_id=session_id,
                role=role,
                content=content,
                sequence_number=sequence_number,
                context_type=context_type,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms,
                model_used=model_used or settings.OPENAI_MODEL
            )
            
            db.add(message)
            
            # Actualizar conversation
            conversation.message_count += 1
            if role == 'user':
                conversation.user_message_count += 1
            else:
                conversation.agent_message_count += 1
            conversation.last_message_at = datetime.now(timezone.utc)
            
            db.commit()
            
            logger.info("Message saved to DB",
                       session_id=session_id,
                       conversation_id=conversation.id,
                       message_id=message.id,
                       role=role,
                       sequence=sequence_number)
            
        except Exception as e:
            logger.error("Error saving message to DB",
                        session_id=session_id,
                        role=role,
                        error=str(e))
            db.rollback()
    
    def _update_session_metadata(self, session_id: str):
        """Actualiza metadata de la sesión"""
        if session_id in self.session_metadata:
            self.session_metadata[session_id]["last_activity"] = now_argentina()
            self.session_metadata[session_id]["message_count"] += 1
    
    def _format_history(self, history: List[Dict]) -> str:
        """Formatea historial para el prompt"""
        if not history:
            return "No hay historial previo."
        
        # Tomar últimos 10 mensajes para mejor contexto conversacional
        recent_history = history[-10:]
        formatted = []
        
        for msg in recent_history:
            role = "Usuario" if msg["role"] == "user" else "Asistente"
            content = msg["content"][:500]  # Limitar longitud
            if len(msg["content"]) > 500:
                content += "..."
            formatted.append(f"{role}: {content}")
        
        return "\n".join(formatted)
    
    async def _generate_casual_response(self, message: str, history: List[Dict], language: str = "es") -> tuple[str, Dict]:
        """
        Genera respuesta natural para conversación casual

        Args:
            message: Mensaje del usuario
            history: Historial de conversación
            language: idioma de respuesta (es | en | pt | fr)

        Returns:
            (respuesta amigable, usage) — usage con los tokens consumidos.
        """
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": settings.OPENAI_MODEL}
        try:
            # Formatear historial
            history_context = ""
            if history:
                recent = history[-4:]
                history_context = "\n".join([
                    f"{'Usuario' if msg['role'] == 'user' else 'Asistente'}: {msg['content'][:200]}"
                    for msg in recent
                ])

            history_section = f"Historial de la conversación:\n{history_context}" if history_context else ""
            prompt = CASUAL_RESPONSE_SYSTEM.format(
                agent_name=profile_manager.get_agent_name(),
                history_section=history_section,
                message=message,
            )
            from app.prompts.context_blocks import build_language_block
            lang_block = build_language_block(language)
            if lang_block:
                prompt = prompt + "\n" + lang_block

            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,  # Más creativo para conversación casual
                max_tokens=150
            )

            casual_response = response.choices[0].message.content.strip()
            usage = usage_from_completion(response, model=settings.OPENAI_MODEL)

            logger.info("Casual response generated",
                       message=message[:50],
                       response_length=len(casual_response))

            return casual_response, usage

        except Exception as e:
            logger.error("Error generating casual response",
                        error=str(e),
                        message=message[:50])
            # Fallback genérico
            return "¡Hola! 😊 ¿En qué puedo ayudarte con tu estadía en el Hampton Bariloche?", usage
    
    def _validate_input(self, message: str, session_id: str) -> tuple[bool, str]:
        """Valida entrada del usuario"""
        if not message or not message.strip():
            return False, "Mensaje vacío"
        
        if len(message) > 1000:
            return False, "Mensaje demasiado largo (máximo 1000 caracteres)"
        
        if not session_id or len(session_id) < 8:
            return False, "Session ID inválido"
        
        # Verificar caracteres sospechosos básicos
        suspicious_patterns = ['<script', 'javascript:', 'eval(', 'DROP TABLE']
        message_lower = message.lower()
        
        for pattern in suspicious_patterns:
            if pattern in message_lower:
                return False, f"Contenido no permitido detectado: {pattern}"
        
        return True, "Válido"
    
    def _get_postsale_service(self, db: Session) -> PostSaleService:
        """Obtiene o crea instancia de PostSaleService"""
        return PostSaleService(db)
    
    async def chat(self, db: Session, message: str, session_id: str, language: str = "es") -> Dict:
        """
        Procesa mensaje del usuario y genera respuesta

        Args:
            db: Sesión de base de datos
            message: Mensaje del usuario
            session_id: ID de sesión
            language: idioma de respuesta (es | en | pt | fr). Default es.
        """
        start_time = time.time()
        tokens_used: Optional[int] = None

        try:
            # 1. Validar entrada
            is_valid, validation_msg = self._validate_input(message, session_id)
            if not is_valid:
                logger.warning("Invalid input",
                              session_id=session_id,
                              reason=validation_msg)
                return {
                    "response": f"Lo siento, hay un problema con tu mensaje: {validation_msg}",
                    "has_context": False,
                    "error": True,
                    "error_type": "validation_error"
                }
            
            logger.info("Processing chat message",
                       session_id=session_id,
                       message_length=len(message))

            # 1.5. FRENO DE GASTO: si se superó el tope (diario/mensual) configurado,
            # NO llamamos a OpenAI. Respondemos un mensaje amable. Cero gasto extra.
            if usage_service.is_budget_exceeded(db):
                logger.warning("Budget exceeded — refusing to call the agent",
                               session_id=session_id)
                return {
                    "response": "El asistente no está disponible en este momento. "
                                "Por favor, intentá de nuevo más tarde.",
                    "has_context": False,
                    "error": True,
                    "error_type": "budget_exceeded",
                }

            # 2. Obtener historial
            history = self._get_or_create_history(session_id, db=db)
            
            # 🆕 2.3. CHEQUEAR ESTADO CONVERSACIONAL (captura de datos multi-paso)
            state = conversation_state_manager.get_state(session_id)
            if state:
                logger.info("Active conversation state detected",
                           session_id=session_id,
                           step=state.get("step"))
                return await self._handle_conversation_state(db, message, session_id, state, history)
            
            # 🆕 2.4. SEÑALES DURAS (determinísticas) — cortocircuitos previos al ruteo.
            # Un mensaje con código de reserva o una sesión post-venta activa SIEMPRE es
            # post-venta, sin importar el flag de ruteo: el regex/DB query es infalible y
            # cuesta 0 llamadas LLM. El detector casual solo aplica si NO hay señal dura.
            from app.models.hotel import HotelTicket
            has_active_postsale = db.query(HotelTicket).filter(
                HotelTicket.session_id == session_id,
                HotelTicket.status.in_(["open", "in_progress", "escalated"]),
            ).first() is not None
            has_booking_code = self._contains_booking_code(message)

            # 🆕 2.5. RUTEO: pre-venta / post-venta / casual.
            # Una señal dura (código de reserva o sesión post-venta activa) SIEMPRE es
            # post-venta y se resuelve sin gastar el triage. En cualquier otro caso, el
            # triage agent del SDK (una sola pasada, con handoffs) desambigua el destino.
            triage = {}  # usage del ruteo (vacío si hubo señal dura y no se invocó)
            if has_booking_code or has_active_postsale:
                is_postsale = True
            else:
                from app.services.triage_sdk_orchestrator import (
                    triage_sdk_orchestrator, ROUTE_CASUAL, ROUTE_POSTVENTA,
                )
                triage = await triage_sdk_orchestrator.route(message, session_id, history)

                if triage["route"] == ROUTE_CASUAL:
                    logger.info("Triage SDK: casual route", session_id=session_id,
                               message=message[:50])
                    # El triage solo rutea; la respuesta casual la genera SIEMPRE este
                    # método (única fuente con reglas de alcance: no recetas/tareas, etc.).
                    response_text, casual_usage = await self._generate_casual_response(message, history, language)
                    history.append({"role": "user", "content": message})
                    history.append({"role": "assistant", "content": response_text})
                    self._update_session_metadata(session_id)

                    # Persistir consumo de la respuesta casual (triage + completion).
                    casual_tokens = (triage.get("usage", {}).get("total_tokens", 0)
                                     + casual_usage.get("total_tokens", 0))
                    try:
                        self._save_message_to_db(
                            db=db, session_id=session_id, role='user',
                            content=message, context_type='pre_sale'
                        )
                        self._save_message_to_db(
                            db=db, session_id=session_id, role='assistant',
                            content=response_text, context_type='pre_sale',
                            tokens_used=casual_tokens or None,
                            model_used=casual_usage.get("model"),
                        )
                    except Exception as e:
                        logger.error("Error saving casual messages to DB",
                                     session_id=session_id, error=str(e))

                    total_duration = time.time() - start_time
                    return {
                        "response": response_text,
                        "has_context": False,
                        "intent": "casual_conversation",
                        "processing_time": f"{total_duration:.2f}s",
                        "session_info": self.get_session_info(session_id)
                    }

                is_postsale = (triage["route"] == ROUTE_POSTVENTA)

            if is_postsale:
                logger.info("Post-sale context detected, delegating to PostSaleService",
                           session_id=session_id,
                           message_preview=message[:50])
                
                try:
                    # Post-venta del HOTEL sobre el Agents SDK: gate determinístico
                    # (validación de reserva por código HTL-XXXX) + loop de tools.
                    from app.services.hotel_postsale import HotelPostSaleService
                    postsale_service = HotelPostSaleService(db)

                    gate = await postsale_service.run_gate(message, session_id, history)
                    if gate["handled"]:
                        # Respuesta terminal del gate (validación fallida o solo-código)
                        response_text = gate["result"].get("response", "")
                        history.append({"role": "user", "content": message})
                        history.append({"role": "assistant", "content": response_text})
                        self._update_session_metadata(session_id)
                        gate["result"].setdefault("has_context", True)
                        gate["result"].setdefault("context_type", "postsale")
                        gate["result"]["session_info"] = self.get_session_info(session_id)
                        return gate["result"]

                    # Listo para el loop con tools (Agents SDK).
                    from app.services.hotel_postsale_orchestrator import hotel_postsale_sdk_orchestrator
                    orch_result = await hotel_postsale_sdk_orchestrator.run(
                        postsale_service, gate["booking"], gate["ticket"],
                        gate["query_to_process"], session_id, history
                    )
                    response_text = orch_result["response"]
                    history.append({"role": "user", "content": message})
                    history.append({"role": "assistant", "content": response_text})
                    self._update_session_metadata(session_id)

                    # Registrar consumo de tokens del turno post-venta (para panel y tope).
                    ps_usage = orch_result.get("usage", {})
                    if ps_usage.get("total_tokens"):
                        try:
                            self._save_message_to_db(
                                db=db, session_id=session_id, role='assistant',
                                content=response_text, context_type='post_sale',
                                tokens_used=ps_usage.get("total_tokens"),
                                model_used=ps_usage.get("model") or settings.OPENAI_MODEL,
                            )
                        except Exception as e:
                            logger.error("Error saving postsale usage to DB",
                                         session_id=session_id, error=str(e))

                    orch_result["session_info"] = self.get_session_info(session_id)
                    return orch_result

                except Exception as e:
                    import traceback
                    logger.error("Error in post-sale processing",
                                session_id=session_id,
                                error=str(e),
                                error_type=type(e).__name__,
                                traceback=traceback.format_exc())
                    
                    # Fallback a respuesta genérica
                    return {
                        "response": "Disculpa, estoy teniendo problemas para procesar tu consulta de post-venta. Por favor, intenta nuevamente o contacta a nuestro equipo de soporte.",
                        "has_context": False,
                        "error": True,
                        "error_type": type(e).__name__
                    }
            
            # PRE-VENTA: delega al orquestador del HOTEL (Agents SDK). Post-venta, estado
            # conversacional y casual ya se resolvieron arriba.
            from app.services.hotel_sdk_orchestrator import hotel_sdk_orchestrator
            orch_result = await hotel_sdk_orchestrator.run(db, message, session_id, history, language)
            response_text = orch_result["response"]

            # Actualizar historial en memoria
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response_text})

            # Tokens del turno = orquestador pre-venta + triage (si se invocó).
            orch_usage = orch_result.get("usage", {})
            turn_tokens = (orch_usage.get("total_tokens", 0)
                           + triage.get("usage", {}).get("total_tokens", 0))

            # Persistir en DB (Visión 360°)
            try:
                self._save_message_to_db(
                    db=db, session_id=session_id, role='user',
                    content=message, context_type='pre_sale'
                )
                self._save_message_to_db(
                    db=db, session_id=session_id, role='assistant',
                    content=response_text, context_type='pre_sale',
                    tokens_used=turn_tokens or None,
                    response_time_ms=int((time.time() - start_time) * 1000),
                    model_used=orch_usage.get("model") or settings.OPENAI_MODEL
                )
            except Exception as e:
                logger.error("Error saving messages to DB (tool agent)",
                             session_id=session_id, error=str(e))

            if len(history) > self._MAX_HISTORY_MESSAGES:
                self.conversation_history[session_id] = history[-self._MAX_HISTORY_MESSAGES:]
            self._update_session_metadata(session_id)

            orch_result["session_info"] = self.get_session_info(session_id)
            return orch_result
        except Exception as e:
            duration = time.time() - start_time
            
            logger.error("Error processing chat message",
                        session_id=session_id,
                        message_length=len(message) if message else 0,
                        error=str(e),
                        duration=f"{duration:.2f}s")
            
            # Respuesta de error amigable
            error_response = "Lo siento, ocurrió un error procesando tu consulta. Por favor, intenta nuevamente en unos momentos."
            
            # Si hay historial, agregar el mensaje del usuario pero no la respuesta de error
            if session_id in self.conversation_history:
                history = self.conversation_history[session_id]
                history.append({"role": "user", "content": message})
                self._update_session_metadata(session_id)
            
            return {
                "response": error_response,
                "has_context": False,
                "error": True,
                "error_type": type(e).__name__,
                "session_info": self.get_session_info(session_id) if session_id in self.session_metadata else {},
                "processing_time": f"{duration:.2f}s"
            }
    
    def clear_history(self, session_id: str) -> Dict:
        """Limpia historial de conversación"""
        try:
            messages_cleared = 0
            
            if session_id in self.conversation_history:
                messages_cleared = len(self.conversation_history[session_id])
                del self.conversation_history[session_id]
            
            if session_id in self.session_metadata:
                del self.session_metadata[session_id]
            
            logger.info("Conversation history cleared",
                       session_id=session_id,
                       messages_cleared=messages_cleared)
            
            return {
                "success": True,
                "messages_cleared": messages_cleared,
                "message": "Historial limpiado exitosamente"
            }
            
        except Exception as e:
            logger.error("Error clearing conversation history",
                        session_id=session_id,
                        error=str(e))
            return {
                "success": False,
                "error": str(e),
                "message": "Error limpiando historial"
            }
    
    def get_session_info(self, session_id: str) -> Dict:
        """Obtiene información de la sesión"""
        if session_id not in self.session_metadata:
            return {
                "exists": False,
                "message_count": 0,
                "history_length": 0
            }
        
        metadata = self.session_metadata[session_id]
        history_length = len(self.conversation_history.get(session_id, []))
        
        return {
            "exists": True,
            "created_at": metadata["created_at"].isoformat(),
            "last_activity": metadata["last_activity"].isoformat(),
            "message_count": metadata["message_count"],
            "history_length": history_length
        }
    
    def get_service_stats(self) -> Dict:
        """Obtiene estadísticas del servicio desde la base de datos"""
        try:
            from app.models.database import SessionLocal
            from app.models.conversation import Conversation
            from sqlalchemy import func
            
            # Obtener datos de la base de datos en lugar de memoria
            db = SessionLocal()
            try:
                # Contar conversaciones totales
                total_conversations = db.query(func.count(Conversation.id)).scalar() or 0
                
                # Sumar todos los mensajes
                total_messages = db.query(func.sum(Conversation.message_count)).scalar() or 0
                
                # Conversaciones activas (últimas 24 horas o sin finalizar)
                from datetime import datetime, timedelta
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)
                active_sessions = db.query(func.count(Conversation.id)).filter(
                    Conversation.last_message_at >= yesterday
                ).scalar() or 0
                
            finally:
                db.close()
            
            # Estados de circuit breakers
            openai_cb_state = openai_circuit_breaker.get_state()
            
            return {
                "active_sessions": total_conversations,  # Total de conversaciones en DB
                "total_messages": total_messages,  # Total de mensajes en DB
                "active_sessions_24h": active_sessions,  # Activas en últimas 24h
                "agent_profile": profile_manager.get_profile_info(),
                "openai_circuit_breaker": openai_cb_state,
                "model_config": {
                    "model": settings.OPENAI_MODEL,
                    "temperature": settings.OPENAI_TEMPERATURE,
                    "max_retries": settings.OPENAI_MAX_RETRIES
                }
            }
            
        except Exception as e:
            logger.error("Error getting service stats", error=str(e))
            return {"error": str(e)}
    
    async def _handle_conversation_state(
        self,
        db: Session,
        message: str,
        session_id: str,
        state: Dict,
        history: List[Dict]
    ) -> Dict:
        """
        Maneja flujos conversacionales multi-paso (captura de datos)
        """
        try:
            step = state.get("step")
            event_info = state.get("event_info", {})
            contact_data = state.get("contact_data", {})
            
            logger.info("Handling conversation state",
                       session_id=session_id,
                       step=step)
            
            # Paso 0: Elección de opción (notificación o alternativas)
            if step == "awaiting_event_choice":
                message_lower = message.lower().strip()
                
                # Opción 1: Notificación
                if any(word in message_lower for word in ["1", "notif", "avisa", "aviso", "primera"]):
                    conversation_state_manager.update_state(session_id, {
                        "step": "awaiting_name",
                        "event_info": event_info,
                        "contact_data": contact_data
                    })
                    
                    response_text = "¡Perfecto! Te notificaré cuando tengamos paquetes disponibles.\n\n¿Cuál es tu nombre?"
                    
                # Opción 2: Destinos similares
                elif any(word in message_lower for word in ["2", "destin", "alternativ", "similar", "segunda", "opciones"]):
                    # Limpiar estado
                    conversation_state_manager.clear_state(session_id)
                    
                    # Usar lógica actual de alternativas por región
                    countries = event_info.get("related_countries", [])
                    geo_analysis = {
                        "countries": countries,
                        "continent": None,
                        "suggested_countries": countries
                    }
                    
                    no_context_result = rag_service.format_no_context_response(geo_analysis)
                    response_text = no_context_result if isinstance(no_context_result, str) else no_context_result.get("response", "")
                    
                    logger.info("User chose alternative destinations",
                               session_id=session_id,
                               countries=countries[:3])
                else:
                    # No entendió, preguntar de nuevo
                    response_text = "Por favor, elige una opción:\n\n1️⃣ Notificación\n2️⃣ Destinos similares\n\nResponde con **1** o **2**."
            
            # Paso 1: Capturar nombre
            elif step == "awaiting_name":
                contact_data["name"] = message.strip()
                conversation_state_manager.update_state(session_id, {
                    "step": "awaiting_email",
                    "contact_data": contact_data
                })
                
                response_text = "Perfecto. ¿Cuál es tu email?"
                
            # Paso 2: Capturar email
            elif step == "awaiting_email":
                contact_data["email"] = message.strip()
                conversation_state_manager.update_state(session_id, {
                    "step": "awaiting_phone",
                    "contact_data": contact_data
                })
                
                response_text = "Excelente. ¿Y tu número de teléfono?"
                
            # Paso 3: Capturar teléfono y crear lead
            elif step == "awaiting_phone":
                contact_data["phone"] = message.strip()
                
                # Crear lead con evento
                lead = await lead_service.create_event_lead(
                    db, session_id, event_info, contact_data
                )
                
                # Limpiar estado
                conversation_state_manager.clear_state(session_id)
                
                event_name = event_info.get("event_name", "este evento")
                response_text = f"¡Perfecto {contact_data['name']}! Te contactaremos cuando tengamos paquetes de {event_name} disponibles.\n\n¿Hay algo más en lo que pueda ayudarte?"
                
                logger.info("Event lead created successfully",
                           session_id=session_id,
                           lead_id=lead.id,
                           event_name=event_info.get("event_name"))
            else:
                # Estado desconocido, limpiar
                conversation_state_manager.clear_state(session_id)
                response_text = "Disculpa, hubo un error. ¿En qué puedo ayudarte?"
            
            # Actualizar historial
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response_text})
            self._update_session_metadata(session_id)
            
            return {
                "response": response_text,
                "has_context": False,
                "capturing_lead": step != "awaiting_phone",
                "lead_created": step == "awaiting_phone",
                "session_info": self.get_session_info(session_id)
            }
            
        except Exception as e:
            logger.error("Error handling conversation state",
                        session_id=session_id,
                        error=str(e))
            conversation_state_manager.clear_state(session_id)
            raise


# Instancia global del servicio del agente
agent_service = AgentService()
