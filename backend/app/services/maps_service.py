"""
Servicio de Google Maps
Genera links de Google Maps con ubicación de terminales
"""
from sqlalchemy.orm import Session
from typing import Optional, Dict
from app.models.airport_terminal import AirportTerminal
from app.services.terminal_discovery_service import get_terminal_discovery_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class MapsService:
    """Servicio para generar links de Google Maps a terminales de aeropuerto"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_terminal_maps_link(self, airport_iata: str, terminal_code: str,
                              airport_name: str = None) -> Optional[Dict]:
        """
        Obtiene link de Google Maps para una terminal
        Busca automáticamente si no existe en BD
        
        Args:
            airport_iata: Código IATA del aeropuerto (ej: "EZE")
            terminal_code: Código de terminal (ej: "3", "A")
            airport_name: Nombre del aeropuerto (opcional, ayuda en búsqueda)
            
        Returns:
            dict con maps_url, display_text, confidence, instructions
            o None si no se pudo obtener
        """
        if not airport_iata or not terminal_code:
            return None
        
        logger.info(f"Solicitando link de maps para {airport_iata} Terminal {terminal_code}")
        
        # 1. Buscar en BD primero
        terminal = self._get_terminal_from_db(airport_iata, terminal_code)
        
        if terminal:
            logger.info(f"✅ Terminal encontrada en BD (método: {terminal.discovery_method})")
            return self._generate_link(terminal)
        
        # 2. No existe, buscar automáticamente
        logger.info(f"Terminal no encontrada en BD, iniciando búsqueda automática...")
        discovery_service = get_terminal_discovery_service(self.db)
        terminal = discovery_service.discover_terminal_coordinates(
            airport_iata, terminal_code, airport_name
        )
        
        if terminal:
            logger.info(f"✅ Terminal descubierta automáticamente")
            return self._generate_link(terminal)
        
        # 3. No se pudo encontrar
        logger.warning(f"❌ No se pudo obtener link para {airport_iata} Terminal {terminal_code}")
        return None
    
    def _get_terminal_from_db(self, airport_iata: str, terminal_code: str) -> Optional[AirportTerminal]:
        """Busca terminal en base de datos"""
        return self.db.query(AirportTerminal).filter(
            AirportTerminal.airport_iata == airport_iata,
            AirportTerminal.terminal_code == terminal_code,
            AirportTerminal.is_active == True
        ).first()
    
    def _generate_link(self, terminal: AirportTerminal) -> Dict:
        """
        Genera link de Google Maps con coordenadas de terminal
        
        Args:
            terminal: Objeto AirportTerminal con coordenadas
            
        Returns:
            dict con información del link
        """
        # URL de Google Maps con coordenadas
        maps_url = f"https://www.google.com/maps/search/?api=1&query={terminal.latitude},{terminal.longitude}"
        
        # Texto descriptivo
        display_text = terminal.terminal_name or f"Terminal {terminal.terminal_code}"
        
        # Nivel de confianza
        confidence = float(terminal.confidence_score) if terminal.confidence_score else 1.0
        
        # Instrucciones según confianza
        if confidence >= 0.8:
            instructions = "Toca el link para ver la ubicación exacta en Google Maps y obtener direcciones desde tu ubicación actual."
        elif confidence >= 0.5:
            instructions = "Toca el link para ver la ubicación aproximada en Google Maps. Verifica en las pantallas del aeropuerto al llegar."
        else:
            instructions = "Toca el link para ver la ubicación general del aeropuerto. Una vez dentro, sigue las señalizaciones para encontrar la terminal."
        
        # Nota sobre descubrimiento automático
        discovery_note = None
        if terminal.auto_discovered:
            if terminal.discovery_method == 'airport_fallback':
                discovery_note = "Ubicación general del aeropuerto (terminal específica no encontrada)"
            else:
                discovery_note = f"Ubicación descubierta automáticamente (confianza: {int(confidence * 100)}%)"
        
        return {
            "maps_url": maps_url,
            "display_text": display_text,
            "confidence": confidence,
            "instructions": instructions,
            "discovery_note": discovery_note,
            "terminal_name": terminal.terminal_name,
            "airport_name": terminal.airport_name,
            "is_fallback": terminal.discovery_method == 'airport_fallback' if terminal.auto_discovered else False
        }
    
    def generate_flight_location_message(self, airport_iata: str, terminal_code: str,
                                        airport_name: str = None, gate: str = None) -> Dict:
        """
        Genera mensaje completo con ubicación de vuelo
        Incluye terminal y opcionalmente puerta
        
        Args:
            airport_iata: Código IATA
            terminal_code: Código de terminal
            airport_name: Nombre del aeropuerto
            gate: Puerta de embarque (opcional)
            
        Returns:
            dict con mensaje formateado y link
        """
        # Obtener link de maps
        maps_info = self.get_terminal_maps_link(airport_iata, terminal_code, airport_name)
        
        if not maps_info:
            # Sin link disponible
            if gate:
                return {
                    "text": f"📍 Terminal {terminal_code}, Puerta {gate}",
                    "has_link": False,
                    "instructions": f"Busca Terminal {terminal_code} en el aeropuerto. Dentro, sigue las pantallas para encontrar la Puerta {gate}."
                }
            else:
                return {
                    "text": f"📍 Terminal {terminal_code}",
                    "has_link": False,
                    "instructions": f"Busca Terminal {terminal_code} en el aeropuerto. La puerta de embarque se asignará aproximadamente 2 horas antes del vuelo."
                }
        
        # Con link disponible
        message_parts = []
        
        # Texto principal
        if gate:
            message_parts.append(f"📍 Terminal {terminal_code}, Puerta {gate}")
        else:
            message_parts.append(f"📍 Terminal {terminal_code}")
        
        # Link
        message_parts.append(f"\n{maps_info['maps_url']}")
        message_parts.append(f"{maps_info['display_text']}")
        
        # Instrucciones
        if gate:
            if maps_info['is_fallback']:
                instructions = f"{maps_info['instructions']} Una vez dentro, sigue las pantallas para encontrar la Puerta {gate}."
            else:
                instructions = f"El link te lleva a Terminal {terminal_code}. Una vez dentro, sigue las pantallas para encontrar la Puerta {gate}."
        else:
            instructions = maps_info['instructions']
            if not maps_info['is_fallback']:
                instructions += " La puerta de embarque se asignará aproximadamente 2 horas antes del vuelo."
        
        return {
            "text": "\n".join(message_parts),
            "has_link": True,
            "maps_url": maps_info['maps_url'],
            "confidence": maps_info['confidence'],
            "instructions": instructions,
            "discovery_note": maps_info.get('discovery_note')
        }


# Factory function
def get_maps_service(db: Session) -> MapsService:
    """Factory para obtener instancia del servicio"""
    return MapsService(db)
