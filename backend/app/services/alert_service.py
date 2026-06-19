"""
Servicio para gestión de alertas proactivas
"""
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from app.models.alert_settings import AlertSettings
import structlog

logger = structlog.get_logger()

# Definición de todas las alertas del sistema
ALERT_DEFINITIONS = [
    # PRE-VIAJE
    {
        "alert_type": "welcome_voucher",
        "category": "pre_trip",
        "name": "Bienvenida y Voucher",
        "description": "Envía mensaje de bienvenida y voucher PDF 48 horas antes del inicio del viaje",
        "timing": "48 horas antes",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": False
    },
    {
        "alert_type": "checkin_outbound",
        "category": "pre_trip",
        "name": "Check-in Vuelo de Ida",
        "description": "Recuerda realizar check-in online 72 horas antes del vuelo de ida",
        "timing": "72 horas antes",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_airline_link": {"label": "Incluir link a aerolínea", "default": True},
            "include_booking_code": {"label": "Incluir código de reserva", "default": True},
            "include_recommendations": {"label": "Incluir recomendaciones", "default": True}
        }
    },
    {
        "alert_type": "transfer_outbound",
        "category": "pre_trip",
        "name": "Transfer de Ida",
        "description": "Detalles del transfer 24 horas antes con checklist y recomendaciones climáticas",
        "timing": "24 horas antes",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_transfer_details": {"label": "Datos del transfer", "default": True},
            "include_checklist": {"label": "Checklist de viaje", "default": True},
            "include_weather": {"label": "Recomendaciones climáticas", "default": True}
        }
    },
    
    # DURANTE EL VIAJE
    {
        "alert_type": "terminal_gate_outbound",
        "category": "during_trip",
        "name": "Terminal y Puerta (Ida)",
        "description": "Info de terminal y gate del vuelo de ida con mapa interactivo",
        "timing": "Al confirmar terminal/gate",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_maps_link": {"label": "Link a Google Maps", "default": True},
            "include_nearby_services": {"label": "Servicios cercanos", "default": True},
            "include_walking_time": {"label": "Tiempo de caminata", "default": True}
        }
    },
    {
        "alert_type": "baggage_claim_outbound",
        "category": "during_trip",
        "name": "Retiro de Equipaje (Ida)",
        "description": "Indica ubicación de cinta de equipaje con mapa de la terminal",
        "timing": "Al aterrizar",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_baggage_belt": {"label": "Incluir número de cinta de equipaje", "default": True},
            "include_terminal_map": {"label": "Incluir link a terminal en Google Maps", "default": True},
            "include_signage_tips": {"label": "Incluir instrucciones de señalética", "default": True}
        }
    },
    {
        "alert_type": "arrival_transfer",
        "category": "during_trip",
        "name": "Transfer de Recepción",
        "description": "Datos del transfer de recepción al aterrizar en destino",
        "timing": "Al aterrizar",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": False
    },
    {
        "alert_type": "activity_reminder",
        "category": "during_trip",
        "name": "Recordatorio de Actividad",
        "description": "Recuerda actividad la noche anterior con detalles y clima",
        "timing": "20:00 del día anterior",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_activity_details": {"label": "Detalles de actividad", "default": True},
            "include_transfer_info": {"label": "Datos del transfer", "default": True},
            "include_weather": {"label": "Recomendaciones climáticas", "default": True}
        }
    },
    {
        "alert_type": "intermediate_flights",
        "category": "during_trip",
        "name": "Vuelos Intermedios",
        "description": "Recuerda vuelos de conexión 48 horas antes",
        "timing": "48 horas antes",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": False
    },
    {
        "alert_type": "checkin_return",
        "category": "during_trip",
        "name": "Check-in Vuelo de Regreso",
        "description": "Recuerda check-in del vuelo de regreso 72 horas antes",
        "timing": "72 horas antes",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": False
    },
    {
        "alert_type": "terminal_gate_return",
        "category": "during_trip",
        "name": "Terminal y Puerta (Regreso)",
        "description": "Info de terminal y gate del vuelo de regreso con mapa interactivo",
        "timing": "Al confirmar terminal/gate",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_maps_link": {"label": "Link a Google Maps", "default": True},
            "include_nearby_services": {"label": "Servicios cercanos", "default": True},
            "include_walking_time": {"label": "Tiempo de caminata", "default": True}
        }
    },
    {
        "alert_type": "baggage_claim_return",
        "category": "during_trip",
        "name": "Retiro de Equipaje (Regreso)",
        "description": "Indica ubicación de cinta de equipaje con mapa de la terminal",
        "timing": "Al aterrizar",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": True,
        "sub_options": {
            "include_baggage_belt": {"label": "Incluir número de cinta de equipaje", "default": True},
            "include_terminal_map": {"label": "Incluir link a terminal en Google Maps", "default": True},
            "include_signage_tips": {"label": "Incluir instrucciones de señalética", "default": True}
        }
    },
    {
        "alert_type": "transfer_return",
        "category": "during_trip",
        "name": "Transfer de Regreso",
        "description": "Confirma transfer al aeropuerto 24 horas antes del regreso",
        "timing": "24 horas antes",
        "recipients": ["passenger"],
        "channels": ["whatsapp"],
        "has_sub_options": False
    },
    
    # POST-VIAJE
    {
        "alert_type": "satisfaction_survey",
        "category": "post_trip",
        "name": "Encuesta de Satisfacción",
        "description": "Solicita feedback 3 días después del regreso",
        "timing": "3 días después",
        "recipients": ["passenger"],
        "channels": ["whatsapp", "email"],
        "has_sub_options": True,
        "sub_options": {
            "send_whatsapp": {"label": "Enviar por WhatsApp", "default": True},
            "send_email": {"label": "Enviar por Email", "default": True},
            "include_incentive": {"label": "Incluir incentivo de descuento", "default": True}
        }
    },
    
    # OPERATIVAS
    {
        "alert_type": "flight_change",
        "category": "operational",
        "name": "Cambio de Vuelo",
        "description": "Notifica cambios de vuelo a todas las partes involucradas",
        "timing": "Inmediato",
        "recipients": ["passenger", "hotel", "transfer", "operator"],
        "channels": ["whatsapp", "email", "internal"],
        "has_sub_options": True,
        "sub_options": {
            "notify_passenger": {"label": "Notificar a pasajero", "default": True},
            "notify_hotel": {"label": "Notificar a hotel", "default": True},
            "notify_transfer": {"label": "Notificar a transfer", "default": True},
            "notify_operator": {"label": "Notificar a operador", "default": True}
        }
    },
    {
        "alert_type": "itinerary_change",
        "category": "operational",
        "name": "Cambio de Planificación",
        "description": "Notifica cambios en actividades, hoteles o transfers",
        "timing": "Inmediato",
        "recipients": ["passenger", "providers", "operator"],
        "channels": ["whatsapp", "email", "internal"],
        "has_sub_options": False
    },
    
    # EMERGENCIAS
    {
        "alert_type": "weather_alert",
        "category": "emergency",
        "name": "Alerta Meteorológica",
        "description": "Notifica condiciones climáticas adversas en el destino",
        "timing": "Al detectar",
        "recipients": ["passenger", "operator"],
        "channels": ["whatsapp", "internal"],
        "has_sub_options": True,
        "sub_options": {
            "heavy_rain": {"label": "Lluvia intensa", "default": True},
            "hurricane": {"label": "Huracán/Tormenta", "default": True},
            "snow": {"label": "Nevada/Frío extremo", "default": True},
            "heat": {"label": "Calor extremo", "default": True}
        }
    },
    {
        "alert_type": "seismic_alert",
        "category": "emergency",
        "name": "Alerta Sísmica",
        "description": "Notifica terremotos de magnitud significativa",
        "timing": "Al detectar",
        "recipients": ["passenger", "operator"],
        "channels": ["whatsapp", "internal"],
        "has_sub_options": False
    },
    {
        "alert_type": "security_alert",
        "category": "emergency",
        "name": "Alerta de Seguridad",
        "description": "Notifica situaciones de riesgo (disturbios, huelgas, emergencias)",
        "timing": "Al detectar",
        "recipients": ["passenger", "operator"],
        "channels": ["whatsapp", "internal"],
        "has_sub_options": False
    }
]

