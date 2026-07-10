from app.core.llm.openai_client import get_async_openai
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.utils.timezone_utils import now_business
from app.core.rag.rag_service import rag_service
from app.services.lead_service import lead_service
from app.services.conversation_state_manager import conversation_state_manager
from app.core.profile.agent_profile import profile_manager
from app.core.llm.circuit_breaker import openai_circuit_breaker
from app.core.observability.logging_config import get_logger
from app.core.llm.sdk_usage import usage_from_completion
from app.services import usage_service
from app.domains.hotel.prompts.generation_prompts import CASUAL_RESPONSE_SYSTEM
import asyncio
import time
import uuid
from datetime import datetime, timezone, timedelta
import re

# 🆕 Imports para módulo post-venta

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
    # Código de reserva de MESA del restaurante (MESA-XXXX). El frontend manda un acuse
    # ("Confirmé mi reserva de mesa MESA-XXXX") tras crear la mesa en el selector: lo
    # interceptamos para felicitar, NO para mandarlo al post-venta del hotel (que pide HTL-).
    TABLE_CODE_PATTERN = r'\bMESA-[A-Z0-9]{4}\b'

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

    # Ventana de sesión: el agente DA CONTINUIDAD a una charla mientras el último mensaje
    # sea más reciente que esto. Pasada la ventana, se trata como conversación nueva (pero
    # el histórico queda en la DB). 24h = estándar de mercado + ventana de servicio de WhatsApp.
    _SESSION_WINDOW_HOURS: int = 24

    def _contains_booking_code(self, message: str) -> bool:
        """True si el mensaje contiene un patrón de código de reserva."""
        upper = message.upper()
        return any(re.search(p, upper) for p in self.BOOKING_CODE_PATTERNS)

    def _is_pure_social(self, message: str) -> bool:
        """True si el mensaje es SOLO agradecimiento/despedida (sin otra intención).

        Una despedida pura no debe forzar el gate de post-venta (que pediría el código HTL).
        Lógica centralizada en app.utils.social_text para reusarla también en el gate.
        """
        from app.utils.social_text import is_pure_social
        return is_pure_social(message)

    def _session_has_recent_booking(self, db, session_id: str) -> bool:
        """True si en ESTA sesión web se creó una reserva dentro de la ventana de sesión (24h).

        Reconoce al huésped que reservó por web durante su sesión sin re-pedirle el código,
        aunque el ticket de post-venta ya esté cerrado. Solo aplica a sesiones web (WhatsApp se
        identifica por teléfono). Pasada la ventana, vuelve a pedir el código (gate normal).
        """
        if not session_id or session_id.startswith("wa_"):
            return False
        try:
            from app.models.hotel import Booking
            # Booking.created_at se guarda con datetime.now() (hora local del server, como todos
            # los modelos de hotel.py). Comparamos con la MISMA base (now_business), NO utcnow,
            # para que la ventana de 24h sea real en local (UTC-3) y no quede en ~21h.
            cutoff = now_business() - timedelta(hours=self._SESSION_WINDOW_HOURS)
            return db.query(Booking).filter(
                Booking.session_id == session_id,
                Booking.status != "cancelled",
                Booking.created_at >= cutoff,
            ).first() is not None
        except Exception:
            return False

    # Palabras que el huésped usa para confirmar / negar la resolución de su pedido (Fase 4).
    # Se matchean como PALABRA COMPLETA (con \b), no substring: evita que "si" matchee dentro
    # de "sigue" o "anda" dentro de "demandar".
    _VALIDATION_YES = (
        "si", "sí", "sip", "dale", "perfecto", "genial", "gracias", "ok", "okey", "buenísimo",
        "buenisimo", "joya", "anda", "funciona", "resuelto", "solucionado", "bárbaro",
        "barbaro", "excelente", "listo", "impecable", "tal cual", "todo bien",
    )
    _VALIDATION_NO = (
        "no", "sigue", "todavía", "todavia", "aún", "aun", "igual", "peor", "nada", "persiste",
        "continúa", "continua", "sin cambios", "no anda", "no funciona", "no se solucionó",
        "no se soluciono", "no quedó", "no quedo", "ni ahí", "ni ahi",
    )

    def _handle_resolution_validation(self, db, message: str, session_id: str, history):
        """Cierra el loop operativo (Fase 4) si el huésped valida/rechaza una resolución.

        Si hay un ticket PRE-RESUELTO para esta sesión y el mensaje es un sí/no claro, aplica
        la validación y devuelve una respuesta terminal. Si no hay ticket o el mensaje es
        ambiguo, devuelve None para que siga el flujo normal.
        """
        from app.services import operations_service as ops
        ticket = ops.find_pending_validation_ticket(db, session_id)
        if not ticket:
            return None

        low = (message or "").strip().lower()

        def _has(words):
            return any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words)

        is_no = _has(self._VALIDATION_NO)
        is_yes = _has(self._VALIDATION_YES)
        # Ni sí ni no → ambiguo: dejamos seguir el flujo normal (no forzamos cierre).
        if not is_no and not is_yes:
            return None
        # NO tiene prioridad: ante cualquier señal de que sigue el problema, NO cerramos
        # (más seguro reabrir que cerrar mal). ok solo si hay sí y no hay no.
        ok = is_yes and not is_no

        status = ops.guest_validate(db, ticket, ok=ok)
        where = ops._room_label(ticket)
        if status == "resuelto":
            response_text = (f"¡Genial! Me alegra que se haya resuelto lo de {where}. "
                             "Cualquier otra cosa que necesites durante tu estadía, acá estoy. 😊")
        else:
            response_text = (f"Lamento que siga el inconveniente con {where}. Ya avisé de nuevo "
                             "al equipo para que lo revisen cuanto antes. Te mantengo al tanto. 🙏")
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response_text})
        self._update_session_metadata(session_id)
        return {
            "response": response_text,
            "has_context": True,
            "context_type": "postsale",
            "intent": "resolution_validation",
            "ticket_number": ticket.ticket_number,
            "status": status,
            "session_info": self.get_session_info(session_id),
        }

    def _handle_table_confirmation(self, db, message: str, session_id: str, history):
        """Intercepta el acuse de reserva de mesa ("Confirmé mi reserva de mesa MESA-XXXX").

        El frontend lo envía tras crear la mesa en el selector. Respondemos una felicitación
        cálida con los datos reales (fecha/turno/personas) y NO seguimos al ruteo (evita que el
        post-venta del hotel pida un código HTL-). Devuelve None si el mensaje no es ese acuse.
        """
        m = re.search(self.TABLE_CODE_PATTERN, (message or "").upper())
        if not m:
            return None
        code = m.group(0)

        # Buscar la reserva real para felicitar con sus datos (si existe).
        detalle = ""
        try:
            from app.models.restaurant import TableReservation
            r = db.query(TableReservation).filter(
                TableReservation.code == code
            ).first()
            if r:
                pax = r.party_size
                partes = []
                if r.reserved_for:
                    partes.append("el " + r.reserved_for.strftime("%d/%m a las %H:%M"))
                if pax:
                    partes.append(f"para {pax} {'persona' if pax == 1 else 'personas'}")
                if partes:
                    detalle = " " + " ".join(partes)
        except Exception as e:  # noqa: BLE001 — nunca romper el turno por el detalle
            logger.warning("No se pudo leer la reserva de mesa", code=code, error=str(e))

        response_text = (
            f"¡Listo! Tu mesa quedó reservada{detalle}. 🍷 "
            f"Guardá el código **{code}** por si necesitás modificarla. "
            "¿Querés que te recomiende algo de la carta para esa noche?"
        )
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response_text})
        self._update_session_metadata(session_id)
        return {
            "response": response_text,
            "has_context": True,
            "context_type": "casual",
            "intent": "table_reservation_confirmed",
            "session_info": self.get_session_info(session_id),
        }

    def __init__(self):
        try:
            self.client = get_async_openai()
            self.conversation_history: Dict[str, List[Dict]] = {}
            self.session_metadata: Dict[str, Dict] = {}
            # Un lock por session_id para SERIALIZAR los turnos de una misma conversación.
            # Sin esto, dos mensajes seguidos (típico en WhatsApp, donde cada uno corre en su
            # propio asyncio.create_task) generan y envían DOS respuestas en paralelo, la
            # segunda computada con contexto rancio (no vio la respuesta de la primera).
            # Ese es el bug del mensaje descolgado. El lock hace que el 2º turno espere al 1º
            # y así vea el intercambio completo. Se crea perezosamente por sesión.
            self._session_locks: Dict[str, asyncio.Lock] = {}

            logger.info("Agent service initialized",
                       model=settings.OPENAI_MODEL,
                       temperature=settings.OPENAI_TEMPERATURE)
        except Exception as e:
            logger.error("Error initializing agent service", error=str(e))
            raise

    def _get_session_lock(self, session_id: str) -> "asyncio.Lock":
        """Devuelve (creando si hace falta) el lock de esta sesión.

        La creación del dict-entry es sincrónica (no hay await entre el `in` y el set),
        así que es segura frente al scheduler cooperativo de asyncio: dos corrutinas de la
        misma sesión obtienen el MISMO objeto Lock y una espera a la otra.
        """
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock
    
    def _session_cutoff(self) -> datetime:
        """Instante (UTC, naive) a partir del cual un mensaje sigue dentro de la ventana
        de sesión. Más viejo que esto = no entra al contexto activo del agente."""
        return datetime.utcnow() - timedelta(hours=self._SESSION_WINDOW_HOURS)

    def _rehydrate_from_db(self, session_id: str, db: Session) -> List[Dict]:
        """Reconstruye el contexto desde la BD: los ÚLTIMOS mensajes dentro de la ventana
        de 24h, en orden cronológico. Robusto ante reinicios del proceso (deploys/restarts).

        Corrige los bugs previos: ordena por created_at (timestamp real, no sequence_number
        que es por-conversación) DESC para tomar los más recientes, y acota a la ventana.
        """
        if db is None:
            return []
        try:
            rows = (
                db.query(ConversationMessage)
                .filter(
                    ConversationMessage.session_id == session_id,
                    ConversationMessage.created_at >= self._session_cutoff(),
                )
                .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
                .limit(self._MAX_HISTORY_MESSAGES)
                .all()
            )
            rows.reverse()  # a orden cronológico (viejo → nuevo) para el modelo
            history = [{"role": m.role, "content": m.content} for m in rows]
            if history:
                logger.info("Conversation history rehydrated from DB",
                            session_id=session_id, messages_loaded=len(history))
            return history
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not rehydrate history from DB",
                           session_id=session_id, error=str(e), exc_info=True)
            return []

    def _get_or_create_history(self, session_id: str, db: Session = None) -> List[Dict]:
        """Obtiene el historial de la conversación con CONTINUIDAD y ventana de sesión.

        - Si la sesión está en RAM pero su última actividad fue hace > 24h, se descarta
          (charla vieja → nueva). Así un huésped que vuelve al otro día arranca de cero
          aunque el proceso no se haya reiniciado.
        - En cache-miss, rehidrata desde la BD los últimos mensajes dentro de la ventana,
          para sobrevivir reinicios del servidor (deploys/restarts) sin perder el hilo.
        """
        # 1) ¿La sesión en RAM sigue vigente (dentro de la ventana)?
        if session_id in self.conversation_history:
            meta = self.session_metadata.get(session_id) or {}
            last = meta.get("last_activity")
            if last is not None and (now_business() - last) > timedelta(hours=self._SESSION_WINDOW_HOURS):
                logger.info("Session window expired (RAM), starting fresh",
                            session_id=session_id)
                self.conversation_history.pop(session_id, None)
                self.session_metadata.pop(session_id, None)
            else:
                return self.conversation_history[session_id]

        # 2) Cache-miss: rehidratar desde la BD (acotado a la ventana de 24h).
        rehydrated = self._rehydrate_from_db(session_id, db)
        self.conversation_history[session_id] = rehydrated
        self.session_metadata[session_id] = {
            "created_at": now_business(),
            "message_count": len(rehydrated),
            "last_activity": now_business(),
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
                # `owner_` = asesor de gerencia por WhatsApp (context_type "management").
                if session_id.startswith("wa_") or session_id.startswith("owner_"):
                    channel = "whatsapp"
                elif session_id.startswith("ig_"):
                    channel = "instagram"
                else:
                    channel = "web"
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
            self.session_metadata[session_id]["last_activity"] = now_business()
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
    
    def _build_casual_guest_block(self, db, session_id: str) -> str:
        """Perfil del huésped conocido para personalizar el saludo casual.

        Resuelve el Contact por el teléfono del session_id de WhatsApp o por el Lead
        de la sesión, y devuelve el bloque de perfil si hay historial (≥1 reserva o
        preferencias). Vacío si es un huésped nuevo/desconocido. Nunca rompe el turno.
        """
        try:
            from app.services.contact_service import contact_service
            from app.domains.hotel.prompts.context_blocks import build_guest_profile_block
            from app.models.contact import Contact

            contact_id = None
            if session_id.startswith("wa_"):
                phone = "+" + session_id[3:]
                c = db.query(Contact).filter(Contact.phone_number == phone).first()
                contact_id = c.id if c else None
            if not contact_id:
                from app.models.lead import Lead
                lead = db.query(Lead).filter(Lead.session_id == session_id).first()
                contact_id = lead.contact_id if lead else None
            if not contact_id:
                return ""

            profile = contact_service.get_guest_profile(contact_id, db)
            if not profile or (not profile.get("stays_count") and not profile.get("preferences")):
                return ""
            return build_guest_profile_block(profile)
        except Exception as e:  # noqa: BLE001 — la personalización nunca debe romper el saludo
            logger.warning("No se pudo armar el guest block casual", error=str(e))
            return ""

    def _build_team_roster_block(self, db) -> str:
        """Roster del EQUIPO real para el prompt casual.

        Fase 0.1: la construcción vive en base_blocks (única fuente, compartida con
        pre-venta y post-venta para la regla anti-invención de personas). Este método
        queda como delegación para no romper a los llamadores existentes.
        """
        from app.domains.hotel.prompts.base_blocks import build_team_roster_block
        return build_team_roster_block(db)

    async def _should_capture_lead_in_casual(self, db, message: str, session_id: str, history) -> bool:
        """True si en un turno casual (típicamente despedida) conviene captar el contacto.

        Corre el mismo análisis de lead que pre-venta; devuelve la decisión de captar
        (incluye el "momento de cierre" por despedida). False si el lead ya tiene contacto
        o si no aplica. Nunca rompe el turno.
        """
        try:
            from app.services.lead_service import lead_service

            lead = lead_service._get_or_create_lead(db, session_id)
            if lead.is_complete_lead():
                return False
            _, should_request = await lead_service.process_message_for_lead(
                db, message, session_id, history, "", {}
            )
            return should_request
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo evaluar captación de lead en casual", error=str(e))
            return False

    def _availability_shown_in_session(self, db, session_id: str) -> bool:
        """True si en esta sesión la pre-venta ya mostró disponibilidad real (flag en
        Conversation.extra_metadata). Permite al cierre casual ir directo a captar el
        contacto en vez de re-ofrecer disponibilidad ya vista. Best-effort."""
        try:
            from app.models.conversation import Conversation
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            return bool(conv and (conv.extra_metadata or {}).get("availability_shown"))
        except Exception:  # noqa: BLE001
            return False

    async def _generate_casual_response(self, message: str, history: List[Dict],
                                        language: str = "es", guest_block: str = "",
                                        capture_lead: bool = False,
                                        availability_shown: bool = False,
                                        is_whatsapp: bool = False,
                                        team_block: str = "",
                                        profile: Optional[dict] = None) -> tuple[str, Dict]:
        """
        Genera respuesta natural para conversación casual

        Args:
            message: Mensaje del usuario
            history: Historial de conversación
            language: idioma de respuesta (es | en | pt | fr)
            guest_block: contexto del huésped conocido (perfil 360°) para personalizar
                el saludo cuando es un huésped recurrente/alojado. Vacío si es nuevo.

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
            from app.domains.hotel.prompts.generation_prompts import (
                CASUAL_LEAD_CAPTURE_HINT, CASUAL_LEAD_CAPTURE_HINT_AFTER_AVAILABILITY,
                NATURALIDAD_BLOCK,
            )
            # Si hay que captar y ya se mostró disponibilidad, vamos directo al contacto
            # (sin re-ofrecer disponibilidad ya rechazada). Si no, el cierre estándar.
            # En WhatsApp usamos siempre el hint AFTER_AVAILABILITY: ya tenemos el teléfono
            # (viene en el session_id), así que pedimos SOLO el nombre y confirmamos que le
            # escribimos a este mismo número — sin re-pedir un dato que ya conocemos.
            if capture_lead:
                if is_whatsapp or availability_shown:
                    lead_hint = CASUAL_LEAD_CAPTURE_HINT_AFTER_AVAILABILITY
                else:
                    lead_hint = CASUAL_LEAD_CAPTURE_HINT
            else:
                lead_hint = ""
            from app.domains.hotel.prompts.identity_blocks import build_casual_identity_block
            prof = profile or {}
            prompt = CASUAL_RESPONSE_SYSTEM.format(
                identity_block=build_casual_identity_block(prof),
                naturalidad_block=NATURALIDAD_BLOCK,
                team_block=team_block,
                history_section=history_section,
                message=message,
                lead_capture_hint=lead_hint,
            )
            # Si conocemos al huésped (recurrente/alojado), anteponemos su perfil para que
            # el saludo lo reconozca por su nombre en vez de tratarlo como desconocido.
            if guest_block:
                prompt = guest_block + "\n" + prompt
            from app.domains.hotel.prompts.context_blocks import build_language_block
            lang_block = build_language_block(language)
            if lang_block:
                prompt = prompt + "\n" + lang_block

            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,  # Más creativo para conversación casual
                max_tokens=220  # margen para una respuesta cálida sin cortarla a mitad
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
    
    def _preventa_channel_gate(self, db: Session, session_id: str):
        """Fase F (Centro): si el canal de esta sesión NO está asignado al flujo de
        pre-venta, la consulta comercial no se atiende (decisión de producto: el flujo
        "trabaja" solo en sus canales). Devuelve el dict de respuesta bloqueada o None.

        Fail-open: sin config, kill switch apagado o error → None (se atiende normal).
        POST-VENTA nunca pasa por acá: un huésped con reserva siempre se atiende.
        Web recibe un aviso breve (el widget no puede quedar colgado); WhatsApp e
        Instagram quedan en silencio (los webhooks salteán el envío vacío).
        """
        try:
            from app.services import skill_service
            flow = skill_service.get_flow_values_for_session(db, session_id, "flujo_preventa")
            if not flow:
                return None
            canales = flow.get("canales")
            if not isinstance(canales, list):
                return None
            sid = session_id or ""
            channel = ("whatsapp" if sid.startswith("wa_")
                       else "instagram" if sid.startswith("ig_") else "web")
            if channel in canales:
                return None
            logger.info("Pre-venta: canal no asignado al flujo, no se atiende",
                        session_id=session_id, channel=channel)
            base = {"has_context": False, "intent": "channel_blocked",
                    "context_type": "blocked", "channel_blocked": True,
                    "session_info": self.get_session_info(session_id)}
            if channel == "web":
                return {**base, "response": "Este canal no está atendiendo consultas en este momento. ¡Gracias por escribirnos!"}
            return {**base, "response": ""}
        except Exception as e:  # noqa: BLE001 — nunca dejar de atender por el gate
            logger.warning("Channel gate falló; se atiende normal", error=str(e))
            return None

    async def chat(self, db: Session, message: str, session_id: str, language: str = "es") -> Dict:
        """Procesa un turno SERIALIZADO por sesión.

        Toma el lock de la sesión antes de procesar: dos mensajes concurrentes de la misma
        conversación (ej. el huésped manda dos seguidos por WhatsApp) se atienden en orden,
        y el segundo ve la respuesta del primero en el historial. Sin esto, ambos corrían
        ciegos entre sí y se enviaban dos respuestas, la segunda con contexto rancio (el
        bug del mensaje descolgado). El trabajo real está en `_chat_impl`.
        """
        async with self._get_session_lock(session_id):
            return await self._chat_impl(db, message, session_id, language)

    async def _chat_impl(self, db: Session, message: str, session_id: str, language: str = "es") -> Dict:
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
            
            # 🆕 2.35. VALIDACIÓN DE RESOLUCIÓN (Fase 4, "empleado digital"): si hay un ticket
            # operativo PRE-RESUELTO para esta sesión, el huésped está respondiendo si quedó
            # bien. Lo interceptamos acá (determinístico, 0 LLM) para cerrar el loop sin pasar
            # por el orquestador. Si el mensaje no es un sí/no claro, dejamos seguir el flujo.
            validation_resp = self._handle_resolution_validation(db, message, session_id, history)
            if validation_resp is not None:
                return validation_resp

            # 🆕 2.37. ACUSE DE RESERVA DE MESA: el frontend envía "Confirmé mi reserva de mesa
            # MESA-XXXX" tras crear la mesa en el selector. Lo interceptamos para felicitar con
            # los datos reales — NO debe ir al post-venta del hotel (que pide un código HTL-).
            table_resp = self._handle_table_confirmation(db, message, session_id, history)
            if table_resp is not None:
                return table_resp

            # 🆕 2.4. SEÑALES DURAS (determinísticas) — cortocircuitos previos al ruteo.
            # Un mensaje con código de reserva o una sesión post-venta activa SIEMPRE es
            # post-venta, sin importar el flag de ruteo: el regex/DB query es infalible y
            # cuesta 0 llamadas LLM. El detector casual solo aplica si NO hay señal dura.
            from app.models.hotel import HotelTicket, TICKET_OPEN_STATES
            # Excluimos los tickets de RESTAURANTE: un pedido a cocina deja un ticket abierto,
            # pero NO convierte la sesión en "soporte de reserva". Si no, una despedida tras
            # pedir comida caería en el gate de post-venta que pide el código HTL.
            has_active_postsale = db.query(HotelTicket).filter(
                HotelTicket.session_id == session_id,
                HotelTicket.status.in_(TICKET_OPEN_STATES),
                HotelTicket.category != "restaurant",
            ).first() is not None
            has_booking_code = self._contains_booking_code(message)
            # CONTINUIDAD DE SESIÓN: si en ESTA sesión web se hizo una reserva (dentro de la
            # ventana de sesión), reconocemos al huésped sin re-pedir el código aunque el ticket
            # ya esté cerrado. Así el que reservó sigue siendo "huésped" mientras dure la sesión.
            has_session_booking = self._session_has_recent_booking(db, session_id)

            # 🆕 2.5. RUTEO: pre-venta / post-venta / casual.
            # Una señal dura (código de reserva o sesión post-venta activa) SIEMPRE es
            # post-venta y se resuelve sin gastar el triage. En cualquier otro caso, el
            # triage agent del SDK (una sola pasada, con handoffs) desambigua el destino.
            triage = {}  # usage del ruteo (vacío si hubo señal dura y no se invocó)
            # Una DESPEDIDA pura ("gracias, nada más", "chau") NO debe forzar post-venta aunque
            # la sesión tenga contexto de reserva: es un cierre, no una consulta. Va a casual.
            # (Si el mensaje trae un código de reserva, sí es señal explícita → post-venta.)
            is_pure_social = self._is_pure_social(message) and not has_booking_code
            if (has_booking_code or has_active_postsale or has_session_booking) and not is_pure_social:
                is_postsale = True
            else:
                from app.services.triage_sdk_orchestrator import (
                    triage_sdk_orchestrator, ROUTE_CASUAL, ROUTE_POSTVENTA,
                )
                triage = await triage_sdk_orchestrator.route(message, session_id, history)

                if triage["route"] == ROUTE_CASUAL:
                    logger.info("Triage SDK: casual route", session_id=session_id,
                               message=message[:50])
                    # Fase F: el casual es parte de la atención de pre-venta — si el canal
                    # no está asignado al flujo, tampoco se atiende el smalltalk.
                    _gate = self._preventa_channel_gate(db, session_id)
                    if _gate:
                        return _gate
                    # El triage solo rutea; la respuesta casual la genera SIEMPRE este
                    # método (única fuente con reglas de alcance: no recetas/tareas, etc.).
                    # Si reconocemos al huésped (recurrente/alojado), personalizamos el saludo.
                    guest_block = self._build_casual_guest_block(db, session_id)
                    # MOMENTO DE CIERRE: si el usuario se despide tras mostrar interés, el
                    # lead service decide captar el contacto. Una despedida se rutea a casual,
                    # así que la oferta de dejar datos se inyecta también acá.
                    capture_lead = await self._should_capture_lead_in_casual(db, message, session_id, history)
                    # ¿Ya se mostró disponibilidad antes? Entonces el cierre va directo al
                    # contacto, sin re-ofrecer disponibilidad ya vista.
                    availability_shown = self._availability_shown_in_session(db, session_id)
                    # Roster del equipo real: Aura reconoce a un empleado si le preguntan por
                    # él, pero NO inventa un vínculo con nombres que no están en el equipo.
                    team_block = self._build_team_roster_block(db)
                    from app.services import business_profile_service
                    profile = business_profile_service.get_profile(db)
                    response_text, casual_usage = await self._generate_casual_response(
                        message, history, language, guest_block, capture_lead, availability_shown,
                        is_whatsapp=(session_id or "").startswith("wa_"),
                        team_block=team_block, profile=profile,
                    )
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
                        "context_type": "casual",
                        "processing_time": f"{total_duration:.2f}s",
                        "session_info": self.get_session_info(session_id)
                    }

                is_postsale = (triage["route"] == ROUTE_POSTVENTA)

                # Fase F: canal no asignado al flujo de pre-venta → no se atiende la
                # consulta comercial. POST-VENTA pasa siempre (huésped con reserva).
                if not is_postsale:
                    _gate = self._preventa_channel_gate(db, session_id)
                    if _gate:
                        return _gate

            if is_postsale:
                logger.info("Post-sale context detected, delegating to HotelPostSaleService",
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
                    orch_result["context_type"] = "postsale"
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

            # El lock de la sesión ya no hace falta si borramos su hilo. No lo quitamos si
            # está tomado (un turno en vuelo): en ese caso lo dejamos y se reusará/limpiará
            # naturalmente. locked() es sincrónico y seguro de consultar acá.
            _lk = self._session_locks.get(session_id)
            if _lk is not None and not _lk.locked():
                self._session_locks.pop(session_id, None)

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
