"""
Servicio de Enriquecimiento Semántico de Queries
Interpreta queries del usuario usando GPT sin necesidad de hardcodear keywords
"""

from app.core.openai_client import get_async_openai
from typing import Dict, List, Optional
import json
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class SemanticQueryEnhancer:
    """
    Interpreta queries del usuario y los enriquece semánticamente
    SIN necesidad de hardcodear keywords infinitas
    
    Ejemplos:
    - "quiero conocer delfines" → detecta temas, actividades, tipo de destino
    - "montañas más altas" → detecta características geográficas
    - "lugares románticos" → detecta tipo de experiencia
    """
    
    def __init__(self):
        self.client = get_async_openai()
        logger.info("Semantic query enhancer initialized")
    
    async def interpret_query(self, query: str) -> Dict:
        """
        Usa GPT para interpretar la intención del usuario
        
        Args:
            query: Consulta del usuario
            
        Returns:
            Dict con temas, actividades, tipo_destino, características, keywords
        """
        
        prompt = f"""Analiza esta consulta de viaje y extrae información semántica para mejorar la búsqueda.

CONSULTA DEL USUARIO: "{query}"

Extrae:
1. TEMAS principales (naturaleza, cultura, aventura, relax, romance, gastronomía, etc.)
2. ACTIVIDADES implícitas (buceo, trekking, safari, snorkel, ski, etc.)
3. TIPO DE DESTINO (playa, montaña, ciudad, parque temático, isla, desierto, etc.)
4. CARACTERÍSTICAS específicas (vida marina, altitud, monumentos, fauna, etc.)
5. KEYWORDS de expansión (palabras relacionadas para mejorar búsqueda vectorial)
6. LANDMARKS detectados (si menciona Disney, Everest, Torre Eiffel, etc.)

Responde SOLO en JSON válido:
{{
  "temas": ["tema1", "tema2"],
  "actividades": ["actividad1", "actividad2"],
  "tipo_destino": "tipo",
  "caracteristicas": ["caracteristica1", "caracteristica2"],
  "keywords_expansion": ["keyword1", "keyword2", "keyword3", "keyword4"],
  "landmarks_detectados": ["landmark1"],
  "confianza": 0.0-1.0
}}

EJEMPLOS:

Ejemplo 1:
Consulta: "quiero conocer delfines"
Respuesta:
{{
  "temas": ["vida marina", "naturaleza", "animales"],
  "actividades": ["snorkel", "buceo", "avistamiento de fauna"],
  "tipo_destino": "costero",
  "caracteristicas": ["fauna oceánica", "biodiversidad marina", "ecosistemas acuáticos"],
  "keywords_expansion": ["océano", "vida submarina", "costa", "mar", "fauna marina", "cetáceos"],
  "landmarks_detectados": [],
  "confianza": 0.9
}}

Ejemplo 2:
Consulta: "las montañas más altas del mundo"
Respuesta:
{{
  "temas": ["aventura", "naturaleza", "montañismo"],
  "actividades": ["trekking", "montañismo", "alpinismo"],
  "tipo_destino": "montaña",
  "caracteristicas": ["alta montaña", "himalayas", "picos elevados", "altitud extrema"],
  "keywords_expansion": ["nepal", "tibet", "everest", "altitud", "cumbres", "himalayas"],
  "landmarks_detectados": ["everest", "himalayas"],
  "confianza": 0.95
}}

Ejemplo 3:
Consulta: "lugares románticos para luna de miel"
Respuesta:
{{
  "temas": ["romance", "relax", "lujo"],
  "actividades": ["relax", "cenas románticas", "spa"],
  "tipo_destino": "romantico",
  "caracteristicas": ["privacidad", "lujo", "paisajes hermosos", "ambiente íntimo"],
  "keywords_expansion": ["parejas", "luna de miel", "resort", "romantico", "exclusivo", "playa privada"],
  "landmarks_detectados": [],
  "confianza": 0.85
}}

Ahora analiza la consulta del usuario y responde en JSON.
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Baja para consistencia
                response_format={"type": "json_object"},
                timeout=15
            )
            
            interpretation = json.loads(response.choices[0].message.content)
            
            # Validar estructura
            if not isinstance(interpretation, dict):
                raise ValueError("Invalid interpretation format")
            
            # Valores por defecto si faltan
            interpretation.setdefault('temas', [])
            interpretation.setdefault('actividades', [])
            interpretation.setdefault('tipo_destino', 'general')
            interpretation.setdefault('caracteristicas', [])
            interpretation.setdefault('keywords_expansion', [])
            interpretation.setdefault('landmarks_detectados', [])
            interpretation.setdefault('confianza', 0.5)
            
            logger.info("Query interpreted successfully",
                       original_query=query[:50],
                       temas=interpretation.get('temas'),
                       tipo_destino=interpretation.get('tipo_destino'),
                       confianza=interpretation.get('confianza'))
            
            return interpretation
            
        except Exception as e:
            logger.error("Error interpreting query", 
                        query=query[:50],
                        error=str(e))
            # Retornar estructura vacía en caso de error
            return {
                "temas": [],
                "actividades": [],
                "tipo_destino": "general",
                "caracteristicas": [],
                "keywords_expansion": [],
                "landmarks_detectados": [],
                "confianza": 0.0
            }
    
    def build_enriched_query(self, original_query: str, interpretation: Dict) -> str:
        """
        Construye query enriquecido basado en la interpretación semántica
        
        Args:
            original_query: Query original del usuario
            interpretation: Resultado de interpret_query()
            
        Returns:
            Query enriquecido con información semántica
        """
        enriched_parts = [original_query]
        
        # Agregar temas
        if interpretation.get('temas'):
            temas_str = ", ".join(interpretation['temas'])
            enriched_parts.append(f"temas: {temas_str}")
        
        # Agregar actividades
        if interpretation.get('actividades'):
            actividades_str = ", ".join(interpretation['actividades'])
            enriched_parts.append(f"actividades: {actividades_str}")
        
        # Agregar características
        if interpretation.get('caracteristicas'):
            caracteristicas_str = ", ".join(interpretation['caracteristicas'])
            enriched_parts.append(f"características: {caracteristicas_str}")
        
        # Agregar keywords de expansión
        if interpretation.get('keywords_expansion'):
            keywords_str = " ".join(interpretation['keywords_expansion'])
            enriched_parts.append(keywords_str)
        
        # Agregar landmarks detectados
        if interpretation.get('landmarks_detectados'):
            landmarks_str = ", ".join(interpretation['landmarks_detectados'])
            enriched_parts.append(f"landmarks: {landmarks_str}")
        
        enriched_query = " | ".join(enriched_parts)
        
        logger.debug("Query enriched semantically",
                    original=original_query[:50],
                    enriched_length=len(enriched_query),
                    added_parts=len(enriched_parts) - 1)
        
        return enriched_query
    
    async def verify_relevance(self, query: str, destination_context: str, 
                               destination_name: str) -> Dict:
        """
        Verifica si un destino es relevante para la consulta del usuario
        
        Args:
            query: Consulta original del usuario
            destination_context: Texto del documento del destino
            destination_name: Nombre del destino
            
        Returns:
            Dict con score de relevancia y razón
        """
        
        # Limitar contexto a primeros 800 caracteres para no gastar muchos tokens
        truncated_context = destination_context[:800]
        
        prompt = f"""Evalúa si este destino turístico cumple con lo que busca el usuario.

