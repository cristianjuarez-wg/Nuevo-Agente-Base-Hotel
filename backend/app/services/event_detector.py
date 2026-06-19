"""
Detector de Eventos Temporales
Identifica eventos como Formula 1, Mundial, Olimpiadas, etc.
"""
from app.core.openai_client import get_async_openai
from app.config import settings
from app.core.logging_config import get_logger
from typing import Dict, Optional
import json

logger = get_logger(__name__)

class EventDetector:
    """
    Detecta eventos temporales en consultas de usuarios
    NO guarda en BD (eventos cambian cada año)
    """
    
    def __init__(self):
        self.openai_client = get_async_openai()
        logger.info("EventDetector initialized")
    
    async def detect_event(self, query: str) -> Optional[Dict]:
        """
        Detecta si la consulta es sobre un evento temporal
        
        Args:
            query: Consulta del usuario
            
        Returns:
            Dict con info del evento o None si no es evento temporal
        """
        try:
            prompt = f"""Analiza la consulta: "{query}"

¿Es sobre un EVENTO TEMPORAL? (eventos que cambian de ubicación/fecha cada año)

Ejemplos de eventos temporales:
- Formula 1, Gran Premio
- Mundial de Fútbol, Copa del Mundo
- Olimpiadas, Juegos Olímpicos
- Carnaval (específico de un año)
- Festivales musicales anuales
- Campeonatos deportivos

NO son eventos temporales:
- Landmarks fijos (Disney, Torre Eiffel, Machu Picchu)
- Ciudades o países
- Regiones geográficas

Si ES un evento temporal, responde con JSON:
{{
  "is_temporal_event": true,
  "event_name": "Formula 1",
  "event_type": "sporting_event|festival|concert|championship",
  "related_countries": ["mónaco", "italia", "españa"],
  "next_edition": "2025",
  "confidence": 0.95
}}

Si NO es evento temporal, responde:
{{"is_temporal_event": false}}"""

            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[
                    {"role": "system", "content": "Eres un experto en eventos internacionales. Respondes solo con JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            
            # Limpiar markdown
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content.strip())
            
            if result.get("is_temporal_event"):
                logger.info("Temporal event detected",
                           event_name=result.get("event_name"),
                           countries=result.get("related_countries"))
                return result
            else:
                logger.debug("Not a temporal event", query=query)
                return None
                
        except Exception as e:
            logger.error("Error detecting temporal event",
                        query=query,
                        error=str(e))
            return None

# Instancia global
event_detector = EventDetector()
