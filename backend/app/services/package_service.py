"""
Servicio para gestión de paquetes turísticos y reservas
"""
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Optional
from app.models.postsale import (
    TourPackage, SoldPackage, PackagePassenger, PackageFlight,
    PackageAccommodation, PackageTransfer, PackageActivity, PackageItinerary
)
from app.models.provider import Provider


class PackageService:
    """Servicio para gestión de paquetes"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_packages_grouped(self) -> List[Dict]:
        """
        Obtiene paquetes turísticos agrupados con sus reservas y pasajeros
        
        Returns:
            Lista de paquetes con estructura:
            {
                "tour_package": {...},
                "reservations": [
                    {
                        "sold_package": {...},
                        "passengers": [...]
                    }
                ]
            }
        """
        # Obtener todos los paquetes turísticos
        tour_packages = self.db.query(TourPackage).filter_by(is_active=True).all()
        
        result = []
        
        for tour_pkg in tour_packages:
            # Obtener reservas de este paquete
            reservations = self.db.query(SoldPackage).filter_by(
                tour_package_id=tour_pkg.id
            ).all()
            
            reservations_data = []
            for reservation in reservations:
                # Obtener pasajeros de esta reserva
                passengers = self.db.query(PackagePassenger).filter_by(
                    package_id=reservation.id
                ).order_by(
                    PackagePassenger.is_primary.desc(),  # Principal primero
                    PackagePassenger.id
                ).all()
                
                passengers_data = []
                for passenger in passengers:
                    passengers_data.append({
                        "id": passenger.id,
                        "is_primary": passenger.is_primary,
                        "relationship_to_primary": passenger.relationship_to_primary,
                        "passenger_type": passenger.passenger_type,
                        "first_name": passenger.first_name,
                        "last_name": passenger.last_name,
                        "full_name": f"{passenger.first_name} {passenger.last_name}",
                        "birth_date": passenger.birth_date.isoformat() if passenger.birth_date else None,
                        "gender": passenger.gender,
                        "document_type": passenger.document_type,
                        "document_number": passenger.document_number,
                        "nationality": passenger.nationality,
                        "email": passenger.email,
                        "phone_country_code": passenger.phone_country_code,
                        "phone_number": passenger.phone_number,
                        "phone_full": f"{passenger.phone_country_code} {passenger.phone_number}" if passenger.phone_country_code and passenger.phone_number else None
                    })
                
                reservations_data.append({
                    "sold_package": {
                        "id": reservation.id,
                        "booking_code": reservation.booking_code,
                        "package_name": reservation.package_name,
                        "departure_date": reservation.departure_date.isoformat() if reservation.departure_date else None,
                        "return_date": reservation.return_date.isoformat() if reservation.return_date else None,
                        "total_passengers": reservation.total_passengers,
                        "total_price": float(reservation.total_price) if reservation.total_price else 0,
                        "currency": reservation.currency,
                        "trip_status": reservation.trip_status,
                        "payment_status": reservation.payment_status
                    },
                    "passengers": passengers_data,
                    "passenger_count": len(passengers_data)
                })
            
            result.append({
                "tour_package": tour_pkg.to_dict(),
                "reservations": reservations_data,
                "reservation_count": len(reservations_data),
                "total_passengers": sum(r["passenger_count"] for r in reservations_data)
            })
        
        return result
    
    def get_reservation_complete(self, booking_code: str) -> Optional[Dict]:
        """
        Obtiene información completa de una reserva
        
        Args:
            booking_code: Código de reserva (ej: BK-2025-200)
            
        Returns:
            Diccionario con toda la información de la reserva
        """
        # Obtener reserva
        reservation = self.db.query(SoldPackage).filter_by(
            booking_code=booking_code
        ).first()
        
        if not reservation:
            return None
        
        # Pasajeros
        passengers = self.db.query(PackagePassenger).filter_by(
            package_id=reservation.id
        ).order_by(
            PackagePassenger.is_primary.desc(),
            PackagePassenger.id
        ).all()
        
        passengers_data = []
        for p in passengers:
            passengers_data.append({
                "id": p.id,
                "is_primary": p.is_primary,
                "relationship_to_primary": p.relationship_to_primary,
                "passenger_type": p.passenger_type,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "full_name": f"{p.first_name} {p.last_name}",
                "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                "gender": p.gender,
                "document_type": p.document_type,
                "document_number": p.document_number,
                "nationality": p.nationality,
                "email": p.email,
                "phone_country_code": p.phone_country_code,
                "phone_number": p.phone_number,
                "phone_full": f"{p.phone_country_code} {p.phone_number}" if p.phone_country_code and p.phone_number else None,
                "emergency_contact_name": p.emergency_contact_name,
                "emergency_contact_phone": p.emergency_contact_phone,
                "dietary_restrictions": p.dietary_restrictions,
                "medical_conditions": p.medical_conditions
            })
        
        # Vuelos con proveedores
        flights = self.db.query(PackageFlight).options(
            joinedload(PackageFlight.provider),
            joinedload(PackageFlight.shared_flight)
        ).filter_by(package_id=reservation.id).order_by(
            PackageFlight.flight_sequence
        ).all()
        
        flights_data = []
        for f in flights:
            flight_dict = {
                "id": f.id,
                "flight_type": f.flight_type,
                "airline": f.airline,
                "flight_number": f.flight_number,
                "flight_iata": f.flight_iata,
                "departure_airport_code": f.departure_airport_code,
                "departure_airport_name": f.departure_airport_name,
                "departure_datetime": f.departure_datetime.isoformat() if f.departure_datetime else None,
                "departure_terminal": f.departure_terminal,
                "arrival_airport_code": f.arrival_airport_code,
                "arrival_airport_name": f.arrival_airport_name,
                "arrival_datetime": f.arrival_datetime.isoformat() if f.arrival_datetime else None,
                "arrival_terminal": f.arrival_terminal,
                "seat_numbers": f.seat_numbers,
                "cabin_class": f.cabin_class,
                "baggage_allowance": f.baggage_allowance,
                "booking_reference": f.booking_reference,
                "flight_status": f.flight_status
            }
            
            if f.provider:
                flight_dict["provider"] = f.provider.to_dict()
            
            flights_data.append(flight_dict)
        
        # Hoteles con proveedores
        hotels = self.db.query(PackageAccommodation).options(
            joinedload(PackageAccommodation.provider)
        ).filter_by(package_id=reservation.id).order_by(
            PackageAccommodation.checkin_date
        ).all()
        
        hotels_data = []
        for h in hotels:
            hotel_dict = {
                "id": h.id,
                "hotel_name": h.hotel_name,
                "hotel_category": h.hotel_category,
                "city": h.city,
                "address": h.address,
                "postal_code": h.postal_code,
                "hotel_phone": h.hotel_phone,
                "hotel_email": h.hotel_email,
                "hotel_website": h.hotel_website,
                "google_maps_url": h.google_maps_url,
                "booking_confirmation": h.booking_confirmation,
                "checkin_date": h.checkin_date.isoformat() if h.checkin_date else None,
                "checkout_date": h.checkout_date.isoformat() if h.checkout_date else None,
                "nights_count": h.nights_count,
                "room_type": h.room_type,
                "bed_configuration": h.bed_configuration,
                "meal_plan": h.meal_plan,
                "amenities": h.amenities,
                "checkin_time": h.checkin_time.strftime("%H:%M") if h.checkin_time else None,
                "checkout_time": h.checkout_time.strftime("%H:%M") if h.checkout_time else None
            }
            
            if h.provider:
                hotel_dict["provider"] = h.provider.to_dict()
            
            hotels_data.append(hotel_dict)
        
        # Traslados con proveedores
        transfers = self.db.query(PackageTransfer).options(
            joinedload(PackageTransfer.provider)
        ).filter_by(package_id=reservation.id).order_by(
            PackageTransfer.transfer_date,
            PackageTransfer.pickup_time
        ).all()
        
        transfers_data = []
        for t in transfers:
            transfer_dict = {
                "id": t.id,
                "transfer_type": t.transfer_type,
                "transfer_date": t.transfer_date.isoformat() if t.transfer_date else None,
                "pickup_time": t.pickup_time.strftime("%H:%M") if t.pickup_time else None,
                "estimated_arrival_time": t.estimated_arrival_time.strftime("%H:%M") if t.estimated_arrival_time else None,
                "pickup_location": t.pickup_location,
                "pickup_address": t.pickup_address,
                "pickup_instructions": t.pickup_instructions,
                "dropoff_location": t.dropoff_location,
                "dropoff_address": t.dropoff_address,
                "provider_name": t.provider_name,
                "provider_phone": t.provider_phone,
                "vehicle_type": t.vehicle_type,
                "vehicle_capacity": t.vehicle_capacity,
                "booking_reference": t.booking_reference,
                "transfer_status": t.transfer_status
            }
            
            if t.provider:
                transfer_dict["provider"] = t.provider.to_dict()
            
            transfers_data.append(transfer_dict)
        
        # Actividades con proveedores
        activities = self.db.query(PackageActivity).options(
            joinedload(PackageActivity.provider)
        ).filter_by(package_id=reservation.id).order_by(
            PackageActivity.activity_date,
            PackageActivity.start_time
        ).all()
        
        activities_data = []
        for a in activities:
            activity_dict = {
                "id": a.id,
                "activity_name": a.activity_name,
                "activity_type": a.activity_type,
                "city": a.city,
                "activity_date": a.activity_date.isoformat() if a.activity_date else None,
                "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,
                "end_time": a.end_time.strftime("%H:%M") if a.end_time else None,
                "duration_hours": float(a.duration_hours) if a.duration_hours else None,
                "meeting_point": a.meeting_point,
                "meeting_point_address": a.meeting_point_address,
                "description": a.description,
                "included_services": a.included_services,
                "not_included": a.not_included,
                "booking_reference": a.booking_reference,
                "activity_status": a.activity_status
            }
            
            if a.provider:
                activity_dict["provider"] = a.provider.to_dict()
            
            activities_data.append(activity_dict)
        
        # Construir respuesta completa
        return {
            "reservation": {
                "id": reservation.id,
                "booking_code": reservation.booking_code,
                "package_name": reservation.package_name,
                "destination_country": reservation.destination_country,
                "destination_cities": reservation.destination_cities,
                "departure_date": reservation.departure_date.isoformat() if reservation.departure_date else None,
                "return_date": reservation.return_date.isoformat() if reservation.return_date else None,
                "duration_days": reservation.duration_days,
                "total_passengers": reservation.total_passengers,
                "total_price": float(reservation.total_price) if reservation.total_price else 0,
                "currency": reservation.currency,
                "trip_status": reservation.trip_status,
                "payment_status": reservation.payment_status
            },
            "passengers": passengers_data,
            "flights": flights_data,
            "hotels": hotels_data,
            "transfers": transfers_data,
            "activities": activities_data
        }
