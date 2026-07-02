"""
Analizador inteligente de leads usando GPT
Evoluciona el sistema actual de leads CALIENTE/TIBIO/FRÍO con análisis contextual
"""
from app.core.openai_client import get_async_openai
from typing import Dict, List, Optional, Tuple
from app.config import settings
from app.core.logging_config import get_logger
import json
import time

logger = get_logger(__name__)

class LeadAnalyzer:
    def __init__(self):
        self.client = get_async_openai()
        logger.info("Lead analyzer initialized")
    
    async def analyze_lead_intent(
        self, 
        message: str, 
        conversation_history: List[Dict],
        travel_context: str = "",
        geo_analysis: Dict = None
    ) -> Dict:
        """
        Analiza la intención del usuario y clasifica el lead de manera inteligente
        
        Args:
            message: Mensaje actual del usuario
            conversation_history: Historial de conversación
            travel_context: Contexto de viajes mencionados
            geo_analysis: Análisis geográfico (continente, países, ciudades)
            
        Returns:
            Dict con análisis completo del lead
        """
        try:
            start_time = time.time()
            
            # Construir contexto de conversación
            conversation_context = self._build_conversation_context(conversation_history)
            
            # Prompt para análisis inteligente (con análisis geográfico)
            analysis_prompt = self._build_analysis_prompt(
                message, conversation_context, travel_context, geo_analysis
            )
            
            logger.debug("Analyzing lead intent", 
                        message_length=len(message),
                        history_messages=len(conversation_history))
            
            # Llamar a GPT para análisis. Clasificación JSON a baja temperatura → el modelo
            # económico (gpt-4o-mini) alcanza; corre en cada turno, así que el ahorro pesa.
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[
                    {"role": "system", "content": analysis_prompt},
                    {"role": "user", "content": f"Analiza este mensaje: '{message}'"}
                ],
                temperature=0.1,  # Baja temperatura para análisis consistente
                max_tokens=500,
                timeout=30  # Timeout de 30 segundos
            )
            
            # Parsear respuesta JSON
            analysis_text = response.choices[0].message.content
            analysis = self._parse_analysis_response(analysis_text)
            
            duration = time.time() - start_time
            
            logger.info("Lead analysis completed",
                       lead_type=analysis.get('lead_type'),
                       interest_score=analysis.get('interest_score'),
                       contact_readiness=analysis.get('contact_readiness'),
                       duration=f"{duration:.2f}s")
            
            return analysis
            
        except Exception as e:
            logger.error("Error analyzing lead intent", 
                        message_length=len(message) if message else 0,
                        error=str(e))
            
            # Fallback a análisis básico
            return self._fallback_analysis(message)
    
    def _build_conversation_context(self, history: List[Dict]) -> str:
        """Construye contexto de conversación para el análisis"""
        if not history:
            return "No hay historial previo."
        
        # Tomar últimos 4 mensajes para contexto
        recent_history = history[-4:]
        context_parts = []
        
        for msg in recent_history:
            role = "Usuario" if msg["role"] == "user" else "Asistente"
            content = msg["content"][:200]  # Limitar longitud
            context_parts.append(f"{role}: {content}")
        
        return "\n".join(context_parts)
    
    def _build_analysis_prompt(self, message: str, conversation: str, travel_context: str, geo_analysis: Dict = None) -> str:
        """Construye el prompt para análisis de leads con información geográfica"""
        
        # 🆕 Construir información geográfica detectada (SIN hardcodear destinos)
        geo_info = ""
        if geo_analysis:
            detected_items = []
            
            if geo_analysis.get('continent'):
                detected_items.append(f"Continente: {geo_analysis['continent']}")
            
            if geo_analysis.get('countries'):
                countries_list = ", ".join(geo_analysis['countries'][:3])  # Máximo 3 países
                if len(geo_analysis['countries']) > 3:
                    countries_list += f" y {len(geo_analysis['countries']) - 3} más"
                detected_items.append(f"Países: {countries_list}")
            
            if geo_analysis.get('cities'):
                cities_list = ", ".join(geo_analysis['cities'][:3])  # Máximo 3 ciudades
                if len(geo_analysis['cities']) > 3:
                    cities_list += f" y {len(geo_analysis['cities']) - 3} más"
                detected_items.append(f"Ciudades: {cities_list}")
            
            if detected_items:
                geo_info = f"\n\nDESTINOS DETECTADOS EN EL MENSAJE:\n" + "\n".join(f"- {item}" for item in detected_items)
        
        return f"""Eres un experto analizador de intenciones de compra en turismo. 

SISTEMA DE CLASIFICACIÓN DE LEADS:

🟢 LEAD CALIENTE: Listo para comprar o muy interesado
- Muestra interés directo sin obstáculos importantes
- Pregunta por reservas, precios específicos, disponibilidad
- Acepta condiciones o muestra urgencia

🟡 LEAD TIBIO: Interesado pero con obstáculos
- Muestra interés pero tiene dudas o limitaciones
- Obstáculos comunes: precio, fechas, tiempo para decidir
- Necesita más información o resolución de dudas

🔵 LEAD FRÍO: Solo explorando
- Preguntas generales sin compromiso
- "Solo estoy mirando", consultas muy básicas
- No muestra señales claras de intención de compra

CONTEXTO DE CONVERSACIÓN:
{conversation}

INFORMACIÓN DE VIAJES MENCIONADA:
{travel_context}{geo_info}

INSTRUCCIONES:
Analiza el mensaje del usuario y responde SOLO en formato JSON con esta estructura:

{{
    "lead_type": "CALIENTE|TIBIO|FRIO",
    "interest_score": 1-10,
    "obstacle": "precio|fechas|tiempo|informacion|ninguno",
    "contact_readiness": true/false,
    "main_interest": "destino o paquete principal mencionado",
    "secondary_interests": ["otro destino 1", "otro destino 2"],
    "reasoning": "breve explicación del análisis",
    "suggested_response_tone": "entusiasta|consultivo|informativo",
    "next_action": "solicitar_contacto|resolver_dudas|dar_informacion|mantener_conversacion"
}}

REGLAS PARA "secondary_interests":
- Lista vacía [] si solo hay un destino de interés
- Incluir otros destinos mencionados en la conversación que no sean el principal
- Máximo 3 elementos

REGLAS CRÍTICAS PARA "main_interest":
1. PRIORIDAD MÁXIMA: Usa los destinos detectados arriba (países, ciudades específicas)
2. Si hay múltiples destinos, elige el más específico (ciudad > país > continente)
3. Si menciona paquete + destino, combina ambos: "Paquete de 7 días a [destino]"
4. EVITA respuestas genéricas como "consulta general" o "viaje"
5. Si NO hay destino claro, usa "Consulta sobre viajes" (solo como último recurso)

EJEMPLOS DE BUEN "main_interest":
- "Paquete a París" (ciudad específica)
- "Viaje a Italia" (país específico)
- "Tour por Europa" (continente con contexto)
- "Paquete de 10 días a Japón" (paquete + destino)

IMPORTANTE: 
- Si dice "no quiero reservar" pero "quiero que me contacten" = TIBIO con contact_readiness: true
- Si muestra interés en destino específico = capturar en main_interest con máxima precisión
- Si tiene dudas = obstacle correspondiente
- Responde SOLO el JSON, sin texto adicional"""

    def _parse_analysis_response(self, response_text: str) -> Dict:
        """Parsea la respuesta JSON del análisis"""
        try:
            # Limpiar respuesta y extraer JSON
            response_text = response_text.strip()
            
            # Buscar JSON en la respuesta
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                analysis = json.loads(json_str)
                
                # Validar campos requeridos
                required_fields = ['lead_type', 'interest_score', 'contact_readiness']
                for field in required_fields:
                    if field not in analysis:
                        logger.warning(f"Missing field in analysis: {field}")
                        return self._fallback_analysis("")
                
                return analysis
            else:
                logger.warning("No JSON found in analysis response")
                return self._fallback_analysis("")
                
        except json.JSONDecodeError as e:
            logger.error("Error parsing analysis JSON", error=str(e))
            return self._fallback_analysis("")
        except Exception as e:
            logger.error("Unexpected error parsing analysis", error=str(e))
            return self._fallback_analysis("")
    
    def _fallback_analysis(self, message: str) -> Dict:
        """Análisis de fallback cuando falla el análisis inteligente"""
        # Análisis básico por palabras clave como backup
        message_lower = message.lower() if message else ""
        
        # Detectar interés básico
        interest_keywords = ['me interesa', 'quiero', 'me gusta', 'reservar']
        contact_keywords = ['contacten', 'llamen', 'escriban', 'asesor']
        
        has_interest = any(keyword in message_lower for keyword in interest_keywords)
        wants_contact = any(keyword in message_lower for keyword in contact_keywords)
        
        if has_interest and wants_contact:
            lead_type = "TIBIO"
            interest_score = 7
        elif has_interest:
            lead_type = "CALIENTE"
            interest_score = 8
        elif wants_contact:
            lead_type = "TIBIO"
            interest_score = 6
        else:
            lead_type = "FRIO"
            interest_score = 3
        
        return {
            "lead_type": lead_type,
            "interest_score": interest_score,
            "obstacle": "ninguno",
            "contact_readiness": wants_contact,
            "main_interest": "consulta general",
            "reasoning": "Análisis de fallback por palabras clave",
            "suggested_response_tone": "consultivo",
            "next_action": "mantener_conversacion",
            "fallback_used": True
        }
    
    # Señales de que el usuario se está despidiendo, postergando o RECHAZANDO POR PRECIO.
    # Es el "momento de cierre": si mostró interés, conviene captar el contacto antes
    # de que se vaya sin convertir (best practice de captación conversacional). Incluimos
    # objeciones de precio + despedidas informales porque un lead que se va por precio es
    # justo a quien conviene retener (ofrecerle avisarle de promos / novedades).
    _EXIT_SIGNALS = (
        # Postergación / despedida
        "lo voy a pensar", "lo pienso", "lo consulto", "lo veo", "después veo",
        "despues veo", "más adelante", "mas adelante", "otro día", "otro dia",
        "gracias por todo", "muchas gracias", "nada más", "nada mas", "chau",
        "adiós", "adios", "hasta luego", "lo hablo", "tengo que ver", "veré",
        "vere", "let me think", "i'll think", "thanks anyway", "maybe later",
        # Despedidas informales (cierre con "gracias" suelto / descarte)
        "gracias igual", "igual gracias", "bueno gracias", "ok gracias", "dale gracias",
        "dejá", "deja", "déjalo", "dejalo", "lo dejo", "ahí veo", "ahi veo", "después te",
        # Objeción de precio (rechazo que igual amerita captar para promos)
        "muy caro", "carísimo", "carisimo", "está caro", "esta caro", "es caro",
        "se me va de presupuesto", "fuera de presupuesto", "no me alcanza", "es mucho",
        "demasiado caro", "muy costoso", "no me da el presupuesto", "too expensive",
    )

    def _is_exit_intent(self, message: str) -> bool:
        text = (message or "").lower()
        return any(sig in text for sig in self._EXIT_SIGNALS)

    # Umbrales de captura de contacto — DEFAULTS de fábrica (Fase A, flujos configurables).
    # Estos son los valores históricos del comportamiento actual: son el piso fail-open.
    # El flujo "flujo_preventa" del Centro puede sobreescribirlos vía `criteria`; sin
    # criteria (None) el comportamiento es EXACTAMENTE el de siempre (paridad).
    CONTACT_CRITERIA_DEFAULTS = {
        "min_msgs": 2,        # nunca pedir contacto antes de N mensajes
        "score_caliente": 7,  # interés mínimo de un lead CALIENTE para pedir contacto
        "score_tibio": 6,     # interés mínimo de un lead TIBIO
        "msgs_tibio": 4,      # mensajes mínimos para pedir contacto a un TIBIO
    }

    def should_request_contact(self, analysis: Dict, conversation_length: int,
                               message: str = "", persisted_floor: Dict = None,
                               criteria: Dict = None) -> bool:
        """
        Determina si es el momento apropiado para solicitar datos de contacto

        Args:
            analysis: Resultado del análisis de lead (de ESTE turno)
            conversation_length: Número de mensajes en la conversación
            message: Mensaje actual (para detectar intención de salida/despedida)
            persisted_floor: Estado YA persistido del lead {lead_type, interest_score} de los
                turnos previos. El análisis del turno solo mira los últimos mensajes, así que en
                una DESPEDIDA ("dejame pensarlo") puede leer FRIO aunque el lead ya haya
                demostrado interés antes. El piso evita esa degradación efímera.
            criteria: Umbrales del flujo configurado en el Centro (opcional). None → defaults
                de fábrica = comportamiento histórico exacto.

        Returns:
            bool: True si debe solicitar contacto
        """
        c = {**self.CONTACT_CRITERIA_DEFAULTS, **(criteria or {})}

        # No solicitar contacto en los primeros mensajes
        if conversation_length < c["min_msgs"]:
            return False

        # Si ya expresó que quiere ser contactado
        if analysis.get('contact_readiness', False):
            return True

        # Lead caliente con interés alto
        if (analysis.get('lead_type') == 'CALIENTE' and
            analysis.get('interest_score', 0) >= c["score_caliente"]):
            return True

        # Lead tibio que ya tuvo varias interacciones
        if (analysis.get('lead_type') == 'TIBIO' and
            conversation_length >= c["msgs_tibio"] and
            analysis.get('interest_score', 0) >= c["score_tibio"]):
            return True

        # MOMENTO DE CIERRE: el usuario se despide/posterga/objeta el precio tras una
        # conversación con algo de interés. Captamos el contacto para hacer seguimiento antes
        # de que se vaya sin convertir, de forma natural y no invasiva.
        #
        # La SEÑAL DE CIERRE se deriva PRIMERO del análisis SEMÁNTICO del LLM (que entiende el
        # mensaje, no depende de adivinar frases): el modelo ya marca `obstacle` (precio/fechas/
        # tiempo), `next_action`='solicitar_contacto', etc. La lista de palabras `_is_exit_intent`
        # queda solo como RED DE RESPALDO barata para despedidas explícitas.
        obstacle = (analysis.get('obstacle') or '').lower()
        next_action = (analysis.get('next_action') or '').lower()
        llm_close_signal = (
            obstacle in ('precio', 'fechas', 'tiempo')      # el LLM detectó una objeción real
            or next_action == 'solicitar_contacto'           # el LLM cree que es momento de captar
        )
        is_close_moment = llm_close_signal or self._is_exit_intent(message)

        if is_close_moment and conversation_length >= c["min_msgs"]:
            # Umbral bajo a propósito: alguien que preguntó y se va (o objeta el precio) es justo
            # a quien conviene retener. Solo excluimos el caso claramente sin interés (FRÍO con
            # score muy bajo). El interés se evalúa contra el MÁXIMO entre el análisis del turno y
            # el piso persistido: si el lead YA era TIBIO/CALIENTE, la despedida no lo degrada.
            turn_type = analysis.get('lead_type', 'FRIO')
            turn_score = analysis.get('interest_score', 0)
            floor_type = (persisted_floor or {}).get('lead_type', 'FRIO')
            floor_score = (persisted_floor or {}).get('interest_score', 0)
            no_interest = (
                (turn_type == 'FRIO' and turn_score <= 2) and
                (floor_type == 'FRIO' and (floor_score or 0) <= 2)
            )
            if not no_interest:
                return True

        return False
    
    async def generate_contact_request_with_llm(
        self,
        analysis: Dict,
        travel_interest: str,
        conversation_context: str = ""
    ) -> str:
        """
        Genera mensaje COMPLETAMENTE natural para solicitar contacto usando LLM
        
        Args:
            analysis: Análisis del lead (tipo, obstáculo, score)
            travel_interest: Destino o paquete de interés
            conversation_context: Últimos mensajes de la conversación
            
        Returns:
            Mensaje personalizado generado por IA
        """
        try:
            lead_type = analysis.get('lead_type', 'TIBIO')
            obstacle = analysis.get('obstacle', 'ninguno')
            interest_score = analysis.get('interest_score', 5)
            suggested_tone = analysis.get('suggested_response_tone', 'consultivo')
            
            # Construir contexto de obstáculos
            obstacle_guidance = ""
            if obstacle == 'precio':
                obstacle_guidance = "Menciona opciones de financiación y formas de pago flexibles."
            elif obstacle == 'fechas':
                obstacle_guidance = "Ofrece notificación de nuevas fechas disponibles."
            elif obstacle == 'tiempo':
                obstacle_guidance = "Menciona que no hay apuro y que podemos mantenerlo informado."
            
            prompt = f"""Genera un mensaje NATURAL y conversacional para solicitar datos de contacto en una conversación de turismo.

CONTEXTO DEL LEAD:
- Tipo: {lead_type}
- Interés específico en: {travel_interest}
- Score de interés: {interest_score}/10
- Obstáculo detectado: {obstacle}
- Tono sugerido: {suggested_tone}

CONVERSACIÓN RECIENTE:
{conversation_context if conversation_context else "Primera interacción sobre este tema"}

INSTRUCCIONES:
1. Usa un tono {suggested_tone} y amigable
2. Menciona ESPECÍFICAMENTE el destino de interés: "{travel_interest}"
3. {obstacle_guidance if obstacle_guidance else "Enfatiza la atención personalizada"}
4. Solicita: nombre, apellido, email y teléfono
5. Hazlo sentir natural y conversacional, NO robótico
6. Máximo 4-5 líneas de texto
7. Usa emojis con moderación (máximo 2)
8. NO uses frases genéricas como "no dudes en contactarnos"

IMPORTANTE: 
- El usuario debe sentir que un humano le está escribiendo
- Conecta con lo que se habló en la conversación
- Personaliza según el tipo de lead y obstáculo

Mensaje:"""

            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,  # Suficiente para esta tarea creativa
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,  # Un poco de creatividad para naturalidad
                max_tokens=200,
                timeout=30
            )
            
            generated_message = response.choices[0].message.content.strip()
            
            logger.info("Contact request message generated with LLM",
                       lead_type=lead_type,
                       obstacle=obstacle,
                       interest=travel_interest[:50],
                       message_length=len(generated_message),
                       tokens_used=response.usage.total_tokens if hasattr(response, 'usage') else 0)
            
            return generated_message
            
        except Exception as e:
            logger.error("Error generating contact message with LLM, using fallback",
                        error=str(e),
                        lead_type=analysis.get('lead_type'))
            # Fallback a método con templates
            return self.get_contact_request_message(analysis, travel_interest)
    
    def get_contact_request_message(self, analysis: Dict, travel_interest: str) -> str:
        """
        Genera mensaje natural para solicitar datos de contacto (FALLBACK)
        
        NOTA: Este método se mantiene como fallback. 
        Usa generate_contact_request_with_llm() para mensajes más naturales.
        
        Args:
            analysis: Análisis del lead
            travel_interest: Destino o paquete de interés
            
        Returns:
            str: Mensaje personalizado para solicitar contacto
        """
        lead_type = analysis.get('lead_type', 'TIBIO')
        obstacle = analysis.get('obstacle', 'ninguno')
        
        if lead_type == 'CALIENTE':
            return f"""¡Excelente! Veo que {travel_interest} realmente te interesa. 

Para darte la mejor atención personalizada y resolver todas tus dudas, ¿te gustaría que uno de nuestros asesores especializados te contacte? 

Ellos pueden ayudarte con:
• Disponibilidad exacta y opciones de fechas
• Detalles específicos del itinerario  
• Formas de pago y promociones disponibles
• Cualquier personalización que necesites

¿Me podrías compartir tu nombre, apellido, email y número de teléfono?"""

        elif obstacle == 'precio':
            return f"""Entiendo tu preocupación por el presupuesto para {travel_interest}. 

Nuestros asesores pueden ayudarte con:
• Opciones de financiación y formas de pago flexibles
• Paquetes alternativos más económicos
• Promociones especiales y descuentos disponibles

¿Te gustaría que un asesor te contacte para explorar estas opciones? Solo necesito tu nombre, apellido, email y teléfono."""

        elif obstacle == 'fechas':
            return f"""Comprendo que las fechas disponibles para {travel_interest} no se ajustan a lo que necesitás.

Podemos ayudarte con:
• Notificarte cuando haya nuevas fechas disponibles
• Buscar paquetes similares en tus fechas preferidas
• Crear opciones personalizadas para tus fechas

¿Te gustaría que te mantengamos informado? Compárteme tu nombre, apellido, email y teléfono."""

        else:  # TIBIO general
            return f"""Me alegra que {travel_interest} haya captado tu interés.

Para brindarte información más detallada y personalizada, ¿te gustaría que uno de nuestros asesores especializados te contacte?

Pueden resolver todas tus dudas sin ningún compromiso y mantenerte al tanto de las mejores opciones disponibles.

¿Me compartís tu nombre, apellido, email y número de teléfono?"""

# Instancia global del analizador de leads
lead_analyzer = LeadAnalyzer()
