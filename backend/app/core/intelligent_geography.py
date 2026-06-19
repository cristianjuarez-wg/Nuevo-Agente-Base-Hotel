"""
Extractor inteligente de geografía con jerarquía completa
Detecta países, regiones, ciudades y landmarks de forma multi-nivel
"""

import json
import re
from typing import List, Dict, Set, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger()


class IntelligentGeographyExtractor:
    """
    Extractor inteligente que usa jerarquía geográfica completa
    """
    
    def __init__(self):
        self.data = self._load_geography_data()
        self._build_indices()
        logger.info("Intelligent geography extractor initialized",
                   cities_count=len(self.city_to_country),
                   landmarks_count=len(self.landmark_to_country),
                   special_regions_count=len(self.special_regions))
    
    def _load_geography_data(self) -> Dict:
        """Carga datos geográficos completos"""
        try:
            # Ruta base: backend/data/
            # __file__ = backend/app/core/intelligent_geography.py
            # parent = backend/app/core/
            # parent.parent = backend/app/
            # parent.parent.parent = backend/
            base_path = Path(__file__).parent.parent.parent / "data"
            
            # Intentar cargar geography_complete.json primero
            complete_path = base_path / "geography_complete.json"
            if complete_path.exists():
                with open(complete_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            # Fallback a geography.json
            fallback_path = base_path / "geography.json"
            if fallback_path.exists():
                with open(fallback_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            logger.error("Geography data files not found",
                        complete_path=str(complete_path),
                        fallback_path=str(fallback_path))
            return {}
                
        except Exception as e:
            logger.error("Error loading geography data", error=str(e))
            return {}
    
    def _build_indices(self):
        """Construir índices para búsqueda rápida"""
        # Índices directos (originales)
        self.city_to_country = self.data.get('city_to_country', {})
        self.landmark_to_country = self.data.get('landmark_to_country', {})
        self.special_regions = self.data.get('special_regions', {})
        
        # 🆕 ÍNDICES PRE-NORMALIZADOS (solución híbrida)
        # Clave normalizada → (valor original, país)
        self.city_to_country_norm = {}
        for city, country in self.city_to_country.items():
            norm_city = self._normalize(city)
            self.city_to_country_norm[norm_city] = (city, country)
        
        self.landmark_to_country_norm = {}
        for landmark, country in self.landmark_to_country.items():
            norm_landmark = self._normalize(landmark)
            self.landmark_to_country_norm[norm_landmark] = (landmark, country)
        
        # Índice: país → continente/región
        self.country_info = {}
        for continent, cont_data in self.data.get('continents', {}).items():
            for region, reg_data in cont_data.get('regions', {}).items():
                for country in reg_data.get('countries', []):
                    self.country_info[country] = {
                        'continent': continent,
                        'region': region
                    }
        
        # Índice: región → países
        self.region_to_countries = {}
        for continent, cont_data in self.data.get('continents', {}).items():
            for region, reg_data in cont_data.get('regions', {}).items():
                self.region_to_countries[region] = reg_data.get('countries', [])
    
    def _normalize(self, text: str) -> str:
        """Normaliza texto para comparación"""
        if not text:
            return ""
        text = text.lower().strip()
        # Remover acentos comunes
        replacements = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'ñ': 'n', 'ü': 'u'
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    def extract_all_geographic_entities(self, text: str, filename: str = "") -> Dict:
        """
        Extrae todas las entidades geográficas del texto
        Retorna dict con países, ciudades, landmarks, etc.
        """
        result = {
            'countries': set(),
            'cities': set(),
            'landmarks': set(),
            'special_regions': set(),
            'confidence': {}
        }
        
        # NIVEL 1: Países explícitos en filename
        if filename:
            countries = self._detect_countries_in_text(filename)
            for country in countries:
                result['countries'].add(country)
                result['confidence'][country] = 'filename'
        
        # NIVEL 2: Países explícitos en texto
        countries = self._detect_countries_in_text(text)
        for country in countries:
            result['countries'].add(country)
            if country not in result['confidence']:
                result['confidence'][country] = 'explicit'
        
        # NIVEL 3: Regiones especiales → Países
        regions = self._detect_special_regions(text, filename)
        for region, region_data in regions.items():
            result['special_regions'].add(region)
            # Agregar país principal
            primary = region_data.get('primary_country')
            if primary:
                result['countries'].add(primary)
                if primary not in result['confidence']:
                    result['confidence'][primary] = f'region:{region}'
            
            # Agregar países adicionales si se mencionan explícitamente
            also_includes = region_data.get('also_includes', [])
            for country in also_includes:
                if self._normalize(country) in self._normalize(text):
                    result['countries'].add(country)
                    if country not in result['confidence']:
                        result['confidence'][country] = f'region:{region}:explicit'
        
        # NIVEL 4: Ciudades → País (usando índice pre-normalizado)
        cities = self._detect_cities(text)
        for city in cities:
            result['cities'].add(city)
            # 🆕 Buscar en índice pre-normalizado
            norm_city = self._normalize(city)
            if norm_city in self.city_to_country_norm:
                _, country = self.city_to_country_norm[norm_city]
                result['countries'].add(country)
                if country not in result['confidence']:
                    result['confidence'][country] = f'city:{city}'
        
        # NIVEL 5: Landmarks → País (usando índice pre-normalizado)
        landmarks = self._detect_landmarks(text)
        for landmark in landmarks:
            result['landmarks'].add(landmark)
            # 🆕 Buscar en índice pre-normalizado
            norm_landmark = self._normalize(landmark)
            if norm_landmark in self.landmark_to_country_norm:
                _, country = self.landmark_to_country_norm[norm_landmark]
                result['countries'].add(country)
                if country not in result['confidence']:
                    result['confidence'][country] = f'landmark:{landmark}'
        
        # NIVEL 6: Análisis de itinerario
        itinerary_data = self._parse_itinerary(text)
        result['countries'].update(itinerary_data['countries'])
        result['cities'].update(itinerary_data['cities'])
        
        # Convertir sets a listas
        return {
            'countries': sorted(list(result['countries'])),
            'cities': sorted(list(result['cities'])),
            'landmarks': sorted(list(result['landmarks'])),
            'special_regions': sorted(list(result['special_regions'])),
            'confidence': result['confidence']
        }
    
    def _detect_countries_in_text(self, text: str) -> List[str]:
        """Detecta países mencionados explícitamente"""
        if not text:
            return []
        
        norm_text = self._normalize(text)
        detected = []
        
        # Buscar en todos los países conocidos
        for country in self.country_info.keys():
            if self._normalize(country) in norm_text:
                detected.append(country)
        
        return detected
    
    def _detect_special_regions(self, text: str, filename: str = "") -> Dict:
        """Detecta regiones especiales (Laponia, Patagonia, etc.)"""
        detected = {}
        combined_text = self._normalize(f"{filename} {text}")
        
        for region, region_data in self.special_regions.items():
            # Buscar nombre de la región
            if region in combined_text:
                detected[region] = region_data
                continue
            
            # Buscar keywords de la región
            keywords = region_data.get('keywords', [])
            if any(kw.lower() in combined_text for kw in keywords):
                detected[region] = region_data
                continue
            
            # Buscar ciudades de la región
            cities = region_data.get('cities', [])
            if any(city.lower() in combined_text for city in cities):
                detected[region] = region_data
        
        return detected
    
    def _detect_cities(self, text: str) -> List[str]:
        """Detecta ciudades mencionadas (usando índice pre-normalizado)"""
        if not text:
            return []
        
        norm_text = self._normalize(text)
        detected = []
        
        # 🆕 Buscar en índice pre-normalizado (más eficiente)
        for norm_city, (original_city, _) in self.city_to_country_norm.items():
            if norm_city in norm_text:
                detected.append(original_city)
        
        return detected
    
    def _detect_landmarks(self, text: str) -> List[str]:
        """Detecta landmarks mencionados (usando índice pre-normalizado)"""
        if not text:
            return []
        
        norm_text = self._normalize(text)
        detected = []
        
        # 🆕 Buscar en índice pre-normalizado (más eficiente)
        for norm_landmark, (original_landmark, _) in self.landmark_to_country_norm.items():
            if norm_landmark in norm_text:
                detected.append(original_landmark)
        
        return detected
    
    def _parse_itinerary(self, text: str) -> Dict:
        """
        Analiza estructura de itinerario para detectar países y ciudades
        Busca patrones como "Día X: Ciudad" o "Día X-Y: País"
        """
        result = {
            'countries': set(),
            'cities': set()
        }
        
        if not text:
            return result
        
        # Patrones de itinerario
        patterns = [
            r'día\s+\d+[:\-\|]\s*([^\n,]+)',  # Día 1: Ciudad
            r'day\s+\d+[:\-\|]\s*([^\n,]+)',  # Day 1: City
            r'día\s+\d+\s*[-a-z\s]*:\s*([^\n,]+)',  # Día 1-3: Ciudad
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text.lower(), re.IGNORECASE)
            for location in matches:
                location = location.strip()
                
                # Intentar detectar ciudad
                cities = self._detect_cities(location)
                for city in cities:
                    result['cities'].add(city)
                    country = self.city_to_country.get(self._normalize(city))
                    if country:
                        result['countries'].add(country)
                
                # Intentar detectar país
                countries = self._detect_countries_in_text(location)
                result['countries'].update(countries)
        
        return result
    
    def get_country_info(self, country: str) -> Optional[Dict]:
        """Obtiene información de un país"""
        norm_country = self._normalize(country)
        for c, info in self.country_info.items():
            if self._normalize(c) == norm_country:
                return {
                    'country': c,
                    'continent': info['continent'],
                    'region': info['region']
                }
        return None
    
    def enrich_query(self, query: str) -> str:
        """
        Enriquece la consulta con información geográfica para búsqueda semántica
        Compatible con lógica anterior pero usando nueva jerarquía completa
        
        Ejemplos:
        - "Europa" → "Europa | Países de europa: españa, francia, italia..."
        - "río Nilo" → "río Nilo | río nilo está en egipto"
        - "París" → "París | parís está en francia"
        - "Laponia" → "Laponia | Países de laponia: finlandia, suecia, noruega"
        """
        enriched_parts = [query]
        
        try:
            norm_query = self._normalize(query)
            
            # Extraer todas las entidades geográficas
            geo_data = self.extract_all_geographic_entities(query, "")
            
            # 0. CONTINENTES → Países (NUEVO)
            # Detectar si menciona un continente
            continent_detected = None
            for continent_name, continent_data in self.data.get('continents', {}).items():
                norm_continent = self._normalize(continent_name)
                # Verificar nombre del continente
                if norm_continent in norm_query:
                    continent_detected = continent_name
                    break
                # Verificar aliases
                for alias in continent_data.get('aliases', []):
                    if self._normalize(alias) in norm_query:
                        continent_detected = continent_name
                        break
                if continent_detected:
                    break
            
            # Si detectó continente, agregar países
            if continent_detected and not geo_data.get('countries'):
                all_countries = []
                continent_data = self.data['continents'][continent_detected]
                for region_data in continent_data.get('regions', {}).values():
                    all_countries.extend(region_data.get('countries', []))
                
                if all_countries:
                    # Limitar a 10 países para no sobrecargar
                    enriched_parts.append(
                        f"Países de {continent_detected}: {', '.join(all_countries[:10])}"
                    )
            
            # 1. REGIONES ESPECIALES → Países
            if geo_data.get('special_regions'):
                for region in geo_data['special_regions']:
                    region_data = self.special_regions.get(region)
                    if region_data:
                        primary = region_data.get('primary_country')
                        also = region_data.get('also_includes', [])
                        all_countries = [primary] + also if primary else also
                        if all_countries:
                            enriched_parts.append(f"Países de {region}: {', '.join(all_countries)}")
            
            # 2. LANDMARKS → País
            if geo_data.get('landmarks'):
                for landmark in geo_data['landmarks']:
                    country = self.landmark_to_country.get(landmark)
                    if country:
                        enriched_parts.append(f"{landmark} está en {country}")
            
            # 3. CIUDADES → País
            if geo_data.get('cities'):
                for city in geo_data['cities']:
                    country = self.city_to_country.get(city)
                    if country:
                        enriched_parts.append(f"{city} está en {country}")
            
            # 4. PAÍSES → Ciudades principales (máximo 3)
            if geo_data.get('countries'):
                for country in geo_data['countries']:
                    # Buscar ciudades de ese país
                    country_cities = [
                        city for city, c in self.city_to_country.items() 
                        if c == country
                    ]
                    if country_cities[:3]:
                        enriched_parts.append(
                            f"Ciudades de {country}: {', '.join(country_cities[:3])}"
                        )
            
            enriched_query = " | ".join(enriched_parts)
            
            # Log solo si se enriqueció
            if len(enriched_parts) > 1:
                logger.debug("Query enriched",
                           original=query,
                           enriched=enriched_query,
                           entities_found={
                               'continent': continent_detected,
                               'countries': len(geo_data.get('countries', [])),
                               'cities': len(geo_data.get('cities', [])),
                               'landmarks': len(geo_data.get('landmarks', [])),
                               'regions': len(geo_data.get('special_regions', []))
                           })
            
            return enriched_query
            
        except Exception as e:
            logger.error("Error enriching query", 
                        query=query,
                        error=str(e))
            # En caso de error, retornar query original
            return query
    
    def analyze_country_relevance(self, text: str, countries: List[str]) -> Dict[str, float]:
        """
        Analiza la relevancia de cada país en el texto usando múltiples factores.
        Retorna score de 0-1 para cada país (sin hardcodeo de palabras específicas).
        
        Factores considerados:
        1. Frecuencia de menciones del país
        2. Ciudades del país mencionadas
        3. Presencia en sección de itinerario
        4. Noches de alojamiento en el país
        5. Contexto negativo (palabras que indican no-destino)
        """
        scores = {}
        text_lower = self._normalize(text)  # FIX: Normalizar texto (no solo lowercase)
        
        for country in countries:
            score = 0.0
            country_lower = self._normalize(country)
            
            # FACTOR 1: Frecuencia de menciones (max 0.3) - AUMENTADO
            mentions = text_lower.count(country_lower)
            score += min(mentions * 0.1, 0.3)  # Antes: 0.05, max 0.2
            
            # FACTOR 2: Ciudades del país mencionadas (max 0.35) - AUMENTADO
            country_cities = [city for city, c in self.city_to_country.items() if c == country]
            cities_found = sum(1 for city in country_cities if self._normalize(city) in text_lower)
            # Dar más peso: 0.15 por ciudad (si el país no se menciona, las ciudades son la evidencia principal)
            score += min(cities_found * 0.15, 0.35)  # Antes: 0.1, max 0.25
            
            # FACTOR 3: Presencia en sección de itinerario (0.25) - AUMENTADO
            itinerary_patterns = [
                r'itinerario[:\s]+(.*?)(?=\n\n[A-Z]|\Z)',
                r'recorrido[:\s]+(.*?)(?=\n\n[A-Z]|\Z)',
                r'programa[:\s]+(.*?)(?=\n\n[A-Z]|\Z)'
            ]
            for pattern in itinerary_patterns:
                match = re.search(pattern, text_lower, re.DOTALL | re.IGNORECASE)
                if match and country_lower in match.group(1):
                    score += 0.25  # Antes: 0.2
                    break
            
            # FACTOR 4: Noches de alojamiento (max 0.3)
            accommodation_patterns = [
                r'alojamiento[s]?[:\s]+(.*?)(?=\n\n[A-Z]|\Z)',
                r'hotel[es]?[:\s]+(.*?)(?=\n\n[A-Z]|\Z)',
                r'hospedaje[:\s]+(.*?)(?=\n\n[A-Z]|\Z)'
            ]
            for pattern in accommodation_patterns:
                match = re.search(pattern, text_lower, re.DOTALL | re.IGNORECASE)
                if match:
                    accommodation_text = match.group(1)
                    # Buscar patrón: "X noche(s) + país/ciudad"
                    nights_pattern = rf'(\d+)\s*noche[s]?\s+.*?{country_lower}'
                    nights_match = re.search(nights_pattern, accommodation_text)
                    if nights_match:
                        nights = int(nights_match.group(1))
                        if nights == 1:
                            score += 0.02  # 1 noche = probablemente pre-viaje - REDUCIDO
                        elif nights == 2:
                            score += 0.15  # 2 noches = destino breve
                        elif nights == 3:
                            score += 0.2   # 3 noches = destino válido
                        else:
                            score += 0.3   # 4+ noches = destino real
                    break
            
            # FACTOR 5: Contexto negativo - palabras que indican no-destino (penalización)
            # NO es hardcodeo porque busca CUALQUIER palabra de este tipo cerca del país
            negative_context_keywords = [
                'pre-viaje', 'pre viaje', 'previaje',
                'escala', 'escalas',
                'tránsito', 'transito',
                'conexión', 'conexion',
                'desde', 'salida desde',
                'partida', 'punto de partida'
            ]
            
            for keyword in negative_context_keywords:
                # Buscar keyword cerca del país (ventana de 50 caracteres)
                pattern = rf'(?:{keyword}.{{0,50}}{country_lower}|{country_lower}.{{0,50}}{keyword})'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    score -= 0.3  # Penalización por contexto negativo - AUMENTADO
                    logger.debug("Negative context detected",
                               country=country,
                               keyword=keyword,
                               penalty=-0.3)
                    break  # Solo penalizar una vez
            
            # Clamp score entre 0 y 1
            scores[country] = max(0.0, min(1.0, score))
            
            logger.debug("Country relevance calculated",
                        country=country,
                        score=f"{scores[country]:.2f}",
                        mentions=mentions,
                        cities_found=cities_found)
        
        return scores
    
    def filter_destination_countries(self, text: str, detected_countries: List[str], 
                                     document_type: str = "package") -> List[str]:
        """
        Filtra países para quedarse solo con destinos reales.
        Usa análisis inteligente de relevancia (sin hardcodeo).
        
        Args:
            text: Texto completo del documento
            detected_countries: Lista de países detectados
            document_type: Tipo de documento (solo aplica a "package")
        
        Returns:
            Lista filtrada de países que son destinos reales
        """
        # Solo aplicar filtro a paquetes turísticos
        if document_type != "package":
            logger.debug("Skipping country filter",
                        document_type=document_type,
                        reason="not_a_package")
            return detected_countries
        
        # Si no hay países o solo hay 1, no filtrar
        if not detected_countries or len(detected_countries) <= 1:
            logger.debug("Skipping country filter",
                        countries_count=len(detected_countries),
                        reason="single_or_no_country")
            return detected_countries
        
        # Analizar relevancia de cada país
        scores = self.analyze_country_relevance(text, detected_countries)
        
        # Filtrar países con score >= 0.15 (threshold ajustado)
        # Incluye países con al menos 1 ciudad detectada
        RELEVANCE_THRESHOLD = 0.15
        destination_countries = [
            country for country, score in scores.items() 
            if score >= RELEVANCE_THRESHOLD
        ]
        
        # Si el filtro elimina TODOS los países, mantener los originales
        # (evitar falsos positivos)
        if not destination_countries:
            logger.warning("Country filter removed all countries, keeping originals",
                          original_countries=detected_countries,
                          scores=scores)
            return detected_countries
        
        # Log de países filtrados
        filtered_out = [c for c in detected_countries if c not in destination_countries]
        if filtered_out:
            logger.info("Countries filtered as non-destinations",
                       original_countries=detected_countries,
                       destination_countries=destination_countries,
                       filtered_out=filtered_out,
                       scores={c: f"{s:.2f}" for c, s in scores.items()})
        
        return destination_countries
    
    def get_countries_in_same_region(self, country: str) -> List[str]:
        """Obtiene países de la misma región"""
        info = self.get_country_info(country)
        if not info:
            return []
        
        region = info['region']
        return self.region_to_countries.get(region, [])


# Instancia global
intelligent_extractor = IntelligentGeographyExtractor()
