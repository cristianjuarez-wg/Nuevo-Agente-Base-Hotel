"""
Clasificador de Severidad de Problemas
Determina si un problema requiere escalación o puede auto-resolverse
"""
from typing import Dict
from app.core.llm.openai_client import get_async_openai
from app.config import settings
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


class SeverityClassifier:
    """Clasifica la severidad de problemas reportados por usuarios"""
    
    def __init__(self):
        self.client = get_async_openai()
    
    async def classify_severity(self, message: str, category: str, package_info: Dict = None, conversation_history: list = None) -> Dict:
        """
        Clasifica la severidad de un problema
        
        Args:
            message: Mensaje del usuario
            category: Categoría detectada (hotel, flight, transfer, etc)
            package_info: Información del paquete para contexto
            conversation_history: Historial de conversación para contexto completo
            
        Returns:
            Dict con severity, requires_escalation, suggested_action, reasoning
        """
        
        # Construir contexto del paquete
        context_str = ""
        if package_info:
            context_str = f"""
Contexto del viaje:
- Destino: {package_info.get('destination', 'N/A')}
- Fecha de salida: {package_info.get('departure_date', 'N/A')}
- Estado del viaje: {package_info.get('travel_status', 'N/A')}
"""
        
        # Construir contexto de conversación
        conversation_context = ""
        if conversation_history and len(conversation_history) > 0:
            # Tomar últimos 5 mensajes para contexto
            recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
            conversation_lines = []
            for msg in recent_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if role == "user":
                    conversation_lines.append(f"Usuario: {content}")
                elif role == "assistant":
                    conversation_lines.append(f"Asistente: {content}")
            
            if conversation_lines:
                conversation_context = f"""
Historial de conversación reciente:
{chr(10).join(conversation_lines)}
"""
        
        prompt = f"""Eres un experto en atención al cliente de turismo. Analiza el siguiente mensaje y clasifica la severidad del problema.

CATEGORÍAS DE SEVERIDAD:

1. INFORMATIONAL (no requiere acción, solo información):
   - Preguntas sobre horarios (check-in, check-out, salida de vuelo)
   - Solicitud de voucher, confirmación, documentos
   - Consultas sobre servicios incluidos
   - Preguntas sobre ubicación, dirección, contacto
   - Información general del paquete
   
2. MINOR (problema menor, puede resolverse con proveedor directamente):
   - Problemas menores de habitación (toalla faltante, control remoto)
   - Solicitudes de servicio (room service, late checkout)
   - Preferencias (piso alto, vista específica)
   - Consultas sobre amenities
   - Problemas de confort no críticos
   
3. MODERATE (requiere seguimiento, posible escalación):
   - Problemas de calidad del servicio
   - Quejas sobre limpieza o mantenimiento
   - Solicitudes de cambio de habitación
   - Problemas con reservas de actividades
   - Retrasos o cambios menores
   
4. MAJOR (requiere escalación urgente a operador):
   - No hay habitación/servicio disponible (overbooking)
   - Problemas de seguridad o higiene graves
   - Cobros incorrectos o fraude
   - Cancelación o cambio de reserva
   - Emergencias (accidente, robo, pérdida de documentos)
   - Servicios no entregados (transfer no llegó, hotel cerrado)
   - Problemas que afectan el viaje inmediatamente

MENSAJE DEL USUARIO:
"{message}"

CATEGORÍA DETECTADA: {category}
{context_str}
{conversation_context}

INSTRUCCIONES IMPORTANTES:
1. **CONSIDERA EL HISTORIAL:** Si en mensajes anteriores el usuario ya dio contexto (ej: "problema con transfer" y luego "no llegó"), NO pidas clarificación. Usa el contexto acumulado.

2. **SOLO pide clarificación si:**
   - Es el PRIMER mensaje y es muy vago (ej: "tengo un problema")
   - No hay suficiente información en TODO el historial

3. **Clasifica según severidad:**
   - INFORMATIONAL: Preguntas simples de información
   - MINOR: Problemas menores que el proveedor puede resolver
   - MODERATE: Requiere seguimiento pero no es urgente
   - MAJOR: Crítico o urgente (servicios no entregados, emergencias)

4. **Ejemplos de MAJOR con contexto:**
   - Usuario dice "problema con transfer" → luego "no llegó" = MAJOR (servicio no entregado)
   - Usuario dice "problema con hotel" → luego "no tienen mi reserva" = MAJOR (overbooking)

Responde SOLO en formato JSON:
{{
  "severity": "needs_clarification|informational|minor|moderate|major",
  "requires_escalation": true/false,
  "suggested_action": "ask_details|provide_info|contact_provider|escalate_moderate|escalate_urgent",
  "reasoning": "explicación breve de por qué clasificaste así",
  "clarification_questions": ["pregunta1", "pregunta2"] // solo si needs_clarification
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,  # Clasificación estructurada: mini es suficiente y ~30x más barato
                messages=[
                    {"role": "system", "content": "Eres un clasificador experto de severidad de problemas en turismo. Respondes SOLO en JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Baja temperatura para clasificación consistente
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Limpiar markdown si viene con ```json
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            import json
            result = json.loads(result_text)
            
            logger.info("Severity classified",
                       severity=result.get("severity"),
                       requires_escalation=result.get("requires_escalation"),
                       suggested_action=result.get("suggested_action"),
                       message_preview=message[:50])
            
            return result
            
        except Exception as e:
            logger.error("Error classifying severity",
                        error=str(e),
                        message_preview=message[:50])
            
            # Fallback seguro: escalar por defecto
            return {
                "severity": "major",
                "requires_escalation": True,
                "suggested_action": "escalate_urgent",
                "reasoning": "Error en clasificación - escalando por seguridad",
                "clarification_questions": []
            }
    
    def generate_clarification_response(self, category: str, questions: list = None) -> str:
        """
        Genera respuesta pidiendo más detalles
        
        Args:
            category: Categoría del problema (hotel, flight, etc)
            questions: Lista de preguntas sugeridas por GPT
            
        Returns:
            Mensaje de respuesta
        """
        category_emojis = {
            "hotel": "🏨",
            "flight": "✈️",
            "transfer": "🚗",
            "activity": "🎯",
            "documentation": "📄"
        }
        
        emoji = category_emojis.get(category, "💬")
        
        if questions and len(questions) > 0:
            questions_text = "\n".join([f"• {q}" for q in questions[:3]])
            return f"{emoji} Entiendo que tienes una consulta. Para ayudarte mejor, ¿podrías darme más detalles?\n\n{questions_text}"
        
        # Preguntas por defecto según categoría
        default_questions = {
            "hotel": [
                "¿Es sobre el check-in/check-out?",
                "¿Hay un problema con la habitación?",
                "¿Necesitas información sobre servicios del hotel?"
            ],
            "flight": [
                "¿Es sobre el horario del vuelo?",
                "¿Necesitas información de check-in?",
                "¿Hay algún problema con tu reserva de vuelo?"
            ],
            "transfer": [
                "¿Es sobre el horario de recogida?",
                "¿Necesitas el contacto del conductor?",
                "¿Hay algún problema con el traslado?"
            ],
            "activity": [
                "¿Es sobre el horario de la actividad?",
                "¿Necesitas el punto de encuentro?",
                "¿Hay algún problema con la excursión?"
            ]
        }
        
        questions_list = default_questions.get(category, [
            "¿Podrías darme más detalles sobre tu consulta?",
            "¿Es algo urgente?",
            "¿Qué tipo de ayuda necesitas?"
        ])
        
        questions_text = "\n".join([f"• {q}" for q in questions_list])
        return f"{emoji} Entiendo que tienes una consulta. Para ayudarte mejor, ¿podrías contarme:\n\n{questions_text}"


# Instancia global
severity_classifier = SeverityClassifier()
