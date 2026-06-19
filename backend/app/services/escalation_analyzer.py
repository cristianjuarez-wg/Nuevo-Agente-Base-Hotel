"""
Servicio de análisis inteligente de escalación de tickets
Usa GPT para determinar si un problema requiere intervención humana
SIN hardcodear casos específicos
"""
from app.core.openai_client import get_async_openai
from typing import Dict, Optional
from app.config import settings
from app.core.logging_config import get_logger
import json
import time

logger = get_logger(__name__)

class EscalationAnalyzer:
    """Analiza si un problema requiere escalación a operaciones humanas"""
    
    def __init__(self):
        self.client = get_async_openai()
        logger.info("Escalation analyzer initialized")
    
    async def analyze_escalation_need(
        self, 
        message: str, 
        package_info: Dict,
        conversation_history: list = None
    ) -> Dict:
        """
        Analiza si el problema requiere escalación a operaciones
        
        Args:
            message: Mensaje del usuario
            package_info: Información del paquete (fechas, servicios, etc.)
            conversation_history: Historial de conversación (opcional)
            
        Returns:
            Dict con:
            - requires_escalation: bool
            - urgency_level: "critical" | "high" | "medium" | "low"
            - escalation_reason: str (explicación)
            - suggested_category: str
            - can_agent_help: bool
            - recommended_response_tone: str
        """
        try:
            start_time = time.time()
            
            # Construir contexto del paquete
            package_context = self._build_package_context(package_info)
            
            # Construir contexto de conversación
            conversation_context = self._build_conversation_context(conversation_history)
            
            # Prompt para análisis inteligente
            analysis_prompt = self._build_escalation_prompt(
                message, package_context, conversation_context
            )
            
            logger.debug("Analyzing escalation need",
                        message_length=len(message),
                        has_package_info=bool(package_info))
            
            # Llamar a GPT para análisis
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": analysis_prompt},
                    {"role": "user", "content": f"Analiza este mensaje del cliente: '{message}'"}
                ],
                temperature=0.1,  # Baja temperatura para análisis consistente
                max_tokens=600,
                timeout=30
            )
            
            # Parsear respuesta JSON
            analysis_text = response.choices[0].message.content
            analysis = self._parse_analysis_response(analysis_text)
            
            duration = time.time() - start_time
            
            logger.info("Escalation analysis completed",
                       requires_escalation=analysis.get('requires_escalation'),
                       urgency_level=analysis.get('urgency_level'),
                       category=analysis.get('suggested_category'),
                       duration=f"{duration:.2f}s")
            
            return analysis
            
        except Exception as e:
            logger.error("Error analyzing escalation need",
                        message_length=len(message) if message else 0,
                        error=str(e))
            
            # Fallback conservador: escalar por defecto en caso de error
            return self._fallback_analysis(message)
    
    def _build_package_context(self, package_info: Dict) -> str:
        """Construye contexto del paquete para el análisis"""
        if not package_info:
            return "No hay información del paquete disponible."
        
        context_parts = []
        
        # Información básica
        if package_info.get('booking_code'):
            context_parts.append(f"Código de reserva: {package_info['booking_code']}")
        
        if package_info.get('destination'):
            context_parts.append(f"Destino: {package_info['destination']}")
        
        # Fechas del viaje
        if package_info.get('departure_date'):
            context_parts.append(f"Fecha de salida: {package_info['departure_date']}")
        
        if package_info.get('return_date'):
            context_parts.append(f"Fecha de regreso: {package_info['return_date']}")
        
        # Estado del viaje
        if package_info.get('travel_status'):
            context_parts.append(f"Estado del viaje: {package_info['travel_status']}")
        
        return "\n".join(context_parts) if context_parts else "Información del paquete limitada."
    
    def _build_conversation_context(self, history: list) -> str:
        """Construye contexto de conversación previa"""
        if not history or len(history) == 0:
            return "Primera interacción del cliente."
        
        # Tomar últimos 3 mensajes para contexto
        recent_history = history[-3:]
        context_parts = []
        
        for msg in recent_history:
            role = "Cliente" if msg.get("role") == "user" else "Agente"
            content = msg.get("content", "")[:150]  # Limitar longitud
            context_parts.append(f"{role}: {content}")
        
        return "\n".join(context_parts)
    
    def _build_escalation_prompt(self, message: str, package_context: str, conversation_context: str) -> str:
        """Construye el prompt para análisis de escalación"""
        
        return f"""Eres un experto analizador de problemas de servicio al cliente en turismo.

Tu tarea es determinar si un problema del cliente REQUIERE INTERVENCIÓN HUMANA de operaciones o si el agente IA puede manejarlo con la información del paquete.

CONTEXTO DEL PAQUETE:
{package_context}

CONVERSACIÓN PREVIA:
{conversation_context}

CRITERIOS PARA ESCALACIÓN (requiere humano):

🔴 CRÍTICO - Escalar INMEDIATAMENTE:
- Emergencias médicas o de seguridad
- Pérdida/robo de documentos (pasaporte, DNI)
- Problemas de vuelo inminentes (sale en pocas horas)
- Servicios contratados que NO llegaron/aparecieron (transfer, guía, hotel)
- Accidentes o situaciones de riesgo

🟠 ALTO - Escalar con prioridad:
- Cambios o cancelaciones de servicios
- Problemas con proveedores (hotel, aerolínea)
- Quejas de calidad de servicio
- Solicitudes de reembolso
- Modificaciones de itinerario

🟡 MEDIO - Puede requerir escalación:
- Dudas complejas que requieren coordinación con proveedores
- Solicitudes especiales no incluidas en el paquete

🔵 BAJO - Agente puede manejar:
- Consultas de información (horarios, direcciones, detalles del paquete)
- Confirmación de servicios incluidos
- Recomendaciones generales
- Preguntas sobre documentación estándar

IMPORTANTE:
- Si el cliente dice "no puedo", "perdí", "no llegó", "problema con" → PROBABLEMENTE requiere escalación
- Si solo pregunta "cuándo", "dónde", "qué incluye" → Agente puede responder
- Considera la URGENCIA temporal (viaje próximo = más crítico)

Responde SOLO en formato JSON con esta estructura:

{{
    "requires_escalation": true/false,
    "urgency_level": "critical|high|medium|low",
    "escalation_reason": "Explicación clara del por qué requiere/no requiere escalación",
    "suggested_category": "emergency|service_failure|complaint|change|flight|hotel|transfer|activity|documentation|information|general",
    "can_agent_help": true/false,
    "recommended_response_tone": "empathetic_urgent|professional_reassuring|informative|standard",
    "key_issues_detected": ["lista", "de", "problemas", "identificados"]
}}

Analiza el mensaje del cliente y determina la acción correcta."""

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
                required_fields = ['requires_escalation', 'urgency_level', 'suggested_category']
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
        # Por seguridad, escalar por defecto
        logger.warning("Using fallback analysis - escalating by default")
        
        return {
            "requires_escalation": True,
            "urgency_level": "high",
            "escalation_reason": "No se pudo analizar el mensaje automáticamente. Escalando por seguridad.",
            "suggested_category": "general",
            "can_agent_help": False,
            "recommended_response_tone": "professional_reassuring",
            "key_issues_detected": ["análisis_fallido"]
        }

# Instancia global del analizador
escalation_analyzer = EscalationAnalyzer()
