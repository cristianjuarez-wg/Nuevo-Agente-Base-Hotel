"""
Cliente para FlightAPI.io Flight Tracking API
"""
import requests
from typing import Optional, Dict
from datetime import datetime
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class FlightAPIClient:
    """Cliente para consultar vuelos en FlightAPI.io"""
    
    def __init__(self, api_key: str = None):
        """
        Inicializa el cliente de FlightAPI.io
        
        Args:
            api_key: API key de FlightAPI.io
        """
        from app.config import settings
        self.api_key = api_key or settings.FLIGHTAPI_API_KEY
        self.base_url = "https://api.flightapi.io/airline"
        
    def get_flight_by_code(
        self, 
        flight_number: str, 
        airline_code: str, 
        flight_date: str
    ) -> Optional[Dict]:
        """
        Obtiene información de un vuelo específico
        
        Args:
            flight_number: Número de vuelo sin código de aerolínea (ej: "1302")
            airline_code: Código IATA de la aerolínea (ej: "AR")
            flight_date: Fecha del vuelo en formato YYYY-MM-DD
            
        Returns:
            Dict con información del vuelo o None si no se encuentra
        """
        try:
            # Convertir fecha de YYYY-MM-DD a YYYYMMDD
            date_obj = datetime.strptime(flight_date, '%Y-%m-%d')
            date_formatted = date_obj.strftime('%Y%m%d')
            
            # Construir URL
            url = f"{self.base_url}/{self.api_key}"
            params = {
                'num': flight_number,
                'name': airline_code,
                'date': date_formatted
            }
            
            logger.info(
                "Fetching flight from FlightAPI.io",
                flight_number=flight_number,
                airline_code=airline_code,
                flight_date=flight_date,
                formatted_date=date_formatted
            )
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Manejar diferentes formatos de respuesta
                flights_data = None
                
                if isinstance(data, list) and len(data) > 0:
                    # Formato 1: Lista directa
                    flights_data = data
                elif isinstance(data, dict):
                    # Formato 2: Objeto con key 'flights'
                    if 'flights' in data and isinstance(data['flights'], list) and len(data['flights']) > 0:
                        flights_data = data['flights']
                    elif 'flight' in data and data['flight']:
                        flights_data = [data['flight']]
                
                if flights_data:
                    # Parsear respuesta
                    flight_info = self._parse_flight_data(flights_data, airline_code, flight_number)
                    
                    logger.info(
                        "Flight found in FlightAPI.io",
                        flight_iata=f"{airline_code}{flight_number}",
                        status=flight_info.get('flight_status')
                    )
                    
                    return flight_info
                else:
                    logger.warning(
                        "Flight not found in FlightAPI.io",
                        flight_number=flight_number,
                        airline_code=airline_code,
                        response=data
                    )
                    return None
                    
            elif response.status_code == 410:
                logger.warning(
                    "No flight data for this date",
                    flight_number=flight_number,
                    date=flight_date
                )
                return None
            else:
                logger.error(
                    "FlightAPI.io API error",
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return None
                
        except Exception as e:
            logger.error(
                "Error fetching flight from FlightAPI.io",
                error=str(e),
                flight_number=flight_number
            )
            return None
    
    def _parse_flight_data(self, data: list, airline_code: str, flight_number: str) -> Dict:
        """
        Parsea la respuesta de FlightAPI.io al formato esperado.
        Maneja múltiples formatos de respuesta de la API.
        
        Args:
            data: Lista de datos del vuelo de FlightAPI.io
            airline_code: Código de aerolínea
            flight_number: Número de vuelo
            
        Returns:
            Dict con información del vuelo en formato estándar
        """
        departure_info = {}
        arrival_info = {}
        flight_status = 'scheduled'
        
        # Buscar el vuelo correcto en la lista
        flight_data = None
        for item in data:
            if isinstance(item, dict):
                # Verificar si es el vuelo que buscamos
                fn = item.get('flightNumber')
                if fn and str(fn) == str(flight_number):
                    flight_data = item
                    break
        
        if not flight_data and data:
            flight_data = data[0]
        
        if not flight_data:
            flight_data = {}
        
        # FORMATO 1: API con keys 'departure' y 'arrival' (formato antiguo)
        if 'departure' in flight_data and 'arrival' in flight_data:
            departure_info = flight_data['departure']
            arrival_info = flight_data['arrival']
            flight_status = self._determine_status(departure_info, arrival_info)
        
        # FORMATO 2: API con keys directas (formato nuevo)
        elif 'departureTime' in flight_data or 'departureAirportCode' in flight_data:
            departure_info = {
                'airportCode': flight_data.get('departureAirportCode'),
                'terminal': flight_data.get('departureTerminal'),
                'gate': flight_data.get('departureGate'),
                'scheduledTime': flight_data.get('departureTime'),
                'estimatedTime': flight_data.get('estimatedDepartureTime'),
                'offGroundTime': flight_data.get('actualDepartureTime')
            }
            
            arrival_info = {
                'airportCode': flight_data.get('arrivalAirportCode'),
                'terminal': flight_data.get('arrivalTerminal'),
                'gate': flight_data.get('arrivalGate'),
                'baggage': flight_data.get('baggage'),
                'scheduledTime': flight_data.get('arrivalTime'),
                'estimatedTime': flight_data.get('estimatedArrivalTime'),
                'onGroundTime': flight_data.get('actualArrivalTime')
            }
            
            # Interpretar estado del vuelo
            status_text = flight_data.get('displayStatus', 'scheduled').lower()
            if 'landed' in status_text or 'arrived' in status_text:
                flight_status = 'landed'
            elif 'active' in status_text or 'en route' in status_text or 'airborne' in status_text:
                flight_status = 'active'
            elif 'cancelled' in status_text:
                flight_status = 'cancelled'
            elif 'delayed' in status_text:
                flight_status = 'delayed'
            else:
                flight_status = 'scheduled'
        
        # FORMATO 3: Intentar con cualquier otro formato
        else:
            # Extraer lo que podamos
            for item in data:
                if isinstance(item, dict):
                    if 'departure' in item:
                        departure_info = item['departure']
                    if 'arrival' in item:
                        arrival_info = item['arrival']
            
            if departure_info or arrival_info:
                flight_status = self._determine_status(departure_info, arrival_info)
        
        # Calcular delay
        delay_minutes = self._calculate_delay(departure_info)
        
        # Construir respuesta en formato estándar
        result = {
            'flight_iata': f"{airline_code}{flight_number}",
            'flight_number': flight_number,
            'airline_iata': airline_code,
            'flight_status': flight_status,
            'departure': {
                'airport': departure_info.get('airportCode'),
                'timezone': None,
                'iata': departure_info.get('airportCode'),
                'terminal': departure_info.get('terminal'),
                'gate': departure_info.get('gate'),
                'delay': delay_minutes,
                'scheduled': departure_info.get('departureDateTime'),
                'estimated': departure_info.get('estimatedTime'),
                'actual': departure_info.get('offGroundTime')
            },
            'arrival': {
                'airport': arrival_info.get('airportCode'),
                'timezone': None,
                'iata': arrival_info.get('airportCode'),
                'terminal': arrival_info.get('terminal'),
                'gate': arrival_info.get('gate'),
                'baggage': arrival_info.get('baggage'),
                'delay': None,
                'scheduled': arrival_info.get('arrivalDateTime'),
                'estimated': arrival_info.get('estimatedTime'),
                'actual': arrival_info.get('onGroundTime')
            },
            'delay_minutes': delay_minutes
        }
        
        return result
    
    def _determine_status(self, departure: Dict, arrival: Dict) -> str:
        """
        Determina el estado del vuelo basado en la información disponible
        
        Args:
            departure: Información de salida
            arrival: Información de llegada
            
        Returns:
            Estado del vuelo: scheduled, active, landed
        """
        # Si ya aterrizó
        if arrival.get('onGroundTime'):
            return 'landed'
        
        # Si ya despegó pero no aterrizó
        if departure.get('offGroundTime'):
            return 'active'
        
        # Si está programado
        return 'scheduled'
    
    def _calculate_delay(self, departure: Dict) -> int:
        """
        Calcula el delay en minutos
        
        Args:
            departure: Información de salida
            
        Returns:
            Delay en minutos (0 si no hay delay)
        """
        try:
            scheduled = departure.get('scheduledTime')
            estimated = departure.get('estimatedTime')
            
            if not scheduled or not estimated:
                return 0
            
            # Parsear tiempos (formato: "HH:MM, MMM DD")
            # Por simplicidad, si hay tiempo estimado diferente, asumimos delay
            if estimated and estimated != scheduled:
                # Aquí podrías implementar cálculo exacto si necesitas
                # Por ahora retornamos 0 si no hay información clara
                return 0
            
            return 0
            
        except Exception:
            return 0
