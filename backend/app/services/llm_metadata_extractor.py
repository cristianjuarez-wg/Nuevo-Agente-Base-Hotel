"""
Extractor de metadata usando GPT-4o
Reemplaza toda la lógica dura de análisis de documentos
"""

import json
import structlog
from typing import Dict, Optional
from app.core.openai_client import get_sync_openai
from app.config import settings

logger = structlog.get_logger()


class LLMMetadataExtractor:
    """
    Extractor de metadata usando GPT-4o para análisis inteligente de documentos
    Funciona con cualquier tipo de documento turístico
    """
    
    def __init__(self):
        self.client = get_sync_openai()
        self.model = settings.OPENAI_MODEL  # Modelo principal (alta calidad para metadata RAG)
        logger.info("LLM metadata extractor initialized", model=self.model)
    
    def extract_metadata(self, text: str, filename: str) -> Dict:
        """
        Extrae metadata de cualquier tipo de documento usando GPT-4o
        
        Args:
            text: Texto completo del documento
            filename: Nombre del archivo (ayuda al contexto)
        
        Returns:
            Dict con metadata estructurada
        """
        
        try:
            prompt = self._build_prompt(text, filename)
            
            logger.info("Extracting metadata with LLM",
                       filename=filename,
                       text_length=len(text),
                       model=self.model)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Baja temperatura para respuestas consistentes
                response_format={"type": "json_object"}  # Forzar respuesta JSON
            )
            
            metadata_json = response.choices[0].message.content
            metadata = json.loads(metadata_json)
            
            # Validar y normalizar metadata
            metadata = self._validate_metadata(metadata, filename)
            
            logger.info("Metadata extracted successfully",
                       document_type=metadata.get('document_type'),
                       confidence=metadata.get('confidence'),
                       countries=metadata.get('countries'),
                       cities=metadata.get('cities'))
            
            return metadata
            
        except Exception as e:
            logger.error("Error extracting metadata with LLM",
                        error=str(e),
                        filename=filename)
            # Fallback a metadata mínima
            return self._fallback_metadata(filename)
    
    def _get_system_prompt(self) -> str:
        """Prompt del sistema que define el rol del LLM"""
        return """Eres un experto en análisis de documentos turísticos con años de experiencia en la industria de viajes.

Tu tarea es analizar documentos y extraer metadata precisa y estructurada.

REGLAS CRÍTICAS sobre países:
- Incluye SOLO los países que son DESTINOS TURÍSTICOS reales donde el viajero pasa tiempo significativo
- NO incluyas países que son solo:
  * Puntos de tránsito o escalas
  * Aeropuertos de conexión
  * Pre-viaje (1 noche antes del viaje principal)
  * Lugares mencionados solo como punto de partida
  * Países mencionados solo en contexto de "salida desde", "vuelo desde", "conexión en"

EJEMPLOS:
- ✅ INCLUIR: "3 noches en París" → Francia es destino
- ❌ NO INCLUIR: "1 noche en Buenos Aires (pre-viaje)" → Argentina NO es destino
- ❌ NO INCLUIR: "Vuelo desde Buenos Aires" → Argentina NO es destino
- ❌ NO INCLUIR: "Escala en Madrid" → España NO es destino (si solo es escala)

Sé preciso, consistente y estructurado en tus respuestas."""
    
    def _build_prompt(self, text: str, filename: str) -> str:
        """Construye el prompt para GPT-4o"""
        
        return f"""Analiza el siguiente documento turístico y extrae la metadata necesaria.

NOMBRE DEL ARCHIVO: {filename}

TEXTO DEL DOCUMENTO:
{text}

Extrae la siguiente información en formato JSON:

{{
    "document_type": "package|policy|faq|payment|other",
    "confidence": 0.0-1.0,
    
    // Para PAQUETES TURÍSTICOS:
    "package_name": "nombre del paquete" o null,
    "countries": ["país1", "país2"],  // SOLO destinos reales (NO tránsito/pre-viaje) - en minúsculas
    "cities": ["ciudad1", "ciudad2"],  // Ciudades principales visitadas - en minúsculas
    "landmarks": ["landmark1", "landmark2"],  // Lugares icónicos mencionados - en minúsculas
    "duration_days": número o null,
    "includes_flights": true/false/null,
    "meal_plan": "all_inclusive|half_board|breakfast|none" o null,
    "price_from": número o null,
    "package_category": "cultural|adventure|beach|luxury|family|romantic" o null,
    "target_audience": ["couples", "families", "solo"] o null,
    
    // Para POLÍTICAS:
    "policy_type": "cancellation|payment|travel|baggage|other" o null,
    "applies_to": ["tipo de paquete"] o null,
    
    // Para FAQs:
    "faq_categories": ["categoría1", "categoría2"] o null,
    
    // Para PAGOS:
    "payment_methods": ["método1", "método2"] o null,
    "installments_available": true/false/null,
    
    // GENERAL (para todos los tipos):
    "language": "es|en|pt",
    "keywords": ["keyword1", "keyword2", "keyword3"],  // 5-10 keywords relevantes
    "summary": "resumen breve del documento en 1-2 líneas"
}}

IMPORTANTE:
- Para "countries", incluye SOLO los países que son DESTINOS TURÍSTICOS reales
- NO incluyas países de tránsito, escalas, aeropuertos o pre-viaje
- Si un país tiene solo 1 noche y se menciona como "pre-viaje" o "conexión", NO lo incluyas
- Todos los nombres geográficos (países, ciudades, landmarks) deben estar en MINÚSCULAS
- Sé preciso con el tipo de documento
- Si no puedes determinar algo, usa null
- Para arrays vacíos, usa []

Responde SOLO con el JSON, sin texto adicional."""
    
    def _validate_metadata(self, metadata: Dict, filename: str) -> Dict:
        """Valida y normaliza metadata extraída"""
        
        # Asegurar campos requeridos
        metadata.setdefault('document_type', 'other')
        metadata.setdefault('confidence', 0.5)
        metadata.setdefault('countries', [])
        metadata.setdefault('cities', [])
        metadata.setdefault('landmarks', [])
        metadata.setdefault('keywords', [])
        metadata.setdefault('language', 'es')
        
        # Normalizar listas a lowercase
        if isinstance(metadata.get('countries'), list):
            metadata['countries'] = [c.lower().strip() for c in metadata['countries'] if c]
        
        if isinstance(metadata.get('cities'), list):
            metadata['cities'] = [c.lower().strip() for c in metadata['cities'] if c]
        
        if isinstance(metadata.get('landmarks'), list):
            metadata['landmarks'] = [l.lower().strip() for l in metadata['landmarks'] if l]
        
        if isinstance(metadata.get('keywords'), list):
            metadata['keywords'] = [k.lower().strip() for k in metadata['keywords'] if k]
        
        # Generar package_id si es paquete
        if metadata['document_type'] == 'package':
            if not metadata.get('package_name'):
                # Usar filename como fallback
                metadata['package_name'] = filename.replace('.pdf', '').replace('.PDF', '')
            
            # Generar package_id único
            package_id = metadata['package_name'].lower().replace(' ', '_').replace('-', '_')
            # Limpiar caracteres especiales
            package_id = ''.join(c if c.isalnum() or c == '_' else '_' for c in package_id)
            metadata['package_id'] = package_id
            
            # Detectar si es multi-país
            if len(metadata.get('countries', [])) > 1:
                metadata['package_type'] = 'multi-country'
            elif len(metadata.get('countries', [])) == 1:
                metadata['package_type'] = 'single-country'
            else:
                metadata['package_type'] = 'unknown'
        
        # Validar confidence
        if not isinstance(metadata.get('confidence'), (int, float)):
            metadata['confidence'] = 0.5
        else:
            metadata['confidence'] = max(0.0, min(1.0, float(metadata['confidence'])))
        
        logger.debug("Metadata validated",
                    document_type=metadata['document_type'],
                    countries_count=len(metadata.get('countries', [])),
                    cities_count=len(metadata.get('cities', [])))
        
        return metadata
    
    def _fallback_metadata(self, filename: str) -> Dict:
        """Metadata mínima si LLM falla"""
        
        logger.warning("Using fallback metadata", filename=filename)
        
        return {
            'document_type': 'other',
            'confidence': 0.0,
            'countries': [],
            'cities': [],
            'landmarks': [],
            'keywords': [],
            'language': 'es',
            'summary': f'Documento: {filename}',
            'package_name': filename.replace('.pdf', '').replace('.PDF', ''),
            'package_id': filename.replace('.pdf', '').replace('.PDF', '').lower().replace(' ', '_')
        }


# Instancia global
llm_extractor = LLMMetadataExtractor()