class AlertService:
    """Servicio para gestión de alertas proactivas"""
    
    def get_alert_definitions(self) -> List[Dict]:
        """Obtiene definiciones de todas las alertas disponibles"""
        return ALERT_DEFINITIONS
    
    def get_all_settings(self, db: Session) -> List[AlertSettings]:
        """Obtiene todas las configuraciones de alertas"""
        return db.query(AlertSettings).all()
    
    def get_settings_by_category(self, category: str, db: Session) -> List[AlertSettings]:
        """Obtiene configuraciones por categoría"""
        return db.query(AlertSettings).filter(AlertSettings.category == category).all()
    
    def get_setting(self, alert_type: str, db: Session) -> Optional[AlertSettings]:
        """Obtiene configuración de una alerta específica"""
        return db.query(AlertSettings).filter(AlertSettings.alert_type == alert_type).first()
    
    def update_setting(self, alert_type: str, is_enabled: bool, 
                      sub_options: Optional[Dict], excluded_tours: Optional[List],
                      db: Session) -> AlertSettings:
        """Actualiza configuración de una alerta"""
        setting = self.get_setting(alert_type, db)
        
        if not setting:
            # Crear nueva configuración
            # Buscar definición para obtener categoría
            definition = next((a for a in ALERT_DEFINITIONS if a["alert_type"] == alert_type), None)
            if not definition:
                raise ValueError(f"Alert type {alert_type} not found in definitions")
            
            setting = AlertSettings(
                alert_type=alert_type,
                category=definition["category"],
                is_enabled=is_enabled,
                sub_options=sub_options or {},
                excluded_tours=excluded_tours or []
            )
            db.add(setting)
        else:
            # Actualizar existente
            setting.is_enabled = is_enabled
            if sub_options is not None:
                setting.sub_options = sub_options
            if excluded_tours is not None:
                setting.excluded_tours = excluded_tours
        
        db.commit()
        db.refresh(setting)
        
        logger.info("Alert setting updated",
                   alert_type=alert_type,
                   is_enabled=is_enabled)
        
        return setting
    
    def bulk_update_settings(self, updates: List[Dict], db: Session) -> List[AlertSettings]:
        """Actualiza múltiples configuraciones"""
        results = []
        for update in updates:
            setting = self.update_setting(
                alert_type=update["alert_type"],
                is_enabled=update.get("is_enabled", False),
                sub_options=update.get("sub_options"),
                excluded_tours=update.get("excluded_tours"),
                db=db
            )
            results.append(setting)
        
        return results
    
    def should_send_alert(self, alert_type: str, tour_id: Optional[int], db: Session) -> bool:
        """Verifica si se debe enviar una alerta"""
        setting = self.get_setting(alert_type, db)
        
        if not setting or not setting.is_enabled:
            return False
        
        # Verificar si el tour está excluido
        if tour_id and setting.excluded_tours and tour_id in setting.excluded_tours:
            return False
        
        return True
    
    def initialize_default_settings(self, db: Session):
        """Inicializa configuraciones por defecto para todas las alertas"""
        for definition in ALERT_DEFINITIONS:
            existing = self.get_setting(definition["alert_type"], db)
            if not existing:
                setting = AlertSettings(
                    alert_type=definition["alert_type"],
                    category=definition["category"],
                    is_enabled=False,  # Por defecto desactivadas
                    sub_options={}
                )
                db.add(setting)
        
        db.commit()
        logger.info("Default alert settings initialized", count=len(ALERT_DEFINITIONS))


# Instancia global del servicio
alert_service = AlertService()
