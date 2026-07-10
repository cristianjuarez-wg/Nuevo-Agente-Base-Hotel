"""
Servicio para gestionar calificaciones de tickets
"""
from typing import Optional, Dict
from app.core.llm.openai_client import get_async_openai
from app.config import settings
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

class RatingService:
    """Servicio para gestionar calificaciones y validaciones"""
    
    def __init__(self):
        self.client = get_async_openai()
    
    async def user_needs_more_help(self, message: str) -> bool:
        """
        Detecta si el usuario necesita más ayuda o está satisfecho
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            True si necesita más ayuda, False si está satisfecho
        """
        try:
            prompt = f"""Analiza si el usuario necesita más ayuda o está satisfecho con la respuesta recibida.

Mensaje del usuario: "{message}"

Responde SOLO con una palabra: NECESITA_MAS o SATISFECHO

Ejemplos:
- "Gracias, eso es todo" → SATISFECHO
- "Perfecto, no necesito más" → SATISFECHO
- "Ok, gracias" → SATISFECHO
- "Entendido" → SATISFECHO
- "Sí, pero también quiero saber..." → NECESITA_MAS
- "¿Y el hotel?" → NECESITA_MAS
- "Tengo otra duda" → NECESITA_MAS
- "¿Podrías ayudarme con..." → NECESITA_MAS
"""
            
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_FAST,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10
            )
            
            result = response.choices[0].message.content.strip().upper()
            needs_more = "NECESITA_MAS" in result or "NECESITA" in result
            
            logger.info("User help validation",
                       message_preview=message[:50],
                       needs_more_help=needs_more,
                       gpt_response=result)
            
            return needs_more
            
        except Exception as e:
            logger.error("Error validating user needs", error=str(e))
            # Por seguridad, asumir que necesita más ayuda
            return True
    
    async def extract_rating(self, message: str) -> Optional[int]:
        """
        Extrae la calificación del mensaje del usuario
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Rating (1, 2 o 3) o None si no se detectó
        """
        try:
            # Primero intentar detección simple
            message_lower = message.lower().strip()
            
            # Detectar números directos
            if message_lower in ['1', 'uno', 'una estrella', '⭐']:
                return 1
            elif message_lower in ['2', 'dos', 'dos estrellas', '⭐⭐']:
                return 2
            elif message_lower in ['3', 'tres', 'tres estrellas', '⭐⭐⭐']:
                return 3
            
            # Contar estrellas emoji
            star_count = message.count('⭐')
            if 1 <= star_count <= 3:
                return star_count
            
            # Si no es obvio, usar GPT
            prompt = f"""El usuario está calificando un servicio del 1 al 3 (estrellas).

Mensaje: "{message}"

¿Qué calificación dio? Responde SOLO con: 1, 2, 3, o NONE

Ejemplos:
- "3 estrellas" → 3
- "⭐⭐" → 2
- "mal" → 1
- "excelente" → 3
- "muy bien" → 3
- "regular" → 2
- "no quiero calificar" → NONE
- "paso" → NONE
"""
            
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_FAST,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10
            )
            
            result = response.choices[0].message.content.strip()
            
            if result in ['1', '2', '3']:
                rating = int(result)
                logger.info("Rating extracted",
                           message_preview=message[:50],
                           rating=rating,
                           method="gpt")
                return rating
            
            logger.info("No rating detected",
                       message_preview=message[:50],
                       gpt_response=result)
            return None
            
        except Exception as e:
            logger.error("Error extracting rating", error=str(e))
            return None
    
    def get_rating_response(self, rating: int) -> str:
        """
        Genera respuesta según la calificación
        
        Args:
            rating: Calificación (1, 2 o 3)
            
        Returns:
            Mensaje de respuesta
        """
        if rating == 3:
            return "¡Muchas gracias por tu calificación! 🌟 Me alegra haber podido ayudarte. ¿Hay algo más en lo que pueda asistirte?"
        elif rating == 2:
            return "Gracias por tu calificación. Lamento no haber cumplido completamente tus expectativas. ¿Te gustaría dejar alguna sugerencia para mejorar nuestro servicio? (Es opcional)"
        else:  # rating == 1
            return "Gracias por tu calificación. Lamento mucho que la experiencia no haya sido satisfactoria. ¿Podrías compartir qué podríamos mejorar? Tu opinión es muy valiosa para nosotros. (Es opcional)"
    
    async def is_suggestion(self, message: str, previous_rating: int) -> bool:
        """
        Detecta si el mensaje es una sugerencia después de una calificación baja
        
        Args:
            message: Mensaje del usuario
            previous_rating: Calificación previa (debe ser 1 o 2)
            
        Returns:
            True si es una sugerencia, False si es otra cosa
        """
        if previous_rating >= 3:
            return False
        
        try:
            # Detectar si el usuario no quiere dejar sugerencia
            message_lower = message.lower().strip()
            skip_phrases = ['no', 'no gracias', 'paso', 'nada', 'ninguna', 'está bien']
            
            if message_lower in skip_phrases:
                return False
            
            # Si el mensaje es corto y parece una sugerencia, aceptarlo
            if len(message.split()) > 3:
                return True
            
            # Usar GPT para casos ambiguos
            prompt = f"""El usuario acaba de dar una calificación baja ({previous_rating} estrellas) y se le preguntó si quería dejar una sugerencia.

Mensaje: "{message}"

¿Es una sugerencia o está declinando/cambiando de tema?

Responde SOLO: SUGERENCIA o NO_SUGERENCIA

Ejemplos:
- "La información no fue clara" → SUGERENCIA
- "Podrían mejorar los tiempos de respuesta" → SUGERENCIA
- "No, gracias" → NO_SUGERENCIA
- "Tengo otra pregunta sobre el hotel" → NO_SUGERENCIA
"""
            
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_FAST,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20
            )
            
            result = response.choices[0].message.content.strip().upper()
            is_sug = "SUGERENCIA" in result
            
            logger.info("Suggestion detection",
                       message_preview=message[:50],
                       is_suggestion=is_sug)
            
            return is_sug
            
        except Exception as e:
            logger.error("Error detecting suggestion", error=str(e))
            # Por defecto, asumir que es una sugerencia si el rating fue bajo
            return True
