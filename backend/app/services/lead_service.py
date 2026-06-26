"""
Servicio de gestión inteligente de leads
"""
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.lead import Lead
from app.services.lead_analyzer import lead_analyzer
from app.services.contact_service import ContactService
from app.core.logging_config import get_logger
from typing import Dict, List, Optional, Tuple
import re
from datetime import datetime, timedelta, timezone
from app.core.openai_client import get_async_openai
from app.config import settings
import json

logger = get_logger(__name__)

# Instancia global de ContactService
contact_service = ContactService()

class LeadService:
    def __init__(self):
        self.openai_client = get_async_openai()
        logger.info("Lead service initialized")
    
    async def process_message_for_lead(
        self,
        db: Session,
        message: str, 
        session_id: str,
        conversation_history: List[Dict],
        travel_context: str = "",
        geo_analysis: Dict = None
    ) -> Tuple[Dict, bool]:
        """
        Procesa un mensaje para análisis de lead y determina acciones
        
        Args:
            db: Sesión de base de datos
            message: Mensaje del usuario
            session_id: ID de sesión
            conversation_history: Historial de conversación
            travel_context: Contexto de viajes mencionados
            geo_analysis: Análisis geográfico (continente, países, ciudades)
            
        Returns:
            Tuple[Dict, bool]: (análisis_completo, debe_solicitar_contacto)
        """
        try:
            # 1. Analizar intención con GPT (con análisis geográfico)
            analysis = await lead_analyzer.analyze_lead_intent(
                message, conversation_history, travel_context, geo_analysis
            )
            
            # 2. Obtener o crear lead en base de datos
            lead = self._get_or_create_lead(db, session_id)

            # Piso del lead ANTES de re-analizar este turno: lo que el lead ya demostró en la
            # charla. El "momento de cierre" lo usa para no degradar a un lead interesado que
            # se despide (su análisis del turno de despedida puede leer FRIO efímero).
            persisted_floor = {
                "lead_type": lead.lead_type,
                "interest_score": lead.interest_score,
            }

            # 3. Actualizar lead con nuevo análisis.
            #    BLINDAJE: si el lead YA reservó (convertido/ganado), NO lo re-clasificamos.
            #    Un mensaje de cortesía post-reserva ("gracias, nos vemos") no tiene intención
            #    de compra y degradaría a un lead que es, de hecho, el más caliente posible.
            #    Igual seguimos capturando datos de contacto más abajo (eso no toca el scoring).
            is_converted = (lead.status == "converted") or (lead.kanban_stage == "won")
            if not is_converted:
                lead.update_from_analysis(analysis, travel_context)
            
            # 4. Extraer información de contacto si está presente (con historial)
            logger.info("About to extract contact info",
                       session_id=session_id,
                       message_preview=message[:100])
            
            contact_info = await self._extract_contact_info(message, conversation_history)
            
            logger.info("Contact info extraction completed",
                       session_id=session_id,
                       contact_info_keys=list(contact_info.keys()) if contact_info else [],
                       has_data=bool(contact_info))
            
            if contact_info:
                logger.info("Adding contact info to lead",
                           session_id=session_id,
                           lead_id=lead.id,
                           contact_data=contact_info)
                
                # Verificar estado ANTES de add_contact_info
                logger.info("Lead state BEFORE add_contact_info",
                           lead_id=lead.id,
                           name_before=lead.name,
                           last_name_before=lead.last_name,
                           email_before=lead.email,
                           phone_before=lead.phone)
                
                lead.add_contact_info(**contact_info)
                
                # Verificar estado DESPUÉS de add_contact_info
                logger.info("Lead state AFTER add_contact_info",
                           lead_id=lead.id,
                           name_after=lead.name,
                           last_name_after=lead.last_name,
                           email_after=lead.email,
                           phone_after=lead.phone)
                
                # 🆕 VISIÓN 360°: Crear/vincular Contact si tenemos teléfono.
                # El teléfono puede venir en ESTE mensaje (web: "soy Ana, 11-2233...") o ya
                # estar en el lead (WhatsApp: el número ES la sesión, se cargó al crearlo).
                # Usamos el efectivo para que un mensaje que solo trae el NOMBRE ("Mi nombre es
                # Ramiro") igual cree/vincule el Contact por el teléfono que ya conocemos —
                # si no, el nombre quedaba solo en el Lead y la conversación sin Contact
                # (aparecía "Sin nombre" en Conversaciones / perfil 360° vacío).
                effective_phone = contact_info.get('phone') or lead.phone
                if effective_phone:
                    try:
                        contact = contact_service.get_or_create_contact(
                            phone=effective_phone,
                            name=contact_info.get('name'),
                            last_name=contact_info.get('last_name'),
                            email=contact_info.get('email'),
                            db=db
                        )
                        
                        if contact:
                            # Vincular lead al contact
                            lead.contact_id = contact.id
                            
                            # Vincular conversación al contact
                            contact_service.link_conversation_by_session(
                                session_id=session_id,
                                contact_id=contact.id,
                                db=db
                            )
                            
                            # Incrementar contador de leads
                            contact.increment_leads()
                            
                            # 🆕 VISIÓN 360°: Actualizar métricas completas del contact
                            contact_service.update_contact_metrics(contact.id, db)
                            
                            logger.info("Lead linked to contact and metrics updated",
                                       lead_id=lead.id,
                                       contact_id=contact.id,
                                       session_id=session_id)
                    except Exception as e:
                        logger.error("Error linking lead to contact",
                                   lead_id=lead.id,
                                   error=str(e))
                
                logger.info("Contact info extracted", 
                           session_id=session_id,
                           message_preview=message[:50] + "..." if len(message) > 50 else message,
                           extracted_name=contact_info.get('name'),
                           extracted_last_name=contact_info.get('last_name'),
                           extracted_phone=contact_info.get('phone'),
                           extracted_email=contact_info.get('email'),
                           has_name=bool(contact_info.get('name')),
                           has_last_name=bool(contact_info.get('last_name')),
                           has_phone=bool(contact_info.get('phone')),
                           has_email=bool(contact_info.get('email')))
            
            db.commit()
            
            # Verificar que el commit funcionó
            logger.info("Database committed successfully", 
                       session_id=session_id,
                       lead_id=lead.id)
            
            # Refrescar el lead para ver el estado final
            db.refresh(lead)
            logger.info("Lead state AFTER commit and refresh",
                       lead_id=lead.id,
                       name_final=lead.name,
                       last_name_final=lead.last_name,
                       email_final=lead.email,
                       phone_final=lead.phone)
            
            # 5. Determinar si debe solicitar contacto (incluye "momento de cierre":
            #    si el usuario se despide tras mostrar interés, captamos el contacto).
            should_request = lead_analyzer.should_request_contact(
                analysis, len(conversation_history), message, persisted_floor=persisted_floor
            )
            
            # No solicitar si ya tiene contacto completo
            if lead.is_complete_lead():
                should_request = False

            # Bitácora: si Aura va a pedir el contacto, lo registramos (idempotente, best-effort).
            if should_request:
                try:
                    from app.services import lead_events_service as les
                    les.log_aura_action_once(db, lead.id, "contact_requested")
                except Exception:  # noqa: BLE001
                    pass

            # 6. Preparar respuesta completa
            complete_analysis = {
                **analysis,
                "lead_id": lead.id,
                "has_contact_info": lead.is_complete_lead(),
                "priority_score": lead.get_priority_score(),
                "should_request_contact": should_request,
                "contact_message": None
            }
            
            # 7. Generar mensaje de solicitud de contacto si es necesario
            if should_request and analysis.get('main_interest'):
                # Construir contexto conversacional para el LLM (últimos 4 mensajes)
                conversation_context = ""
                if conversation_history and len(conversation_history) > 0:
                    recent_messages = conversation_history[-4:]
                    context_parts = []
                    for msg in recent_messages:
                        role = "Usuario" if msg.get("role") == "user" else "Asistente"
                        content = msg.get("content", "")[:200]  # Limitar longitud
                        context_parts.append(f"{role}: {content}")
                    conversation_context = "\n".join(context_parts)
                
                # Usar LLM para generar mensaje natural
                complete_analysis["contact_message"] = await lead_analyzer.generate_contact_request_with_llm(
                    analysis, 
                    analysis.get('main_interest'),
                    conversation_context
                )
                
            logger.info("Lead processed successfully",
                       session_id=session_id,
                       lead_type=analysis.get('lead_type'),
                       should_request_contact=should_request,
                       has_complete_contact=lead.is_complete_lead())
            
            return complete_analysis, should_request
                
        except Exception as e:
            logger.error("Error processing message for lead",
                        session_id=session_id,
                        message_length=len(message) if message else 0,
                        error=str(e))
            # Rollback en caso de error
            db.rollback()
            # Retornar análisis básico en caso de error
            return {
                "lead_type": "FRIO",
                "interest_score": 1,
                "contact_readiness": False,
                "error": str(e)
            }, False
    
    def _get_or_create_lead(self, db: Session, session_id: str) -> Lead:
        """Obtiene lead existente o crea uno nuevo"""
        from app.models.conversation import Conversation
        
        lead = db.query(Lead).filter(Lead.session_id == session_id).first()
        
        if not lead:
            # Canal derivado del session_id: el webhook de WhatsApp usa el prefijo "wa_".
            is_wa = session_id.startswith("wa_")
            channel = "whatsapp" if is_wa else "web"
            # En WhatsApp el teléfono ES la sesión: lo guardamos en el lead para que Aura sepa
            # que ya lo conoce (y no se lo pida) y para arrancar el contacto con el dato.
            wa_phone = ("+" + session_id[3:]) if is_wa else None
            lead = Lead(
                session_id=session_id,
                lead_type="FRIO",
                interest_score=1,
                contact_readiness=False,
                channel=channel,
                phone=wa_phone,
            )
            db.add(lead)
            db.flush()  # Para obtener el ID
            
            logger.info("New lead created", session_id=session_id, lead_id=lead.id)
        
        # ✅ SIEMPRE marcar lead_generated=1 en la conversación (nuevo o existente)
        conversation = db.query(Conversation).filter(
            Conversation.session_id == session_id
        ).first()
        
        if conversation and conversation.lead_generated == 0:
            conversation.lead_generated = 1
            logger.info("Lead marked in conversation", 
                       session_id=session_id, 
                       lead_id=lead.id,
                       conversation_id=conversation.id)
        
        return lead
    
    def mark_lead_converted(
        self,
        db: Session,
        session_id: Optional[str] = None,
        contact_id: Optional[int] = None,
        booking_code: Optional[str] = None,
    ) -> bool:
        """Marca como CONVERTIDO el lead que originó una reserva.

        Un lead que reservó es el más caliente posible: lo dejamos CALIENTE/won y lo
        blindamos para que un mensaje de cortesía posterior ("gracias") no lo degrade
        (ver el guard en process_message_for_lead).

        Busca por session_id y, si no hay (ej. reserva web sin sesión), por contact_id.
        Best-effort: si no hay lead o algo falla, NO rompe la reserva (devuelve False).
        """
        try:
            lead = None
            if session_id:
                lead = db.query(Lead).filter(Lead.session_id == session_id).first()
            if not lead and contact_id:
                lead = (
                    db.query(Lead)
                    .filter(Lead.contact_id == contact_id)
                    .order_by(Lead.updated_at.desc())
                    .first()
                )
            if not lead:
                # Reserva sin conversación previa (landing puro): no hay lead que convertir.
                # El Contact 360° ya captura la compra; no fabricamos un lead artificial.
                logger.info("mark_lead_converted: sin lead asociado a la reserva",
                            session_id=session_id, contact_id=contact_id)
                return False

            if lead.status == "converted":
                return True  # ya estaba convertido (idempotente)

            lead.lead_type = "CALIENTE"
            lead.interest_score = 10
            lead.status = "converted"
            lead.contact_readiness = False
            lead.update_kanban_stage("won")
            if booking_code:
                lead.add_note(f"Reservó — {booking_code}")
            db.commit()
            # Bitácora: registrar la confirmación de reserva como acción de Aura (idempotente).
            try:
                from app.services import lead_events_service as les
                summary = f"Confirmó la reserva {booking_code}" if booking_code else "Confirmó la reserva"
                les.log_aura_action_once(db, lead.id, "booking_confirmed", summary=summary)
            except Exception:  # noqa: BLE001 — la bitácora nunca rompe la conversión
                pass
            logger.info("Lead marcado como convertido (reservó)",
                        lead_id=lead.id, session_id=lead.session_id, booking_code=booking_code)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo marcar el lead como convertido",
                           session_id=session_id, contact_id=contact_id, error=str(e))
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return False

    def _should_extract_contact_info(self, conversation_history: List[Dict]) -> bool:
        """
        Determina si el bot pidió información de contacto en el mensaje anterior
        
        Args:
            conversation_history: Historial de la conversación
            
        Returns:
            True si el bot pidió datos de contacto
        """
        if not conversation_history or len(conversation_history) < 2:
            return False
        
        # Obtener último mensaje del bot
        last_bot_message = None
        for msg in reversed(conversation_history):
            if msg.get('role') == 'assistant':
                last_bot_message = msg.get('content', '').lower()
                break
        
        if not last_bot_message:
            return False
        
        # Patrones que indican que el bot pidió datos
        contact_request_patterns = [
            'compartir tu nombre',
            'compartís tu nombre',
            'tu nombre',
            'pasame tu nombre',
            'decime tu nombre',
            'cómo te llamás',
            'como te llamas',
            'datos de contacto',
            'información de contacto',
            'nombre, apellido, email',
            'nombre y teléfono',
            'nombre, apellido',
            'me compartís',
            'me podrías compartir',
            'me das tu',
            'te dejo anotado',  # cierre WhatsApp ("te dejo anotado y te aviso…")
        ]
        
        return any(pattern in last_bot_message for pattern in contact_request_patterns)
    
    def _calculate_name_confidence(
        self,
        potential_name: str,
        message: str,
        bot_requested: bool,
        has_email: bool,
        has_phone: bool
    ) -> int:
        """
        Calcula score de confianza (0-100) de que el texto es un nombre real
        
        Args:
            potential_name: Nombre potencial extraído
            message: Mensaje completo
            bot_requested: Si el bot pidió datos
            has_email: Si el mensaje contiene email
            has_phone: Si el mensaje contiene teléfono
            
        Returns:
            Score de confianza (0-100)
        """
        score = 0
        
        # Factor 1: Formato del nombre (+30 puntos)
        # Debe estar capitalizado correctamente. Acepta nombre de pila solo ("Ramiro") O
        # nombre + apellido(s) ("Ramiro García") — el grupo de palabras extra es OPCIONAL
        # (`*`), según lo que el lead haya dado. Antes exigía 2+ palabras (`+`), por lo que un
        # nombre de pila solo (lo común en WhatsApp) no sumaba y el lead quedaba sin nombre.
        if re.match(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*$', potential_name):
            score += 30
        
        # Factor 2: Mensaje contiene email o teléfono (+25 puntos)
        if has_email or has_phone:
            score += 25
        
        # Factor 3: Bot pidió datos en mensaje anterior (+30 puntos)
        if bot_requested:
            score += 30
        
        # Factor 4: Longitud razonable (+10 puntos)
        if 4 <= len(potential_name) <= 50:
            score += 10
        
        # Factor 5: No contiene palabras MUY comunes (-50 puntos)
        # Solo palabras que claramente NO son nombres
        very_common_words = [
            'todo', 'toda', 'todos', 'todas',
            'bien', 'mal',
            'si', 'no', 'ok', 'dale',
            'claro', 'obvio', 'seguro',
            'gracias', 'muchas',
        ]
        
        name_lower = potential_name.lower()
        for word in very_common_words:
            if word in name_lower.split():
                score -= 50
                logger.debug("Name rejected - very common word",
                           potential_name=potential_name,
                           rejected_word=word)
                break
        
        return max(0, min(100, score))
    
    async def _extract_name_with_ai(self, message: str) -> Optional[Dict]:
        """
        Usa OpenAI para extraer nombre de forma inteligente (sin regex hardcoded)
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Dict con 'name' y 'last_name' o None si no hay nombre
        """
        try:
            prompt = f"""Extrae SOLO el nombre completo de la persona de este mensaje.

Reglas estrictas:
- Si hay un nombre de persona REAL, devuelve SOLO el nombre completo
- Si NO hay nombre de persona, devuelve exactamente: NINGUNO
- NO incluyas palabras como "mi nombre", "me llamo", etc.
- NO incluyas emails, teléfonos, ni otros datos
- NO incluyas expresiones comunes como "todo bien", "si claro", "ok", etc.
- Solo nombres de personas reales

Ejemplos:
- "Mi nombre, Frank Kikino, email@test.com" → "Frank Kikino"
- "Soy Juan Perez" → "Juan Perez"
- "Todo bien, me interesa" → "NINGUNO"
- "Si claro" → "NINGUNO"
- "María González, 341-1234567" → "María González"

Mensaje: "{message}"

Nombre extraído:"""

            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=50,
                timeout=30  # Timeout de 30 segundos para evitar esperas indefinidas
            )
            
            extracted_name = response.choices[0].message.content.strip()
            
            logger.info("Name extraction with AI completed",
                       message_preview=message[:100],
                       extracted_name=extracted_name)
            
            # Si OpenAI dice que no hay nombre
            if extracted_name.upper() == "NINGUNO" or not extracted_name:
                return None
            
            # Separar nombre y apellido
            name_parts = extracted_name.split()
            if len(name_parts) >= 1:
                result = {
                    'name': name_parts[0],
                    'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else None
                }
                
                logger.info("Name successfully extracted with AI",
                           full_name=extracted_name,
                           name=result['name'],
                           last_name=result.get('last_name'))
                
                return result
            
            return None
            
        except Exception as e:
            logger.error("Error extracting name with AI",
                        error=str(e),
                        message_preview=message[:100])
            return None
    
    async def _extract_contact_info(self, message: str, conversation_history: List[Dict] = None) -> Dict:
        """
        Extrae información de contacto del mensaje usando patrones inteligentes
        
        Args:
            message: Mensaje del usuario
            conversation_history: Historial de la conversación (opcional)
            
        Returns:
            Dict con información de contacto encontrada
        """
        contact_info = {}
        
        # 🤖 EXTRACCIÓN INTELIGENTE DE NOMBRES CON OPENAI
        # Verificar si debe extraer nombres (contexto conversacional)
        bot_requested = False
        if conversation_history:
            bot_requested = self._should_extract_contact_info(conversation_history)
        
        # Detectar si hay email o teléfono (indica intención de compartir datos).
        # El teléfono se detecta con un patrón parecido a un número real (8+ dígitos, con
        # espacios/guiones/+ permitidos): así "2 noches del 5 al 9" o "$1200" NO gatillan
        # una extracción de nombre por error (era el caso del antiguo r'[0-9]{3,}').
        has_email = bool(re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', message))
        digit_count = len(re.sub(r'\D', '', message))
        has_phone = bool(re.search(r'\+?[\d][\d\s\-().]{7,}\d', message)) and digit_count >= 8
        
        # Solo intentar extraer nombre si:
        # 1. El bot pidió datos, O
        # 2. El mensaje contiene email/teléfono (indica intención de compartir)
        should_extract_name = bot_requested or has_email or has_phone
        
        if should_extract_name:
            logger.info("Attempting name extraction with AI",
                       bot_requested=bot_requested,
                       has_email=has_email,
                       has_phone=has_phone)
            
            # Extraer nombre con OpenAI
            name_data = await self._extract_name_with_ai(message)
            
            if name_data:
                # Validar con scoring
                full_name = name_data['name']
                if name_data.get('last_name'):
                    full_name += ' ' + name_data['last_name']
                
                confidence = self._calculate_name_confidence(
                    full_name,
                    message,
                    bot_requested,
                    has_email,
                    has_phone
                )
                
                logger.info("Name confidence score calculated",
                           potential_name=full_name,
                           confidence=confidence,
                           bot_requested=bot_requested,
                           has_email=has_email,
                           has_phone=has_phone)
                
                # Aceptar si score >= 60
                if confidence >= 60:
                    contact_info['name'] = name_data['name']
                    if name_data.get('last_name'):
                        contact_info['last_name'] = name_data['last_name']
                    
                    logger.info("Name accepted after AI extraction and validation",
                               name=contact_info['name'],
                               last_name=contact_info.get('last_name'),
                               confidence=confidence)
                else:
                    logger.info("Name rejected - low confidence score",
                               potential_name=full_name,
                               confidence=confidence,
                               threshold=60)
            else:
                logger.debug("No name extracted by AI",
                            message_preview=message[:100])
        else:
            logger.debug("Name extraction skipped - no context or contact data",
                        bot_requested=bot_requested,
                        has_email=has_email,
                        has_phone=has_phone)
        
        # Extraer teléfono (intentar con regex primero)
        phone_patterns = [
            r'mi tel(?:éfono)?\s+es\s+([0-9\s\-\+\(\)]{8,20})',
            r'mi número es\s+([0-9\s\-\+\(\)]{8,20})',
            r'teléfono[:\s]+([0-9\s\-\+\(\)]{8,20})',
            r'tel[:\s]+([0-9\s\-\+\(\)]{8,20})',
            r'(\+?54\s?9?\s?[0-9\s\-]{8,15})',  # Formato argentino
            r'([0-9]{3}\s?[0-9]{6,9})',  # Formato general
            r'([0-9\s\-]{8,15})'  # Números generales
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                phone = re.sub(r'[^\d\+]', '', match.group(1))  # Limpiar formato
                if len(phone) >= 8:  # Mínimo 8 dígitos
                    contact_info['phone'] = match.group(1).strip()
                    break
        
        # Extraer email (intentar con regex primero)
        email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        email_match = re.search(email_pattern, message)
        if email_match:
            contact_info['email'] = email_match.group(1).lower()
        
        # 🆕 FALLBACK: Si no se detectó email o teléfono con regex, usar LLM
        if (not contact_info.get('email') or not contact_info.get('phone')) and (has_email or has_phone or bot_requested):
            logger.info("Regex extraction incomplete, trying LLM fallback",
                       has_email_regex=bool(contact_info.get('email')),
                       has_phone_regex=bool(contact_info.get('phone')))
            
            llm_contact = await self._extract_contact_with_llm(message)
            
            # Completar con datos del LLM si regex no los encontró
            if not contact_info.get('email') and llm_contact.get('email'):
                contact_info['email'] = llm_contact['email']
                logger.info("Email extracted by LLM fallback", email=contact_info['email'])
            
            if not contact_info.get('phone') and llm_contact.get('phone'):
                contact_info['phone'] = llm_contact['phone']
                logger.info("Phone extracted by LLM fallback", phone=contact_info['phone'])
        
        return contact_info
    
    async def _extract_contact_with_llm(self, message: str) -> Dict:
        """
        Extrae email y teléfono usando GPT-4o-mini como fallback
        cuando regex no detecta formatos no estándar
        """
        try:
            prompt = f"""Extrae la información de contacto del mensaje.

Mensaje: "{message}"

Responde en formato JSON:
{{
    "email": "email@example.com" o null,
    "phone": "número de teléfono" o null
}}

REGLAS:
- Email: Formato válido (usuario@dominio.ext)
- Teléfono: Cualquier número de 7+ dígitos, incluir código de país si se menciona
- Normalizar teléfono: remover espacios extras pero mantener formato legible
- Si no encuentras algo, usa null

Ejemplos:
- "contactame al 11 1234 5678" → {{"phone": "11 1234 5678"}}
- "mi cel es +54 9 11 1234-5678" → {{"phone": "+54 9 11 1234-5678"}}
- "escribime a juan@gmail.com" → {{"email": "juan@gmail.com"}}

Responde SOLO con el JSON."""
            
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL_FAST,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=30
            )
            
            result = json.loads(response.choices[0].message.content)
            
            logger.info("Contact info extracted with LLM",
                       email=result.get('email'),
                       phone=result.get('phone'),
                       tokens_used=response.usage.total_tokens)
            
            return result
            
        except Exception as e:
            logger.error("Error extracting contact with LLM",
                        error=str(e),
                        message_preview=message[:100])
            return {}
    
    def get_lead_by_session(self, session_id: str) -> Optional[Dict]:
        """Obtiene lead por session_id"""
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.session_id == session_id).first()
            return lead.to_dict() if lead else None
        finally:
            db.close()
    
    def get_active_leads(self, limit: int = 50, include_unnamed: bool = False,
                         include_converted: bool = False) -> List[Dict]:
        """Obtiene leads ordenados por prioridad.

        `include_unnamed=True` incluye los contactos "crudos": leads con teléfono pero sin
        nombre todavía (ej. un número de WhatsApp que consultó antes de reservar). Por
        defecto se ocultan (vista de calificados). Siempre se exige email o teléfono para
        no traer leads totalmente vacíos.

        `include_converted=True` trae TODOS los estados (incl. los convertidos/ganados, que
        reservaron). Por defecto solo `status="active"` — pero la LISTA del backoffice quiere
        ver todo (igual que el tablero), así que pasa True. El badge "Reservó" los distingue.
        """
        db = SessionLocal()
        try:
            filters = [
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None))),
            ]
            if not include_converted:
                filters.append(Lead.status == "active")
            if not include_unnamed:
                filters.append(Lead.name.isnot(None))
            leads = db.query(Lead).filter(*filters).order_by(
                Lead.updated_at.desc()
            ).limit(limit).all()
            
            # Calcular prioridad y ordenar
            lead_dicts = [lead.to_dict() for lead in leads]
            lead_dicts.sort(key=lambda x: self._calculate_priority(x), reverse=True)
            
            return lead_dicts
        finally:
            db.close()
    
    def get_leads_by_type(self, lead_type: str) -> List[Dict]:
        """Obtiene leads por tipo (CALIENTE, TIBIO, FRIO)"""
        db = SessionLocal()
        try:
            leads = db.query(Lead).filter(
                Lead.lead_type == lead_type,
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).order_by(Lead.updated_at.desc()).all()
            
            return [lead.to_dict() for lead in leads]
        finally:
            db.close()
    
    def get_leads_ready_for_contact(self) -> List[Dict]:
        """Obtiene leads listos para ser contactados"""
        db = SessionLocal()
        try:
            leads = db.query(Lead).filter(
                Lead.contact_readiness == True,
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).order_by(Lead.updated_at.desc()).all()
            
            return [lead.to_dict() for lead in leads]
        finally:
            db.close()
    
    def update_lead_status(self, lead_id: int, status: str) -> bool:
        """Actualiza el status de un lead"""
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.status = status
                lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
                logger.info("Lead status updated", lead_id=lead_id, new_status=status)
                return True
            return False
        finally:
            db.close()

    def update_lead_fields(self, lead_id: int, fields: Dict) -> Optional[Dict]:
        """Edita datos de contacto de un lead (nombre, apellido, email, teléfono).

        Solo toca los campos provistos (no None). Si el lead está vinculado a un Contact,
        propaga el cambio al Contact para mantener la Visión 360° consistente.
        Devuelve el lead actualizado (dict) o None si no existe.
        """
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return None

            allowed = ("name", "last_name", "email", "phone")
            for key in allowed:
                if key in fields and fields[key] is not None:
                    val = str(fields[key]).strip() or None
                    setattr(lead, key, val)
            lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Propagar al Contact vinculado (si lo hay) para no desincronizar el 360°.
            if lead.contact_id:
                from app.models.contact import Contact
                c = db.query(Contact).filter(Contact.id == lead.contact_id).first()
                if c:
                    if "name" in fields and fields["name"] is not None:
                        c.first_name = (fields["name"] or "").strip() or None
                    if "last_name" in fields and fields["last_name"] is not None:
                        c.last_name = (fields["last_name"] or "").strip() or None
                    if c.first_name or c.last_name:
                        c.full_name = " ".join(p for p in [c.first_name, c.last_name] if p)
                    if "email" in fields and fields["email"] is not None:
                        c.email = (fields["email"] or "").strip() or None

            db.commit()
            db.refresh(lead)
            logger.info("Lead fields updated", lead_id=lead_id, fields=list(fields.keys()))
            return lead.to_dict() if hasattr(lead, "to_dict") else {
                "id": lead.id, "name": lead.name, "last_name": lead.last_name,
                "email": lead.email, "phone": lead.phone,
            }
        finally:
            db.close()

    def delete_lead(self, lead_id: int) -> bool:
        """Elimina un lead por su ID. Devuelve True si existía y se borró."""
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return False
            db.delete(lead)
            db.commit()
            logger.info("Lead deleted", lead_id=lead_id)
            return True
        finally:
            db.close()
    
    def get_lead_stats(self) -> Dict:
        """Obtiene estadísticas de leads"""
        db = SessionLocal()
        try:
            total_leads = db.query(Lead).filter(
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            active_leads = db.query(Lead).filter(
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            
            # Por tipo
            calientes = db.query(Lead).filter(
                Lead.lead_type == "CALIENTE",
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            tibios = db.query(Lead).filter(
                Lead.lead_type == "TIBIO",
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            frios = db.query(Lead).filter(
                Lead.lead_type == "FRIO",
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            
            # Con contacto completo
            with_contact = db.query(Lead).filter(
                Lead.name.isnot(None),
                Lead.phone.isnot(None),
                Lead.status == "active"
            ).count()
            
            # Listos para contactar
            ready_for_contact = db.query(Lead).filter(
                Lead.contact_readiness == True,
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            
            return {
                "total_leads": total_leads,
                "active_leads": active_leads,
                "by_type": {
                    "calientes": calientes,
                    "tibios": tibios,
                    "frios": frios
                },
                "with_complete_contact": with_contact,
                "ready_for_contact": ready_for_contact,
                "conversion_rate": (with_contact / active_leads * 100) if active_leads > 0 else 0
            }
        finally:
            db.close()
    
    def _calculate_priority(self, lead_dict: Dict) -> float:
        """Calcula prioridad de un lead para ordenamiento"""
        classification = lead_dict.get('classification', {})
        metadata = lead_dict.get('metadata', {})
        contact_info = lead_dict.get('contact_info', {})
        
        score = classification.get('interest_score', 1)
        
        # Bonificaciones
        if classification.get('lead_type') == 'CALIENTE':
            score += 3
        elif classification.get('lead_type') == 'TIBIO':
            score += 1
        
        if contact_info.get('name') and contact_info.get('phone'):
            score += 2
        
        if classification.get('contact_readiness'):
            score += 1
        
        # Penalización por antigüedad (leads más recientes tienen prioridad)
        if metadata.get('updated_at'):
            try:
                updated = datetime.fromisoformat(metadata['updated_at'].replace('Z', '+00:00'))
                hours_old = (datetime.now(timezone.utc).replace(tzinfo=None) - updated.replace(tzinfo=None)).total_seconds() / 3600
                if hours_old > 24:
                    score -= min(hours_old / 24, 2)  # Máximo -2 puntos
            except Exception as e:
                logger.debug("No se pudo calcular antigüedad del lead para el score", error=str(e))

        return max(score, 0)
    
    async def create_event_lead(
        self,
        db: Session,
        session_id: str,
        event_info: Dict,
        contact_info: Dict
    ):
        """
        Crea o actualiza lead con información de evento temporal
        
        Args:
            db: Sesión de base de datos
            session_id: ID de sesión
            event_info: Info del evento (name, type, countries, year)
            contact_info: Info de contacto (name, email, phone)
            
        Returns:
            Lead creado/actualizado
        """
        try:
            # Reutilizar método existente
            lead = self._get_or_create_lead(db, session_id)
            
            # Agregar info de evento (campos nuevos)
            lead.is_event_lead = True
            lead.event_name = event_info.get("event_name")
            lead.event_type = event_info.get("event_type")
            
            # Guardar países como JSON string
            import json
            if event_info.get("related_countries"):
                lead.event_countries = json.dumps(event_info["related_countries"])
            
            lead.event_year = event_info.get("next_edition")
            
            # Actualizar main_interest con evento
            lead.main_interest = f"{event_info.get('event_name')} {event_info.get('next_edition', '')}"
            
            # Usar método existente para agregar contacto
            lead.add_contact_info(**contact_info)
            
            # Marcar como lead caliente (interés específico)
            lead.lead_type = "CALIENTE"
            lead.interest_score = 8
            lead.contact_readiness = True
            
            db.commit()
            
            logger.info("Event lead created/updated",
                       session_id=session_id,
                       lead_id=lead.id,
                       event_name=lead.event_name,
                       has_contact=lead.is_complete_lead())
            
            return lead
            
        except Exception as e:
            logger.error("Error creating event lead",
                        session_id=session_id,
                        error=str(e))
            db.rollback()
            raise

# Instancia global del servicio de leads
lead_service = LeadService()
