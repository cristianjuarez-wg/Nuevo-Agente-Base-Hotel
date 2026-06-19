"""
Servicio de Monitoreo de Vuelos
Gestiona chequeos de estado y detección de cambios
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.utils.timezone_utils import now_argentina
from app.models.postsale import SoldPackage, PackageFlight, SupportTicket, TicketInteraction
from app.models.flight_tracking import FlightStatusTracking
from app.services.flightapi_client import FlightAPIClient
from app.services.notification_service import NotificationService
from app.core.logging_config import get_logger
import json

logger = get_logger(__name__)

class FlightMonitorService:
    """Servicio de monitoreo de vuelos"""
    
    def __init__(self, db: Session):
        self.db = db
        self.api_client = FlightAPIClient()
        self.notification_service = NotificationService()
    
    def get_upcoming_flights(self, hours: int = 48) -> List[Dict]:
        """Obtiene vuelos próximos a salir, agrupados por vuelo único"""
        now = now_argentina()
        cutoff = now + timedelta(hours=hours)
        
        flights = self.db.query(PackageFlight).join(
            SoldPackage, PackageFlight.package_id == SoldPackage.id
        ).filter(
            PackageFlight.departure_datetime >= now,
            PackageFlight.departure_datetime <= cutoff
        ).order_by(
            PackageFlight.departure_datetime
        ).all()
        
        logger.info("Querying upcoming flights", now=now, cutoff=cutoff, count=len(flights))
        
        # Agrupar vuelos por flight_number + departure_datetime
        grouped_flights = {}
        for flight in flights:
            # Crear clave única para agrupar
            key = f"{flight.flight_number}_{flight.departure_datetime.isoformat()}"
            
            if key not in grouped_flights:
                grouped_flights[key] = {
                    "flights": [],
                    "flight_number": flight.flight_number,
                    "flight_iata": flight.flight_iata,
                    "airline": flight.airline,
                    "departure_datetime": flight.departure_datetime,
                    "departure_airport": flight.departure_airport_code,
                    "arrival_airport": flight.arrival_airport_code,
                    "arrival_airport_name": flight.arrival_airport_name,
                }
            
            grouped_flights[key]["flights"].append(flight)
        
        # Construir resultado
        result = []
        for key, group in grouped_flights.items():
            flights_in_group = group["flights"]
            
            # Usar el primer vuelo como referencia para el chequeo
            first_flight = flights_in_group[0]
            last_check = self.db.query(FlightStatusTracking).filter(
                FlightStatusTracking.flight_id == first_flight.id
            ).order_by(FlightStatusTracking.check_timestamp.desc()).first()
            
            # Construir lista de pasajeros
            passengers = []
            total_pax = 0
            for flight in flights_in_group:
                pax_count = flight.package.total_passengers or 1
                total_pax += pax_count
                
                passengers.append({
                    "flight_id": flight.id,
                    "package_id": flight.package_id,
                    "booking_code": flight.package.booking_code,
                    "passenger_name": flight.package.passenger_name,
                    "passenger_lastname": flight.package.passenger_lastname,
                    "passenger_email": flight.package.passenger_email,
                    "passenger_phone": flight.package.passenger_phone,
                    "seat_numbers": flight.seat_numbers,
                    "total_passengers": pax_count
                })
            
            result.append({
                "id": first_flight.id,  # ID del primer vuelo para chequear
                "flight_ids": [f.id for f in flights_in_group],  # Todos los IDs
                "flight_number": group["flight_number"],
                "flight_iata": group["flight_iata"],
                "airline": group["airline"],
                "departure_datetime": group["departure_datetime"].isoformat(),
                "departure_airport": group["departure_airport"],
                "arrival_airport": group["arrival_airport"],
                "arrival_airport_name": group["arrival_airport_name"],
                "total_passengers": total_pax,
                "passengers": passengers,
                "last_checked": last_check.check_timestamp.isoformat() if last_check else None,
                "current_status": last_check.flight_status if last_check else "not_checked",
                "has_changes": last_check.has_changes if last_check else False,
                "change_severity": last_check.change_severity if last_check else None,
                "delay_minutes": last_check.departure_delay if last_check else 0,
                "departure_gate": last_check.departure_gate if last_check else None,
                "departure_terminal": last_check.departure_terminal if last_check else None,
                "ticket_id": last_check.ticket_id if last_check and last_check.ticket_created else None
            })
        
        logger.info("Upcoming flights retrieved (grouped)", count=len(result), total_flights=len(flights))
        return result
    
    def check_flight_on_demand(self, flight_id: int) -> Dict:
        """Chequea UN vuelo específico"""
        flight = self.db.query(PackageFlight).filter(PackageFlight.id == flight_id).first()
        
        if not flight:
            return {"error": "Flight not found"}
        
        # Extraer código IATA y fecha del vuelo
        flight_iata = flight.flight_iata or flight.flight_number
        flight_date = flight.departure_datetime.strftime('%Y-%m-%d') if flight.departure_datetime else None
        
        # Separar código de aerolínea y número de vuelo
        # Ejemplo: "AR1302" -> airline="AR", number="1302"
        airline_code = ''.join([c for c in flight_iata if c.isalpha()])
        flight_number = ''.join([c for c in flight_iata if c.isdigit()])
        
        logger.info("Checking flight", 
                   flight_id=flight_id, 
                   flight_iata=flight_iata,
                   airline_code=airline_code,
                   flight_number=flight_number,
                   flight_date=flight_date)
        
        # Consultar FlightAPI.io con fecha específica (CRÍTICO para precisión)
        api_data = self.api_client.get_flight_by_code(flight_number, airline_code, flight_date)
        
        if not api_data:
            logger.warning("Flight not found in API", flight_id=flight_id)
            return {
                "flight_id": flight_id,
                "status": "not_found_in_api",
                "message": "Vuelo no encontrado en API",
                "has_changes": False,
                "ticket_created": False
            }
        
        if not flight.flight_iata and api_data.get('flight_iata'):
            flight.flight_iata = api_data['flight_iata']
            self.db.commit()
        
        last_status = self.db.query(FlightStatusTracking).filter(
            FlightStatusTracking.flight_id == flight_id
        ).order_by(FlightStatusTracking.check_timestamp.desc()).first()
        
        changes = self._detect_changes(last_status, api_data) if last_status else None
        new_status = self._save_flight_status(flight, api_data, changes, "manual")
        
        if changes and changes.get('has_changes'):
            ticket = self._create_flight_change_ticket(flight, changes, new_status)
            new_status.ticket_id = ticket.id
            new_status.ticket_created = True
            
            notifications = self.notification_service.simulate_notifications(flight.package, changes)
            new_status.notifications_simulated = json.dumps(notifications)
            
            logger.info("Flight change detected", flight_id=flight_id, ticket_id=ticket.id)
        
        # IMPORTANTE: Hacer commit siempre, no solo cuando hay cambios
        self.db.commit()
        
        return {
            "flight_id": flight_id,
            "status": new_status.flight_status,
            "has_changes": changes.get('has_changes') if changes else False,
            "changes": changes,
            "severity": changes.get('severity') if changes else None,
            "ticket_created": new_status.ticket_created,
            "ticket_id": new_status.ticket_id
        }
    
    def check_all_upcoming_flights(self) -> Dict:
        """Chequea TODOS los vuelos próximos"""
        flights = self.get_upcoming_flights()
        
        results = {
            "total": len(flights),
            "checked": 0,
            "changes_detected": 0,
            "tickets_created": 0,
            "errors": 0,
            "timestamp": now_argentina().isoformat()
        }
        
        for flight_data in flights:
            try:
                result = self.check_flight_on_demand(flight_data["id"])
                results["checked"] += 1
                
                if result.get("has_changes"):
                    results["changes_detected"] += 1
                
                if result.get("ticket_created"):
                    results["tickets_created"] += 1
                    
            except Exception as e:
                logger.error("Error checking flight", flight_id=flight_data["id"], error=str(e))
                results["errors"] += 1
        
        logger.info("All flights checked", **results)
        return results
    
    def _detect_changes(self, old_status: FlightStatusTracking, new_data: Dict) -> Dict:
        """Detecta cambios entre estados"""
        changes = []
        severity = "low"
        
        new_status = new_data.get('flight_status')
        new_delay = new_data.get('departure', {}).get('delay') or 0
        
        # Cambio de estado crítico
        if old_status and old_status.flight_status != new_status:
            if new_status in ['cancelled', 'diverted', 'incident']:
                changes.append({
                    "type": "status_change",
                    "old": old_status.flight_status,
                    "new": new_status,
                    "message": f"⚠️ VUELO {new_status.upper()}"
                })
                severity = "critical"
        
        # Delay
        old_delay = old_status.departure_delay if old_status else 0
        if new_delay > old_delay:
            if new_delay >= 240:
                severity = "critical"
                msg = f"⚠️ DELAY CRÍTICO: {new_delay} min"
            elif new_delay >= 120:
                severity = "high"
                msg = f"⚠️ DELAY ALTO: {new_delay} min"
            elif new_delay >= 60:
                severity = "medium"
                msg = f"⏰ Delay: {new_delay} min"
            else:
                msg = f"⏰ Delay menor: {new_delay} min"
            
            changes.append({"type": "delay", "old": old_delay, "new": new_delay, "message": msg})
        
        # Cambio de gate
        new_gate = new_data.get('departure', {}).get('gate')
        if old_status and old_status.departure_gate and new_gate and old_status.departure_gate != new_gate:
            changes.append({
                "type": "gate_change",
                "old": old_status.departure_gate,
                "new": new_gate,
                "message": f"🚪 Cambio de puerta: {old_status.departure_gate} → {new_gate}"
            })
        
        return {
            "has_changes": len(changes) > 0,
            "changes": changes,
            "severity": severity,
            "flight_number": new_data.get('flight_iata')
        }
    
    def _save_flight_status(self, flight, api_data, changes, checked_by) -> FlightStatusTracking:
        """Guarda estado del vuelo"""
        dep = api_data.get('departure', {})
        arr = api_data.get('arrival', {})
        
        # Parsear fechas de FlightAPI.io (pueden venir en formato ISO, timestamp, "HH:MM, MMM DD" o None)
        def parse_datetime(dt_value):
            if not dt_value:
                return None
            try:
                # Si es un string, intentar diferentes formatos
                if isinstance(dt_value, str):
                    # Formato ISO
                    try:
                        return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
                    except:
                        pass
                    
                    # Formato FlightAPI: "11:20, Nov 06" o "18:15, Nov 06"
                    try:
                        from datetime import datetime as dt
                        # Agregar año actual
                        year = flight.departure_datetime.year if flight.departure_datetime else datetime.now().year
                        dt_with_year = f"{dt_value}, {year}"
                        return dt.strptime(dt_with_year, "%H:%M, %b %d, %Y")
                    except:
                        pass
                    
                # Si es un número (timestamp), convertir
                elif isinstance(dt_value, (int, float)):
                    return datetime.fromtimestamp(dt_value)
                    
                return None
            except Exception as e:
                logger.warning(f"Error parsing datetime: {dt_value}, error: {e}")
                return None
        
        status = FlightStatusTracking(
            flight_id=flight.id,
            checked_by=checked_by,
            flight_iata=api_data.get('flight_iata'),
            flight_number=api_data.get('flight_number'),
            airline_name=api_data.get('airline_iata'),
            flight_date=flight.departure_datetime.date() if flight.departure_datetime else None,
            flight_status=api_data.get('flight_status'),
            departure_airport=dep.get('airport'),
            departure_iata=dep.get('iata'),
            departure_terminal=dep.get('terminal'),
            departure_gate=dep.get('gate'),
            departure_scheduled=parse_datetime(dep.get('scheduled')),
            departure_estimated=parse_datetime(dep.get('estimated')),
            departure_delay=dep.get('delay') or 0,
            arrival_airport=arr.get('airport'),
            arrival_iata=arr.get('iata'),
            arrival_terminal=arr.get('terminal'),
            arrival_gate=arr.get('gate'),
            arrival_baggage=arr.get('baggage'),
            arrival_scheduled=parse_datetime(arr.get('scheduled')),
            arrival_estimated=parse_datetime(arr.get('estimated')),
            arrival_delay=arr.get('delay') or 0,
            has_changes=changes.get('has_changes') if changes else False,
            changes_detected=json.dumps(changes) if changes else None,
            change_severity=changes.get('severity') if changes else 'low',
            raw_api_response=json.dumps(api_data)
        )
        
        self.db.add(status)
        self.db.flush()
        return status
    
    def _create_flight_change_ticket(self, flight, changes, status) -> SupportTicket:
        """Crea ticket por cambio de vuelo"""
        package = flight.package
        severity = changes.get('severity', 'low')
        
        priority_map = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}
        
        ticket = SupportTicket(
            session_id=f"flight_monitor_{flight.id}_{now_argentina().timestamp()}",
            package_id=package.id,
            ticket_category="flight",
            priority=priority_map.get(severity, "medium"),
            status="open",
            description=f"⚠️ Cambio en vuelo {flight.flight_number} - {package.booking_code}",
            provider_id=flight.provider_id,
            has_escalated_issues=True,
            escalated_issues_count=1
        )
        
        self.db.add(ticket)
        self.db.flush()
        
        # Agregar interaction
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type="system_event",
            message=self._build_ticket_message(flight, changes),
            interaction_category="flight",
            requires_escalation=True,
            auto_resolved=False,
            sequence_number=1
        )
        
        self.db.add(interaction)
        self.db.flush()
        
        return ticket
    
    def _build_ticket_message(self, flight, changes) -> str:
        """Construye mensaje del ticket"""
        msg = f"Cambio detectado en vuelo {flight.flight_number}\n\n"
        msg += f"Paquete: {flight.package.booking_code}\n"
        msg += f"Pasajero: {flight.package.passenger_name} {flight.package.passenger_lastname}\n\n"
        msg += "Cambios:\n"
        
        for change in changes.get('changes', []):
            msg += f"• {change.get('message')}\n"
        
        msg += "\n✅ Notificaciones simuladas enviadas a pasajero, hotel y transfer"
        return msg