CONSULTA DEL USUARIO: "{query}"

DESTINO: {destination_name}

INFORMACIÓN DEL DESTINO:
{truncated_context}

¿Este destino es relevante para la consulta del usuario?

Responde SOLO en JSON válido:
{{
  "es_relevante": true/false,
  "score": 0.0-1.0,
  "razon": "explicación breve en una oración"
}}

CRITERIOS DE PUNTUACIÓN:
- 0.0-0.2 = Nada relevante (no tiene relación)
- 0.3-0.5 = Parcialmente relevante (menciona temas relacionados pero no cumple lo específico)
- 0.6-0.8 = Relevante (cumple algunos requisitos importantes)
- 0.9-1.0 = Muy relevante (cumple exactamente lo que busca el usuario)

EJEMPLOS:

Ejemplo 1:
Usuario busca: "conocer delfines"
Destino: "Tailandia - Templos y Playas" con snorkel en islas
Respuesta: {{"es_relevante": true, "score": 0.8, "razon": "Tailandia tiene playas con actividades de snorkel donde se puede ver vida marina"}}

Ejemplo 2:
Usuario busca: "conocer delfines"
Destino: "Japón Tradicional" enfocado en cultura y templos
Respuesta: {{"es_relevante": false, "score": 0.2, "razon": "Japón tradicional se enfoca en cultura y templos, no en actividades marinas"}}

Ahora evalúa el destino.
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=10
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Validar resultado
            score = float(result.get('score', 0.5))
            score = max(0.0, min(1.0, score))  # Clamp entre 0 y 1
            
            result['score'] = score
            result.setdefault('es_relevante', score >= 0.5)
            result.setdefault('razon', 'No disponible')
            
            logger.debug("Relevance verified",
                        destination=destination_name[:30],
                        score=score,
                        es_relevante=result['es_relevante'])
            
            return result
            
        except Exception as e:
            logger.error("Error verifying relevance", 
                        destination=destination_name[:30],
                        error=str(e))
            # Score neutral por defecto en caso de error
            return {
                "es_relevante": True,  # Por defecto asumir relevante
                "score": 0.5,
                "razon": "Error al verificar relevancia"
            }


# Instancia global del servicio
semantic_enhancer = SemanticQueryEnhancer()
