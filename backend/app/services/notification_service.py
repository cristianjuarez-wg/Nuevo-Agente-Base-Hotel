"""
Servicio de Notificaciones (SIMULADO para MVP)
Registra notificaciones que se enviarían en producción
"""
from typing import Dict
from datetime import datetime
from app.core.observability.logging_config import get_logger
from app.utils.timezone_utils import utcnow_naive

logger = get_logger(__name__)

class NotificationService:
    """Servicio de notificaciones (SIMULADO para MVP)"""
    
    def simulate_notifications(self, package, changes: Dict) -> Dict:
        """
        Simula envío de notificaciones
        
        Args:
            package: Paquete vendido
            changes: Cambios detectados en el vuelo
            
        Returns:
            Dict con notificaciones simuladas
        """
        notifications = {}
        
        # Notificación al pasajero
        notifications["passenger"] = {
            "email": package.passenger_email,
            "subject": f"Cambio en tu vuelo {changes.get('flight_number', '')}",
            "message": self._build_passenger_message(package, changes),
            "simulated": True,
            "would_send_at": utcnow_naive().isoformat()
        }
        
        logger.info("Passenger notification simulated", 
                   email=package.passenger_email,
                   booking_code=package.booking_code)
        
        # Notificación a hotel si hay
        if package.accommodations:
            hotel = package.accommodations[0]
            if hotel.provider:
                notifications["hotel"] = {
                    "email": hotel.provider.email,
                    "provider_name": hotel.provider.provider_name,
                    "message": self._build_hotel_message(package, changes),
                    "simulated": True,
                    "would_send_at": utcnow_naive().isoformat()
                }
                
                logger.info("Hotel notification simulated",
                           provider=hotel.provider.provider_name,
                           booking_code=package.booking_code)
        
        # Notificación a transfer si hay
        if package.transfers:
            transfer = package.transfers[0]
            if transfer.provider:
                notifications["transfer"] = {
                    "phone": transfer.provider.whatsapp_number or transfer.provider.phone_number,
                    "provider_name": transfer.provider.provider_name,
                    "message": self._build_transfer_message(package, changes),
                    "simulated": True,
                    "would_send_at": utcnow_naive().isoformat()
                }
                
                logger.info("Transfer notification simulated",
                           provider=transfer.provider.provider_name,
                           booking_code=package.booking_code)
        
        return notifications
    
    def _build_passenger_message(self, package, changes: Dict) -> str:
        """Construye mensaje para el pasajero"""
        
        severity = changes.get('severity', 'low')
        change_list = changes.get('changes', [])
        
        if severity == 'critical':
            greeting = f"⚠️ IMPORTANTE: Cambio crítico en tu vuelo"
        elif severity == 'high':
            greeting = f"⚠️ Atención: Cambio significativo en tu vuelo"
        else:
            greeting = f"Actualización sobre tu vuelo"
        
        message = f"""
Hola {package.passenger_name},

{greeting}

Reserva: {package.booking_code}
Destino: {package.destination_country}

Cambios detectados:
"""
        
        for change in change_list:
            message += f"\n• {change.get('message', '')}"
        
        message += f"""

Tu hotel y transfer han sido notificados del cambio.

Si tienes dudas, contáctanos.

Equipo Aura Travel
"""
        
        return message.strip()
    
    def _build_hotel_message(self, package, changes: Dict) -> str:
        """Construye mensaje para el hotel"""
        
        message = f"""
Estimado Hotel,

Cambio en reserva {package.booking_code}:

Pasajero: {package.passenger_name} {package.passenger_lastname}
Contacto: {package.passenger_phone}

Cambios en vuelo:
"""
        
        for change in changes.get('changes', []):
            message += f"\n• {change.get('message', '')}"
        
        message += f"""

Por favor, ajustar horario de check-in según nueva llegada.

Saludos,
Aura Travel
"""
        
        return message.strip()
    
    def _build_transfer_message(self, package, changes: Dict) -> str:
        """Construye mensaje para el transfer"""
        
        message = f"""
Cambio en servicio de transfer

Reserva: {package.booking_code}
Pasajero: {package.passenger_name} {package.passenger_lastname}

Cambios en vuelo:
"""
        
        for change in changes.get('changes', []):
            message += f"\n• {change.get('message', '')}"
        
        message += f"""

Por favor, ajustar horario de pickup.

Aura Travel
"""
        
        return message.strip()
