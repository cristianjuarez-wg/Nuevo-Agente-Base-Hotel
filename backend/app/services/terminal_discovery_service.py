"""
Servicio de Descubrimiento Automático de Terminales
Busca coordenadas GPS usando servicios gratuitos (Nominatim, Overpass)
"""
import requests
import json
import time
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.airport_terminal import AirportTerminal, TerminalDiscoveryLog
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class TerminalDiscoveryService:
    """Servicio para descubrir automáticamente coordenadas de terminales"""
    
    # Base de datos de aeropuertos principales (fallback)
    KNOWN_AIRPORTS = {
        "EZE": {"lat": -34.8222, "lng": -58.5358, "name": "Aeropuerto Internacional Ministro Pistarini", "city": "Buenos Aires", "country": "Argentina"},
        "AEP": {"lat": -34.5592, "lng": -58.4156, "name": "Aeroparque Jorge Newbery", "city": "Buenos Aires", "country": "Argentina"},
        "COR": {"lat": -31.3236, "lng": -64.2080, "name": "Aeropuerto Internacional Ingeniero Ambrosio Taravella", "city": "Córdoba", "country": "Argentina"},
        "MDZ": {"lat": -32.8317, "lng": -68.7929, "name": "Aeropuerto Internacional Gobernador Francisco Gabrielli", "city": "Mendoza", "country": "Argentina"},
        "DFW": {"lat": 32.8998, "lng": -97.0403, "name": "Dallas/Fort Worth International Airport", "city": "Dallas", "country": "USA"},
        "MIA": {"lat": 25.7959, "lng": -80.2870, "name": "Miami International Airport", "city": "Miami", "country": "USA"},
        "JFK": {"lat": 40.6413, "lng": -73.7781, "name": "John F. Kennedy International Airport", "city": "New York", "country": "USA"},
        "LAX": {"lat": 33.9425, "lng": -118.4081, "name": "Los Angeles International Airport", "city": "Los Angeles", "country": "USA"},
        "MAD": {"lat": 40.4719, "lng": -3.5626, "name": "Adolfo Suárez Madrid-Barajas", "city": "Madrid", "country": "España"},
        "BCN": {"lat": 41.2974, "lng": 2.0833, "name": "Aeropuerto de Barcelona-El Prat", "city": "Barcelona", "country": "España"},
        "CDG": {"lat": 49.0097, "lng": 2.5479, "name": "Aéroport Paris-Charles de Gaulle", "city": "París", "country": "Francia"},
        "FCO": {"lat": 41.8003, "lng": 12.2389, "name": "Aeroporto di Roma-Fiumicino", "city": "Roma", "country": "Italia"},
        "LHR": {"lat": 51.4700, "lng": -0.4543, "name": "London Heathrow Airport", "city": "Londres", "country": "Reino Unido"},
        "GRU": {"lat": -23.4356, "lng": -46.4731, "name": "Aeroporto Internacional de São Paulo/Guarulhos", "city": "São Paulo", "country": "Brasil"},
        "SCL": {"lat": -33.3930, "lng": -70.7858, "name": "Aeropuerto Internacional Arturo Merino Benítez", "city": "Santiago", "country": "Chile"},
        "LIM": {"lat": -12.0219, "lng": -77.1143, "name": "Aeropuerto Internacional Jorge Chávez", "city": "Lima", "country": "Perú"},
        "BOG": {"lat": 4.7016, "lng": -74.1469, "name": "Aeropuerto Internacional El Dorado", "city": "Bogotá", "country": "Colombia"},
        "MEX": {"lat": 19.4363, "lng": -99.0721, "name": "Aeropuerto Internacional de la Ciudad de México", "city": "Ciudad de México", "country": "México"},
        "CUN": {"lat": 21.0365, "lng": -86.8770, "name": "Aeropuerto Internacional de Cancún", "city": "Cancún", "country": "México"},
        "PUJ": {"lat": 18.5674, "lng": -68.3634, "name": "Aeropuerto Internacional de Punta Cana", "city": "Punta Cana", "country": "República Dominicana"},
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def discover_terminal_coordinates(self, airport_iata: str, terminal_code: str, 
                                     airport_name: str = None) -> AirportTerminal:
        """
        Busca automáticamente coordenadas de terminal
        Intenta múltiples fuentes gratuitas en orden de precisión
        
        Args:
            airport_iata: Código IATA del aeropuerto (ej: "EZE")
            terminal_code: Código de terminal (ej: "3", "A")
            airport_name: Nombre del aeropuerto (opcional)
            
        Returns:
            AirportTerminal o None
        """
        logger.info(f"Iniciando búsqueda automática: {airport_iata} Terminal {terminal_code}")
        
        # Obtener info del aeropuerto
        airport_info = self.KNOWN_AIRPORTS.get(airport_iata, {})
        if not airport_name and airport_info:
            airport_name = airport_info.get("name")
        
        # Método 1: Nominatim (OpenStreetMap)
        result = self._search_nominatim(airport_iata, terminal_code, airport_name)
        if result and result.get('confidence', 0) > 0.7:
            return self._save_discovered_terminal(
                airport_iata, terminal_code, result, 'nominatim', airport_info
            )
        
        # Método 2: Overpass API (OpenStreetMap detallado)
        result = self._search_overpass(airport_iata, terminal_code)
        if result and result.get('confidence', 0) > 0.7:
            return self._save_discovered_terminal(
                airport_iata, terminal_code, result, 'overpass', airport_info
            )
        
        # Método 3: Fallback - Coordenadas del aeropuerto general
        result = self._get_airport_fallback(airport_iata, terminal_code)
        if result:
            return self._save_discovered_terminal(
                airport_iata, terminal_code, result, 'airport_fallback', airport_info
            )
        
        # No se pudo encontrar
        self._log_failed_discovery(airport_iata, terminal_code, airport_name)
        logger.warning(f"No se encontraron coordenadas para {airport_iata} Terminal {terminal_code}")
        return None
    
    def _search_nominatim(self, airport_iata: str, terminal_code: str, 
                         airport_name: str) -> dict:
        """Buscar en Nominatim (OpenStreetMap Geocoding)"""
        if not airport_name:
            return None
        
        # Construir query
        query = f"Terminal {terminal_code}, {airport_name}"
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1
        }
        headers = {
            "User-Agent": "TravelAgentSystem/1.0 (contact@travelagent.com)"
        }
        
        try:
            logger.info(f"Buscando en Nominatim: {query}")
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if data and len(data) > 0:
                    result = data[0]
                    
                    # Verificar que sea relevante (contiene aeropuerto o terminal)
                    display_name = result.get("display_name", "").lower()
                    if "airport" in display_name or "terminal" in display_name or airport_iata.lower() in display_name:
                        logger.info(f"✅ Nominatim encontró: {result.get('display_name')}")
                        return {
                            "latitude": float(result["lat"]),
                            "longitude": float(result["lon"]),
                            "terminal_name": result.get("display_name"),
                            "confidence": 0.8
                        }
            
            time.sleep(1)  # Rate limiting: 1 req/segundo
        
        except Exception as e:
            logger.error(f"Error en Nominatim: {e}")
        
        return None
    
    def _search_overpass(self, airport_iata: str, terminal_code: str) -> dict:
        """Buscar en Overpass API (OpenStreetMap detallado)"""
        
        # Query Overpass QL para buscar terminales de aeropuerto
        query = f"""
        [out:json][timeout:10];
        (
          node["aeroway"="terminal"]["iata"="{airport_iata}"]["ref"="{terminal_code}"];
          way["aeroway"="terminal"]["iata"="{airport_iata}"]["ref"="{terminal_code}"];
          node["aeroway"="terminal"]["name"~"Terminal {terminal_code}",i];
          way["aeroway"="terminal"]["name"~"Terminal {terminal_code}",i];
        );
        out center;
        """
        
        url = "https://overpass-api.de/api/interpreter"
        
        try:
            logger.info(f"Buscando en Overpass: {airport_iata} Terminal {terminal_code}")
            response = requests.post(url, data={"data": query}, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("elements") and len(data["elements"]) > 0:
                    element = data["elements"][0]
                    
                    # Obtener coordenadas
                    if "lat" in element and "lon" in element:
                        lat, lon = element["lat"], element["lon"]
                    elif "center" in element:
                        lat, lon = element["center"]["lat"], element["center"]["lon"]
                    else:
                        return None
                    
                    terminal_name = element.get("tags", {}).get("name", f"Terminal {terminal_code}")
                    logger.info(f"✅ Overpass encontró: {terminal_name}")
                    
                    return {
                        "latitude": lat,
                        "longitude": lon,
                        "terminal_name": terminal_name,
                        "confidence": 0.9
                    }
        
        except Exception as e:
            logger.error(f"Error en Overpass: {e}")
        
        return None
    
    def _get_airport_fallback(self, airport_iata: str, terminal_code: str) -> dict:
        """Fallback: Usar coordenadas generales del aeropuerto"""
        
        if airport_iata in self.KNOWN_AIRPORTS:
            airport = self.KNOWN_AIRPORTS[airport_iata]
            logger.info(f"⚠️  Usando fallback (aeropuerto general): {airport['name']}")
            
            return {
                "latitude": airport["lat"],
                "longitude": airport["lng"],
                "terminal_name": f"Aeropuerto {airport['name']} (ubicación general)",
                "confidence": 0.3
            }
        
        return None
    
    def _save_discovered_terminal(self, airport_iata: str, terminal_code: str, 
                                  result: dict, method: str, airport_info: dict) -> AirportTerminal:
        """Guardar terminal descubierta automáticamente"""
        
        terminal = AirportTerminal(
            airport_iata=airport_iata,
            airport_name=airport_info.get("name", ""),
            airport_city=airport_info.get("city"),
            airport_country=airport_info.get("country"),
            terminal_code=terminal_code,
            terminal_name=result.get("terminal_name"),
            latitude=result["latitude"],
            longitude=result["longitude"],
            auto_discovered=True,
            discovery_method=method,
            confidence_score=result.get("confidence", 0.5),
            last_verified=datetime.utcnow(),
            search_attempts=1,
            is_active=True
        )
        
        try:
            self.db.add(terminal)
            self.db.commit()
            self.db.refresh(terminal)
            
            # Log exitoso
            self._log_discovery(
                airport_iata, terminal_code, method, True,
                json.dumps({"lat": result["latitude"], "lng": result["longitude"]}),
                result.get("confidence"), None, airport_info.get("name")
            )
            
            logger.info(f"✅ Terminal guardada: {airport_iata} Terminal {terminal_code} (método: {method}, confianza: {result.get('confidence')})")
            return terminal
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error al guardar terminal: {e}")
            return None
    
    def _log_discovery(self, airport_iata: str, terminal_code: str, method: str,
                      success: bool, coordinates: str, confidence: float,
                      error: str, airport_name: str = None):
        """Registrar intento de búsqueda en log"""
        
        log_entry = TerminalDiscoveryLog(
            airport_iata=airport_iata,
            terminal_code=terminal_code,
            airport_name=airport_name,
            search_query=f"Terminal {terminal_code}, {airport_name or airport_iata}",
            method_used=method,
            success=success,
            coordinates_found=coordinates,
            confidence_score=confidence,
            error_message=error
        )
        
        try:
            self.db.add(log_entry)
            self.db.commit()
        except:
            self.db.rollback()
    
    def _log_failed_discovery(self, airport_iata: str, terminal_code: str, airport_name: str):
        """Registrar búsqueda fallida"""
        self._log_discovery(
            airport_iata, terminal_code, "all_methods_failed", False,
            None, 0.0, "No se encontraron coordenadas en ninguna fuente", airport_name
        )


# Instancia global del servicio
def get_terminal_discovery_service(db: Session) -> TerminalDiscoveryService:
    """Factory para obtener instancia del servicio"""
    return TerminalDiscoveryService(db)
