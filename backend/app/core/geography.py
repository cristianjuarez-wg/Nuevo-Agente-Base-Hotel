import json
import re
from typing import List, Dict, Set, Optional
from unidecode import unidecode
from app.config import settings

class GeographyService:
    def __init__(self):
        with open(settings.GEOGRAPHY_DATA_PATH, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        self._build_search_index()
    
    def _normalize(self, text: str) -> str:
        """Normaliza texto para búsqueda (sin acentos, minúsculas)"""
        return unidecode(text.lower().strip())
    
    def _build_search_index(self):
        """Construye índice de búsqueda rápida"""
        self.continent_map = {}
        self.country_to_continent = {}
        self.city_map = {}
        
        # Mapear continentes
        for continent, data in self.data['continents'].items():
            norm_continent = self._normalize(continent)
            self.continent_map[norm_continent] = continent
            
            # Agregar aliases de continentes
            for alias in data.get('aliases', []):
                self.continent_map[self._normalize(alias)] = continent
            
            # Mapear países a continentes
            for country in data['countries']:
                norm_country = self._normalize(country)
                self.country_to_continent[norm_country] = continent
                
                # Agregar aliases de países
                if country in self.data.get('country_aliases', {}):
                    for alias in self.data['country_aliases'][country]:
                        self.country_to_continent[self._normalize(alias)] = continent
        
        # Mapear ciudades (si existen en los datos)
        if 'city_aliases' in self.data:
            for city, aliases in self.data['city_aliases'].items():
                norm_city = self._normalize(city)
                self.city_map[norm_city] = city
                for alias in aliases:
                    self.city_map[self._normalize(alias)] = city
    
    def detect_continent(self, query: str) -> Optional[str]:
        """Detecta si la consulta menciona un continente (word-boundary para evitar falsos positivos)"""
        norm_query = self._normalize(query)
        for norm_continent, continent in self.continent_map.items():
            # Usar word boundary para que "ue" (alias de Europa) no matchee dentro de "paquetes"
            if re.search(r'\b' + re.escape(norm_continent) + r'\b', norm_query):
                return continent
        return None
    
    def detect_countries(self, query: str) -> List[str]:
        """Detecta países mencionados en la consulta"""
        norm_query = self._normalize(query)
        detected = []
        for norm_country, continent in self.country_to_continent.items():
            if norm_country in norm_query:
                # Obtener nombre original del país
                for country in self.data['continents'][continent]['countries']:
                    if self._normalize(country) == norm_country:
                        detected.append(country)
                        break
        return detected
    
    def detect_cities(self, query: str) -> List[str]:
        """Detecta ciudades mencionadas en la consulta"""
        norm_query = self._normalize(query)
        detected = []
        for norm_city, city in self.city_map.items():
            if norm_city in norm_query:
                detected.append(city)
        return detected
    
    def get_countries_by_continent(self, continent: str) -> List[str]:
        """Obtiene lista de países de un continente"""
        continent = self._normalize(continent)
        if continent in self.continent_map:
            real_continent = self.continent_map[continent]
            return self.data['continents'][real_continent]['countries']
        return []
    
    def get_continent_by_country(self, country: str) -> Optional[str]:
        """Obtiene el continente de un país específico"""
        norm_country = self._normalize(country)
        return self.country_to_continent.get(norm_country)
    
    def enrich_query(self, query: str) -> str:
        """Enriquece la consulta con información geográfica"""
        enriched_parts = [query]
        
        # Detectar componentes geográficos
        continent = self.detect_continent(query)
        countries = self.detect_countries(query)
        cities = self.detect_cities(query)
        
        # Si menciona continente, agregar países
        if continent and not countries:
            countries_list = self.get_countries_by_continent(continent)
            if countries_list:
                enriched_parts.append(f"Países de {continent}: {', '.join(countries_list)}")
        
        # Si menciona países, agregar información del continente
        if countries:
            for country in countries:
                cont = self.get_continent_by_country(country)
                if cont:
                    enriched_parts.append(f"{country} está en {cont}")
        
        # Si menciona ciudades, agregar contexto
        if cities:
            enriched_parts.append(f"Ciudades mencionadas: {', '.join(cities)}")
        
        return " | ".join(enriched_parts)
    
    def get_geographic_analysis(self, query: str) -> Dict:
        """Análisis completo de componentes geográficos"""
        return {
            "continent": self.detect_continent(query),
            "countries": self.detect_countries(query),
            "cities": self.detect_cities(query),
            "enriched_query": self.enrich_query(query)
        }
    
    def get_all_continents(self) -> List[str]:
        """Obtiene lista de todos los continentes disponibles"""
        return list(self.data['continents'].keys())
    
    def get_all_countries(self) -> List[str]:
        """Obtiene lista de todos los países disponibles"""
        all_countries = []
        for continent_data in self.data['continents'].values():
            all_countries.extend(continent_data['countries'])
        return sorted(all_countries)

# Instancia global del servicio
geography_service = GeographyService()
