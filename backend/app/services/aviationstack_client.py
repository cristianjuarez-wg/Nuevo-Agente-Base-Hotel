"""
Cliente para AviationStack API
Maneja consultas de estado de vuelos
"""
import requests
from typing import Optional, Dict, List
from datetime import datetime
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class AviationStackClient:
    """Cliente para consultar AviationStack API"""
    
    BASE_URL = "https://api.aviationstack.com/v1/flights"
    API_KEY = "b0401e7a9ea1d32dc339b102ad4ee613"
    
    def get_flight_by_iata(self, flight_iata: str, flight_date: str = None) -> Optional[Dict]:
        """
        Busca vuelo por código IATA y fecha
        
        Args:
            flight_iata: Código IATA del vuelo (ej: "IB106")
            flight_date: Fecha del vuelo en formato YYYY-MM-DD (REQUERIDO para precisión)
            
        Returns:
            Datos del vuelo o None si no se encuentra
        """
        try:
            params = {
                "access_key": self.API_KEY,
                "flight_iata": flight_iata
            }
            
            # Agregar fecha si está disponible (CRÍTICO para vuelos recurrentes)
            if flight_date:
                params["flight_date"] = flight_date
            
            logger.info("Fetching flight from API", 
                       flight_iata=flight_iata, 
                       flight_date=flight_date)
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('data') and len(data['data']) > 0:
                    logger.info("Flight found", 
                               flight_iata=flight_iata,
                               status=data['data'][0].get('flight_status'))
                    return data['data'][0]
                else:
                    logger.warning("Flight not found in API", flight_iata=flight_iata)
                    return None
            else:
                logger.error("API error", 
                           status_code=response.status_code,
                           response=response.text)
                return None
                
        except Exception as e:
            logger.error("Error fetching flight", 
                        flight_iata=flight_iata, 
                        error=str(e))
            return None
    
    def get_flights_by_airline(self, airline_name: str, flight_date: str = None) -> List[Dict]:
        """
        Busca vuelos por aerolínea
        
        Args:
            airline_name: Nombre de la aerolínea
            flight_date: Fecha en formato YYYY-MM-DD (opcional)
            
        Returns:
            Lista de vuelos
        """
        try:
            params = {
                "access_key": self.API_KEY,
                "airline_name": airline_name,
                "limit": 100
            }
            
            if flight_date:
                params["flight_date"] = flight_date
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            
            return []
            
        except Exception as e:
            logger.error("Error fetching flights by airline", 
                        airline=airline_name, 
                        error=str(e))
            return []
    
    def get_flights_by_airport(self, airport_iata: str, flight_date: str = None) -> List[Dict]:
        """
        Busca vuelos por aeropuerto de salida
        
        Args:
            airport_iata: Código IATA del aeropuerto (ej: "MAD")
            flight_date: Fecha en formato YYYY-MM-DD (opcional)
            
        Returns:
            Lista de vuelos
        """
        try:
            params = {
                "access_key": self.API_KEY,
                "dep_iata": airport_iata,
                "limit": 100
            }
            
            if flight_date:
                params["flight_date"] = flight_date
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            
            return []
            
        except Exception as e:
            logger.error("Error fetching flights by airport", 
                        airport=airport_iata, 
                        error=str(e))
            return []
