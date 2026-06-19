"""
Servicio de Generación de Vouchers en PDF
Genera documentos de viaje profesionales para clientes
"""
from xhtml2pdf import pisa
from jinja2 import Template
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from io import BytesIO
from sqlalchemy.orm import Session
from app.utils.timezone_utils import now_argentina
from app.models.postsale import SoldPackage
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class VoucherService:
    """Servicio para generar vouchers en PDF"""
    
    def __init__(self):
        # Rutas
        self.base_dir = Path(__file__).parent.parent.parent
        self.template_path = self.base_dir / "docsbase" / "Vouchers" / "voucher_template.html"
        self.output_dir = self.base_dir / "vouchers"
        
        # Crear directorio de salida si no existe
        self.output_dir.mkdir(exist_ok=True)
        
        logger.info("VoucherService initialized",
                   template_path=str(self.template_path),
                   output_dir=str(self.output_dir))
    
    async def generate_voucher_pdf(
        self, 
        booking_code: str, 
        db: Session
    ) -> str:
        """
        Genera PDF del voucher para una reserva
        
        Args:
            booking_code: Código de reserva (ej: BK-2025-001)
            db: Sesión de base de datos
            
        Returns:
            str: Ruta del archivo PDF generado
            
        Raises:
            ValueError: Si la reserva no existe
            Exception: Si hay error en la generación
        """
        try:
            logger.info("Starting voucher generation",
                       booking_code=booking_code)
            
            # 1. Obtener datos de la reserva
            voucher_data = await self.get_voucher_data(booking_code, db)
            
            if not voucher_data:
                raise ValueError(f"Reserva {booking_code} no encontrada")
            
            # 2. Renderizar HTML con datos
            html_content = self.render_html_template(voucher_data)
            
            # 3. Generar PDF
            pdf_path = self.output_dir / f"{booking_code}.pdf"
            
            # Convertir HTML a PDF usando xhtml2pdf
            with open(pdf_path, "wb") as pdf_file:
                pisa_status = pisa.CreatePDF(
                    html_content.encode('utf-8'),
                    dest=pdf_file,
                    encoding='utf-8'
                )
            
            if pisa_status.err:
                raise Exception(f"Error generating PDF: {pisa_status.err}")
            
            logger.info("Voucher PDF generated successfully",
                       booking_code=booking_code,
                       pdf_path=str(pdf_path),
                       file_size_kb=pdf_path.stat().st_size // 1024)
            
            return str(pdf_path)
            
        except Exception as e:
            logger.error("Error generating voucher PDF",
                        booking_code=booking_code,
                        error=str(e))
            raise
    
    async def get_voucher_data(
        self, 
        booking_code: str, 
        db: Session
    ) -> Optional[Dict]:
        """
        Obtiene todos los datos necesarios para el voucher
        
        Args:
            booking_code: Código de reserva
            db: Sesión de base de datos
            
        Returns:
            Dict con todos los datos del voucher o None si no existe
        """
        try:
            # Buscar reserva con todas las relaciones
            package = db.query(SoldPackage).filter(
                SoldPackage.booking_code == booking_code
            ).first()
            
            if not package:
                logger.warning("Package not found for voucher",
                             booking_code=booking_code)
                return None
            
            # Construir datos del voucher
            voucher_data = {
                # Identificación
                "voucher_number": booking_code,
                "issue_date": now_argentina().strftime("%d de %B, %Y"),
                "status": self._get_status_text(package.payment_status, package.trip_status),
                
                # Paquete
                "package_name": package.package_name,
                "destination": f"{package.destination_cities}, {package.destination_country}" if package.destination_cities else package.destination_country,
                "duration": f"{package.duration_days} días / {package.duration_days - 1} noches",
                
                # Pasajero principal
                "passenger_name": f"{package.passenger_name} {package.passenger_lastname}",
                "passenger_document": f"{package.passenger_document_type}: {package.passenger_document_number}" if package.passenger_document_type else "N/A",
                "passenger_email": package.passenger_email,
                "passenger_phone": package.passenger_phone,
                "total_passengers": package.total_passengers,
                
                # Pasajeros adicionales
                "additional_passengers": self._format_passengers(package.passengers),
                
                # Fechas
                "departure_date": package.departure_date.strftime("%d de %B, %Y") if package.departure_date else "N/A",
                "return_date": package.return_date.strftime("%d de %B, %Y") if package.return_date else "N/A",
                
                # Vuelos
                "flights": self._format_flights(package.flights),
                "has_flights": len(package.flights) > 0,
                
                # Alojamiento
                "accommodations": self._format_accommodations(package.accommodations),
                "has_accommodations": len(package.accommodations) > 0,
                
                # Traslados
                "transfers": self._format_transfers(package.transfers),
                "has_transfers": len(package.transfers) > 0,
                
                # Actividades
                "activities": self._format_activities(package.activities),
                "has_activities": len(package.activities) > 0,
                
                # Itinerario
                "itinerary": self._format_itinerary(package.itinerary),
                "has_itinerary": len(package.itinerary) > 0,
                
                # Servicios incluidos/no incluidos
                "services_included": self._get_services_included(package),
                "services_not_included": self._get_services_not_included(),
                
                # Precio
                "total_price": f"{package.currency} {float(package.total_price):,.2f}",
                "payment_method": self._get_payment_method(package.payment_status),
                "payment_date": package.created_at.strftime("%d/%m/%Y") if package.created_at else "N/A",
                
                # Punto de encuentro (del primer vuelo)
                "meeting_point": self._get_meeting_point(package.flights),
                "has_meeting_point": len(package.flights) > 0,
                
                # Contacto de emergencia
                "emergency_contact": {
                    "whatsapp": "+54 9 341 888-9999",
                    "email": "emergencias@auratravel.com",
                    "phone": "+54 341 555-0000"
                }
            }
            
            logger.info("Voucher data prepared",
                       booking_code=booking_code,
                       has_flights=voucher_data["has_flights"],
                       has_accommodations=voucher_data["has_accommodations"],
                       total_passengers=voucher_data["total_passengers"])
            
            return voucher_data
            
        except Exception as e:
            logger.error("Error getting voucher data",
                        booking_code=booking_code,
                        error=str(e))
            raise
    
    def render_html_template(self, data: Dict) -> str:
        """
        Renderiza el template HTML con los datos
        
        Args:
            data: Diccionario con datos del voucher
            
        Returns:
            str: HTML renderizado
        """
        try:
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            template = Template(template_content)
            rendered_html = template.render(**data)
            
            logger.debug("HTML template rendered",
                        template_size=len(template_content),
                        rendered_size=len(rendered_html))
            
            return rendered_html
            
        except Exception as e:
            logger.error("Error rendering HTML template",
                        error=str(e))
            raise
    
    def _get_status_text(self, payment_status: str, trip_status: str) -> str:
        """Obtiene texto del estado del voucher"""
        if payment_status == "paid" and trip_status == "confirmed":
            return "✓ CONFIRMADO Y PAGADO"
        elif payment_status == "paid":
            return "✓ PAGADO"
        elif trip_status == "confirmed":
            return "✓ CONFIRMADO"
        else:
            return "⏳ PENDIENTE"
    
    def _format_passengers(self, passengers) -> str:
        """Formatea lista de pasajeros adicionales"""
        if not passengers or len(passengers) <= 1:
            return "No hay pasajeros adicionales"
        
        # Excluir pasajero principal
        additional = [p for p in passengers if not p.is_primary]
        
        if not additional:
            return "No hay pasajeros adicionales"
        
        return ", ".join([
            f"{p.first_name} {p.last_name}" + 
            (f" ({self._translate_passenger_type(p.passenger_type)})" if p.passenger_type and p.passenger_type != "adult" else "")
            for p in additional
        ])
    
    def _translate_passenger_type(self, passenger_type: str) -> str:
        """Traduce tipo de pasajero"""
        translations = {
            "child": "menor",
            "infant": "bebé",
            "adult": "adulto"
        }
        return translations.get(passenger_type, passenger_type)
    
    def _format_flights(self, flights) -> List[Dict]:
        """Formatea información de vuelos"""
        if not flights:
            return []
        
        return [{
            "airline": f.airline or "N/A",
            "flight_number": f.flight_number or "N/A",
            "route": f"{f.departure_airport_name or f.departure_airport_code} → {f.arrival_airport_name or f.arrival_airport_code}",
            "departure": f.departure_datetime.strftime('%d/%m/%Y %H:%M') if f.departure_datetime else "N/A",
            "arrival": f.arrival_datetime.strftime('%d/%m/%Y %H:%M') if f.arrival_datetime else "N/A",
            "class": f.cabin_class or "Económica",
            "baggage": f.baggage_allowance or "1 valija de 23kg"
        } for f in flights]
    
    def _format_accommodations(self, accommodations) -> List[Dict]:
        """Formatea información de alojamiento"""
        if not accommodations:
            return []
        
        return [{
            "hotel_name": a.hotel_name or "N/A",
            "category": f"{a.hotel_category}★" if a.hotel_category else "N/A",
            "check_in": a.checkin_date.strftime("%d/%m/%Y") if a.checkin_date else "N/A",
            "check_out": a.checkout_date.strftime("%d/%m/%Y") if a.checkout_date else "N/A",
            "nights": a.nights_count or 0,
            "room_type": a.room_type or "Estándar",
            "meal_plan": a.meal_plan or "Sin comidas",
            "address": a.address or "N/A"
        } for a in accommodations]
    
    def _format_transfers(self, transfers) -> List[Dict]:
        """Formatea información de traslados"""
        if not transfers:
            return []
        
        return [{
            "type": self._translate_transfer_type(t.transfer_type),
            "from": t.pickup_location or "N/A",
            "to": t.dropoff_location or "N/A",
            "time": t.pickup_time or "N/A",
            "vehicle": t.vehicle_type or "Vehículo estándar"
        } for t in transfers]
    
    def _translate_transfer_type(self, transfer_type: str) -> str:
        """Traduce tipo de traslado"""
        translations = {
            "airport-hotel": "Aeropuerto → Hotel",
            "hotel-airport": "Hotel → Aeropuerto",
            "hotel-hotel": "Hotel → Hotel",
            "excursion": "Excursión"
        }
        return translations.get(transfer_type, transfer_type)
    
    def _format_activities(self, activities) -> List[Dict]:
        """Formatea información de actividades"""
        if not activities:
            return []
        
        return [{
            "name": a.activity_name or "N/A",
            "type": a.activity_type or "Excursión",
            "date": a.activity_date.strftime("%d/%m/%Y") if a.activity_date else "N/A",
            "time": a.start_time or "N/A",
            "duration": f"{a.duration_hours} horas" if a.duration_hours else "N/A",
            "description": a.description or ""
        } for a in activities]
    
    def _format_itinerary(self, itinerary) -> List[Dict]:
        """Formatea itinerario día a día"""
        if not itinerary:
            return []
        
        return [{
            "day": i.day_number,
            "date": i.itinerary_date.strftime("%d/%m/%Y") if i.itinerary_date else "N/A",
            "title": i.day_title or f"Día {i.day_number}",
            "city": i.city or "",
            "activities": self._combine_day_activities(i)
        } for i in sorted(itinerary, key=lambda x: x.day_number)]
    
    def _combine_day_activities(self, day) -> str:
        """Combina actividades del día"""
        activities = []
        
        if day.morning_activities:
            activities.append(f"Mañana: {day.morning_activities}")
        if day.afternoon_activities:
            activities.append(f"Tarde: {day.afternoon_activities}")
        if day.evening_activities:
            activities.append(f"Noche: {day.evening_activities}")
        
        return " | ".join(activities) if activities else "Día libre"
    
    def _get_services_included(self, package) -> List[str]:
        """Obtiene lista de servicios incluidos"""
        services = []
        
        # Basado en lo que tiene el paquete
        if package.flights:
            services.append("Vuelos ida y vuelta")
        
        if package.accommodations:
            services.append(f"Alojamiento ({len(package.accommodations)} hoteles)")
        
        if package.transfers:
            services.append("Traslados aeropuerto-hotel-aeropuerto")
        
        if package.activities:
            services.append(f"Excursiones y actividades ({len(package.activities)})")
        
        # Servicios estándar
        services.extend([
            "Seguro de asistencia al viajero",
            "Impuestos y tasas aeroportuarias",
            "Asistencia 24/7 durante el viaje"
        ])
        
        return services
    
    def _get_services_not_included(self) -> List[str]:
        """Obtiene lista de servicios NO incluidos"""
        return [
            "Gastos personales y propinas",
            "Excursiones opcionales no mencionadas",
            "Documentación (pasaporte, visas si aplica)",
            "Comidas y bebidas no especificadas"
        ]
    
    def _get_meeting_point(self, flights) -> Dict:
        """Obtiene punto de encuentro del primer vuelo"""
        if not flights:
            return {}
        
        # Ordenar por fecha de salida
        sorted_flights = sorted(flights, key=lambda x: x.departure_datetime if x.departure_datetime else datetime.max)
        
        if not sorted_flights:
            return {}
        
        first_flight = sorted_flights[0]
        
        return {
            "airport": first_flight.departure_airport_name or first_flight.departure_airport_code or "N/A",
            "date": first_flight.departure_datetime.strftime("%d/%m/%Y") if first_flight.departure_datetime else "N/A",
            "time": first_flight.departure_datetime.strftime("%H:%M") if first_flight.departure_datetime else "N/A",
            "airline": first_flight.airline or "N/A",
            "flight": first_flight.flight_number or "N/A"
        }
    
    def _get_payment_method(self, payment_status: str) -> str:
        """Obtiene método de pago"""
        if payment_status == "paid":
            return "Transferencia bancaria"
        elif payment_status == "partial":
            return "Pago parcial"
        else:
            return "Pendiente"


# Instancia global del servicio
voucher_service = VoucherService()
