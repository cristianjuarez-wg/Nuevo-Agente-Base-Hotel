"""
Servicio de Mapeo Geográfico Inteligente
Resuelve landmarks, ciudades y regiones usando GPT y auto-aprendizaje
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.geography import GeographicMapping
from app.core.openai_client import get_async_openai
from app.config import settings
from app.core.logging_config import get_logger
from typing import Dict, Optional
import json

logger = get_logger(__name__)

# Conexión a aura_travel.db (donde está geographic_mappings)
engine = create_engine("sqlite:///./aura_travel.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class GeographicMappingService:
    """
    Servicio para resolver términos geográficos con auto-aprendizaje
    Solo para landmarks FIJOS (no eventos temporales)
    """
    
    def __init__(self):
        self.openai_client = get_async_openai()
        self._cache = {}  # Cache en memoria
        logger.info("GeographicMappingService initialized")
    
    async def resolve_term(self, term: str) -> Optional[Dict]:
        """
        Resuelve un término geográfico (landmark, ciudad, región)
        
        Args:
            term: Término a resolver (ej: "disney", "everest", "santorini")
            
        Returns:
            Dict con country, type, confidence o None si no se puede resolver
        """
        try:
            normalized_term = term.lower().strip()
            
            # 1. Buscar en cache
            if normalized_term in self._cache:
                logger.debug("Term found in cache", term=term)
                return self._cache[normalized_term]
            
            # 2. Buscar en base de datos
            db = SessionLocal()
            try:
                mapping = db.query(GeographicMapping).filter_by(
                    normalized_term=normalized_term
                ).first()
                
                if mapping:
                    # Incrementar uso
                    mapping.increment_usage()
                    db.commit()
                    
                    result = {
                        "term": term,
                        "primary_country": mapping.primary_country,
                        "alternative_countries": mapping.alternative_countries or [],
                        "type": mapping.type,
                        "confidence": mapping.confidence,
                        "source": "database"
                    }
                    
                    # Guardar en cache
                    self._cache[normalized_term] = result
                    
                    logger.info("Term resolved from database",
                               term=term,
                               country=mapping.primary_country,
                               usage_count=mapping.usage_count)
                    
                    return result
                
                # 3. No está en BD → Preguntar a GPT
                logger.info("Term not in database, asking GPT", term=term)
                gpt_result = await self._ask_gpt_to_resolve(term)
                
                if gpt_result and gpt_result.get("confidence", 0) >= 0.8:
                    # Guardar en BD para futuro uso
                    self._save_mapping(db, term, gpt_result)
                    
                    # Guardar en cache
                    self._cache[normalized_term] = gpt_result
                    
                    logger.info("Term resolved by GPT and saved",
                               term=term,
                               country=gpt_result.get("primary_country"),
                               confidence=gpt_result.get("confidence"))
                    
                    return gpt_result
                else:
                    logger.warning("GPT could not resolve term with high confidence",
                                  term=term,
                                  confidence=gpt_result.get("confidence") if gpt_result else 0)
                    return None
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error("Error resolving geographic term",
                        term=term,
                        error=str(e))
            return None
    
    async def _ask_gpt_to_resolve(self, term: str) -> Optional[Dict]:
        """
        Pregunta a GPT sobre un término geográfico
        """
        try:
            prompt = f"""Analiza el término geográfico: "{term}"

Determina:
1. ¿Es un landmark, ciudad, región o maravilla natural?
2. ¿En qué país está ubicado principalmente?
3. ¿Hay países alternativos? (si aplica)
4. Nivel de confianza (0-1)

IMPORTANTE: Solo responde para landmarks PERMANENTES (no eventos temporales como Formula 1, Mundial, etc.)

Responde SOLO con JSON válido:
{{
  "term": "{term}",
  "type": "landmark|city|region|natural_wonder",
  "primary_country": "nombre del país",
  "alternative_countries": ["país2", "país3"],
  "confidence": 0.95,
  "reasoning": "breve explicación"
}}

Si no puedes determinar con confianza o es un evento temporal, responde:
{{"confidence": 0.0}}"""

            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[
                    {"role": "system", "content": "Eres un experto en geografía mundial. Respondes solo con JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            
            # Limpiar markdown si existe
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content.strip())
            result["source"] = "gpt"
            
            return result
            
        except Exception as e:
            logger.error("Error asking GPT to resolve term",
                        term=term,
                        error=str(e))
            return None
    
    def _save_mapping(self, db: Session, term: str, gpt_result: Dict):
        """
        Guarda un mapeo en la base de datos
        """
        try:
            normalized_term = term.lower().strip()
            
            mapping = GeographicMapping(
                term=term,
                normalized_term=normalized_term,
                type=gpt_result.get("type", "unknown"),
                primary_country=gpt_result.get("primary_country"),
                alternative_countries=gpt_result.get("alternative_countries"),
                confidence=gpt_result.get("confidence", 0.0),
                is_validated=False,
                validated_by="gpt",
                usage_count=1,
                keywords=None,
                reasoning=gpt_result.get("reasoning"),
                is_permanent=True
            )
            
            db.add(mapping)
            db.commit()
            
            logger.info("Geographic mapping saved",
                       term=term,
                       country=mapping.primary_country)
            
        except Exception as e:
            logger.error("Error saving geographic mapping",
                        term=term,
                        error=str(e))
            db.rollback()
    
    def clear_cache(self):
        """Limpia el cache en memoria"""
        self._cache.clear()
        logger.info("Geographic mapping cache cleared")

# Instancia global
geographic_mapping_service = GeographicMappingService()
