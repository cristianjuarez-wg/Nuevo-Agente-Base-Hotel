"""
Modelos de Base de Datos - Módulo Post-Venta
Gestión de paquetes vendidos, tickets de soporte y sesiones
"""
from sqlalchemy import Column, Integer, String, Text, Date, Time, DateTime, Numeric, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, List, Optional
from app.models.database import Base
from app.utils.timezone_utils import now_argentina

# Import necesario para las relaciones con Provider
# Importación tardía para evitar imports circulares
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.provider import Provider


class TourPackage(Base):
    """Paquete turístico base (plantilla/producto)"""
    __tablename__ = "tour_packages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identificación
    package_code = Column(String(50), unique=True, nullable=False, index=True)  # "EUR-MED-001"
    package_name = Column(String(255), nullable=False)  # "Conociendo Europa Medieval"
    description = Column(Text, nullable=True)
    short_description = Column(Text, nullable=True)
    
    # Itinerario base
    countries = Column(JSON, nullable=True)  # ["España", "Francia", "Italia"]
    cities = Column(JSON, nullable=True)  # ["Madrid", "París", "Roma"]
    duration_days = Column(Integer, nullable=False)
    
    # Precios base
    base_price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default='USD')
    price_per_person = Column(Boolean, default=True)
    
    # Categorización
    category = Column(String(50), nullable=True)  # "cultural", "aventura", "relax", "familiar"
    season = Column(String(20), nullable=True)  # "verano", "invierno", "todo_año"
    difficulty_level = Column(String(20), nullable=True)  # "easy", "moderate", "challenging"
    
    # Capacidad
    min_passengers = Column(Integer, default=1)
    max_passengers = Column(Integer, nullable=True)
    
    # Inclusiones base (JSON)
    includes = Column(JSON, nullable=True)  # ["vuelos", "hoteles", "desayunos", "traslados"]
    excludes = Column(JSON, nullable=True)  # ["almuerzos", "cenas", "propinas"]
    
    # Highlights
    highlights = Column(JSON, nullable=True)  # ["Torre Eiffel", "Coliseo Romano"]
    
    # Vector store reference
    vector_doc_id = Column(String(100), nullable=True)  # ID en la base vectorial
    
    # Estado
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=now_argentina)
    updated_at = Column(DateTime, default=now_argentina, onupdate=now_argentina)
    created_by = Column(String(100), nullable=True)
    
    # Relationships
    sold_packages = relationship("SoldPackage", back_populates="tour_package")
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "package_code": self.package_code,
            "package_name": self.package_name,
            "description": self.description,
            "countries": self.countries,
            "cities": self.cities,
            "duration_days": self.duration_days,
            "base_price": float(self.base_price) if self.base_price else 0,
            "currency": self.currency,
            "category": self.category,
            "is_active": self.is_active
        }


class SoldPackage(Base):
    """Reserva/Voucher de un paquete turístico"""
    __tablename__ = "sold_packages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 🆕 Relación con paquete turístico base
    tour_package_id = Column(Integer, ForeignKey('tour_packages.id'), nullable=True)  # Nullable para compatibilidad
    
    lead_id = Column(Integer, nullable=True)  # Sin FK por ahora, solo referencia
    
    # Información del Paquete (mantener para compatibilidad, pero puede venir de tour_package)
    package_name = Column(String(255), nullable=False)
    destination_country = Column(String(100), nullable=False)
    destination_cities = Column(Text, nullable=True)
    package_type = Column(String(50), nullable=True)
    duration_days = Column(Integer, nullable=False)
    
    # Fechas
    departure_date = Column(Date, nullable=False)
    return_date = Column(Date, nullable=False)
    
    # Comercial
    total_price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default='USD')
    payment_status = Column(String(50), nullable=True)
    booking_code = Column(String(50), unique=True, nullable=False, index=True)
    
    # Pasajero Principal
    passenger_name = Column(String(100), nullable=False)
    passenger_lastname = Column(String(100), nullable=False)
    passenger_email = Column(String(255), nullable=False, index=True)
    passenger_phone = Column(String(50), nullable=False, index=True)
    passenger_document_type = Column(String(20), nullable=True)
    passenger_document_number = Column(String(50), nullable=True)
    
    total_passengers = Column(Integer, default=1)
    trip_status = Column(String(50), default='confirmed')
    special_requirements = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Visión 360°: vínculo con el Contact unificado del cliente
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True)

    created_at = Column(DateTime, default=now_argentina)
    updated_at = Column(DateTime, default=now_argentina, onupdate=now_argentina)
    sold_by = Column(String(100), nullable=True)

    # Relationships
    tour_package = relationship("TourPackage", back_populates="sold_packages")  # 🆕 NUEVO
    passengers = relationship("PackagePassenger", back_populates="package", cascade="all, delete-orphan")
    flights = relationship("PackageFlight", back_populates="package", cascade="all, delete-orphan")
    accommodations = relationship("PackageAccommodation", back_populates="package", cascade="all, delete-orphan")
    transfers = relationship("PackageTransfer", back_populates="package", cascade="all, delete-orphan")
    activities = relationship("PackageActivity", back_populates="package", cascade="all, delete-orphan")
    documents = relationship("PackageDocument", back_populates="package", cascade="all, delete-orphan")
    itinerary = relationship("PackageItinerary", back_populates="package", cascade="all, delete-orphan")
    tickets = relationship("SupportTicket", back_populates="package", cascade="all, delete-orphan")
    sessions = relationship("PostSaleSession", back_populates="package", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict:
        # Obtener lista de pasajeros
        passengers_list = []
        for passenger in self.passengers:
            passengers_list.append({
                "id": passenger.id,
                "first_name": passenger.first_name,
                "last_name": passenger.last_name,
                "full_name": f"{passenger.first_name} {passenger.last_name}",
                "is_primary": passenger.is_primary,
                "document_type": passenger.document_type,
                "document_number": passenger.document_number,
                "nationality": passenger.nationality,
                "email": passenger.email,
                "phone": f"{passenger.phone_country_code or ''} {passenger.phone_number or ''}".strip() if passenger.phone_number else None,
                "birth_date": passenger.birth_date.isoformat() if passenger.birth_date else None
            })
        
        return {
            "id": self.id,
            "booking_code": self.booking_code,
            "package_name": self.package_name,
            "destination_country": self.destination_country,
            "destination_cities": self.destination_cities,
            "passenger_name": f"{self.passenger_name} {self.passenger_lastname}",
            "departure_date": self.departure_date.isoformat() if self.departure_date else None,
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "duration_days": self.duration_days,
            "trip_status": self.trip_status,
            "total_price": float(self.total_price) if self.total_price else 0,
            "currency": self.currency,
            "total_passengers": self.total_passengers,
            "passengers": passengers_list  # Lista completa de pasajeros
        }


class PackagePassenger(Base):
    """Pasajero en una reserva (principal o secundario)"""
    __tablename__ = "package_passengers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    # 🆕 Tipo de pasajero y relación
    is_primary = Column(Boolean, default=False)  # 🆕 NUEVO: Indica si es el titular
    relationship_to_primary = Column(String(50), nullable=True)  # 🆕 NUEVO: "spouse", "child", "friend", "parent"
    
    passenger_type = Column(String(20), nullable=True)  # "adult", "child", "infant"
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    birth_date = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    
    # Documentación
    document_type = Column(String(20), nullable=True)  # "DNI", "Passport", "ID"
    document_number = Column(String(50), nullable=True, index=True)  # 🆕 Agregado índice
    document_expiry = Column(Date, nullable=True)
    nationality = Column(String(50), nullable=True)
    
    # 🆕 CONTACTO (NUEVO - CRÍTICO)
    email = Column(String(255), nullable=True, index=True)  # 🆕 NUEVO
    phone_country_code = Column(String(5), nullable=True)  # 🆕 NUEVO: "+54", "+1", "+34"
    phone_number = Column(String(50), nullable=True, index=True)  # 🆕 NUEVO
    
    # Emergencia
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(50), nullable=True)
    
    # Preferencias y necesidades
    dietary_restrictions = Column(Text, nullable=True)
    medical_conditions = Column(Text, nullable=True)
    special_assistance = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="passengers")


class SharedFlight(Base):
    """Vuelo compartido por múltiples reservas (OPCIONAL)"""
    __tablename__ = "shared_flights"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identificación del vuelo
    airline = Column(String(100), nullable=False)
    airline_code = Column(String(10), nullable=False)  # "AR", "IB", "AA"
    flight_number = Column(String(20), nullable=False)
    flight_iata = Column(String(10), nullable=False, index=True)  # "AR1302"
    
    # Aeropuertos
    departure_airport_code = Column(String(10), nullable=False)
    departure_airport_name = Column(String(200), nullable=True)
    departure_terminal = Column(String(10), nullable=True)
    departure_datetime = Column(DateTime, nullable=False, index=True)
    
    arrival_airport_code = Column(String(10), nullable=False)
    arrival_airport_name = Column(String(200), nullable=True)
    arrival_terminal = Column(String(10), nullable=True)
    arrival_datetime = Column(DateTime, nullable=False)
    
    # Duración y clase
    flight_duration_minutes = Column(Integer, nullable=True)
    aircraft_type = Column(String(50), nullable=True)
    
    # Capacidad (para control de disponibilidad)
    total_seats = Column(Integer, nullable=True)
    available_seats = Column(Integer, nullable=True)
    
    # Estado del vuelo compartido
    flight_status = Column(String(50), default='scheduled')  # scheduled, active, landed, cancelled
    
    # Metadata
    created_at = Column(DateTime, default=now_argentina)
    updated_at = Column(DateTime, default=now_argentina, onupdate=now_argentina)
    
    # Relationships
    package_flights = relationship("PackageFlight", back_populates="shared_flight")
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "flight_iata": self.flight_iata,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "departure_airport": self.departure_airport_code,
            "departure_datetime": self.departure_datetime.isoformat() if self.departure_datetime else None,
            "arrival_airport": self.arrival_airport_code,
            "arrival_datetime": self.arrival_datetime.isoformat() if self.arrival_datetime else None,
            "total_seats": self.total_seats,
            "available_seats": self.available_seats,
            "flight_status": self.flight_status
        }


class PackageFlight(Base):
    """Vuelo asignado a una reserva específica"""
    __tablename__ = "package_flights"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    # 🆕 Relación con vuelo compartido (OPCIONAL)
    shared_flight_id = Column(Integer, ForeignKey('shared_flights.id'), nullable=True)
    
    flight_type = Column(String(20), nullable=True)  # "outbound", "return", "connection"
    flight_sequence = Column(Integer, nullable=True)
    airline = Column(String(100), nullable=False)
    flight_number = Column(String(20), nullable=False)
    booking_reference = Column(String(50), nullable=True)
    
    departure_airport_code = Column(String(10), nullable=False)
    departure_airport_name = Column(String(200), nullable=True)
    departure_terminal = Column(String(10), nullable=True)
    departure_datetime = Column(DateTime, nullable=False)
    
    arrival_airport_code = Column(String(10), nullable=False)
    arrival_airport_name = Column(String(200), nullable=True)
    arrival_terminal = Column(String(10), nullable=True)
    arrival_datetime = Column(DateTime, nullable=False)
    
    flight_duration_minutes = Column(Integer, nullable=True)
    seat_numbers = Column(Text, nullable=True)
    cabin_class = Column(String(20), nullable=True)
    baggage_allowance = Column(Text, nullable=True)
    
    checkin_opens_datetime = Column(DateTime, nullable=True)
    checkin_url = Column(Text, nullable=True)
    eticket_url = Column(Text, nullable=True)
    voucher_url = Column(Text, nullable=True)
    flight_status = Column(String(50), default='confirmed')
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    
    # Campos para integración con API de vuelos
    flight_iata = Column(String(10), nullable=True)
    departure_gate = Column(String(10), nullable=True)
    arrival_gate = Column(String(10), nullable=True)
    flight_date = Column(Date, nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    
    # Relationships
    package = relationship("SoldPackage", back_populates="flights")
    provider = relationship("Provider")
    shared_flight = relationship("SharedFlight", back_populates="package_flights")  # 🆕 NUEVO


class PackageAccommodation(Base):
    """Alojamiento/Hotel incluido en un paquete"""
    __tablename__ = "package_accommodations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    hotel_name = Column(String(255), nullable=False)
    hotel_category = Column(String(50), nullable=True)
    city = Column(String(100), nullable=False)
    address = Column(Text, nullable=False)
    postal_code = Column(String(20), nullable=True)
    google_maps_url = Column(Text, nullable=True)
    coordinates = Column(Text, nullable=True)
    
    hotel_phone = Column(String(50), nullable=True)
    hotel_email = Column(String(255), nullable=True)
    hotel_website = Column(Text, nullable=True)
    
    booking_confirmation = Column(String(50), nullable=False)
    checkin_date = Column(Date, nullable=False)
    checkout_date = Column(Date, nullable=False)
    nights_count = Column(Integer, nullable=False)
    
    room_type = Column(String(100), nullable=True)
    room_number = Column(String(20), nullable=True)
    bed_configuration = Column(String(100), nullable=True)
    meal_plan = Column(String(50), nullable=True)
    amenities = Column(Text, nullable=True)
    
    checkin_time = Column(Time, nullable=True)
    checkout_time = Column(Time, nullable=True)
    early_checkin_available = Column(Boolean, default=False)
    late_checkout_available = Column(Boolean, default=False)
    
    voucher_url = Column(Text, nullable=True)
    hotel_policies_url = Column(Text, nullable=True)
    special_requests = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="accommodations")
    provider = relationship("Provider")


class PackageTransfer(Base):
    """Traslado incluido en un paquete"""
    __tablename__ = "package_transfers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    transfer_type = Column(String(50), nullable=False)
    transfer_sequence = Column(Integer, nullable=True)
    transfer_date = Column(Date, nullable=False)
    pickup_time = Column(Time, nullable=False)
    estimated_arrival_time = Column(Time, nullable=True)
    
    pickup_location = Column(String(255), nullable=False)
    pickup_address = Column(Text, nullable=True)
    pickup_instructions = Column(Text, nullable=True)
    dropoff_location = Column(String(255), nullable=False)
    dropoff_address = Column(Text, nullable=True)
    
    provider_name = Column(String(200), nullable=True)
    provider_phone = Column(String(50), nullable=True)
    driver_name = Column(String(200), nullable=True)
    driver_phone = Column(String(50), nullable=True)
    
    vehicle_type = Column(String(100), nullable=True)
    vehicle_plate = Column(String(20), nullable=True)
    vehicle_capacity = Column(Integer, nullable=True)
    
    booking_reference = Column(String(50), nullable=True)
    voucher_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    transfer_status = Column(String(50), default='confirmed')
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="transfers")
    provider = relationship("Provider")


class PackageActivity(Base):
    """Actividad/Excursión incluida en un paquete"""
    __tablename__ = "package_activities"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    activity_name = Column(String(255), nullable=False)
    activity_type = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    activity_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    duration_hours = Column(Numeric(4, 2), nullable=True)
    
    meeting_point = Column(String(255), nullable=True)
    meeting_point_address = Column(Text, nullable=True)
    meeting_point_instructions = Column(Text, nullable=True)
    meeting_point_maps_url = Column(Text, nullable=True)
    
    provider_name = Column(String(200), nullable=True)
    provider_phone = Column(String(50), nullable=True)
    guide_name = Column(String(200), nullable=True)
    guide_phone = Column(String(50), nullable=True)
    
    description = Column(Text, nullable=True)
    included_services = Column(Text, nullable=True)
    not_included = Column(Text, nullable=True)
    what_to_bring = Column(Text, nullable=True)
    
    booking_reference = Column(String(50), nullable=True)
    voucher_url = Column(Text, nullable=True)
    price_per_person = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    activity_status = Column(String(50), default='confirmed')
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="activities")
    provider = relationship("Provider")


class PackageDocument(Base):
    """Documento/Voucher asociado a un paquete"""
    __tablename__ = "package_documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    document_type = Column(String(50), nullable=False)
    related_to = Column(String(50), nullable=True)
    related_id = Column(Integer, nullable=True)
    document_name = Column(String(255), nullable=False)
    document_description = Column(Text, nullable=True)
    
    file_url = Column(Text, nullable=False)
    file_type = Column(String(20), nullable=True)
    file_size_kb = Column(Integer, nullable=True)
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    document_number = Column(String(100), nullable=True)
    
    is_required = Column(Boolean, default=False)
    is_printable = Column(Boolean, default=True)
    uploaded_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="documents")


class PackageItinerary(Base):
    """Itinerario día a día de un paquete"""
    __tablename__ = "package_itinerary"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    day_number = Column(Integer, nullable=False)
    itinerary_date = Column(Date, nullable=False)
    day_title = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    
    morning_activities = Column(Text, nullable=True)
    afternoon_activities = Column(Text, nullable=True)
    evening_activities = Column(Text, nullable=True)
    
    breakfast_included = Column(Boolean, default=False)
    lunch_included = Column(Boolean, default=False)
    dinner_included = Column(Boolean, default=False)
    
    accommodation_id = Column(Integer, ForeignKey('package_accommodations.id'), nullable=True)
    notes = Column(Text, nullable=True)
    tips = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="itinerary")


class SupportTicket(Base):
    """Ticket de soporte post-venta"""
    __tablename__ = "support_tickets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id', ondelete='CASCADE'), nullable=False)
    
    ticket_number = Column(String(50), unique=True, nullable=False, index=True)
    ticket_subject = Column(String(255), nullable=False)
    ticket_category = Column(String(100), nullable=True)
    priority = Column(String(20), default='medium')
    status = Column(String(50), default='open')
    
    description = Column(Text, nullable=False)
    passenger_location = Column(String(255), nullable=True)
    
    assigned_to = Column(String(100), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_type = Column(String(50), nullable=True)
    auto_resolved_by_agent = Column(Boolean, default=False)
    resolution_time_minutes = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=now_argentina)
    updated_at = Column(DateTime, default=now_argentina, onupdate=now_argentina)
    
    related_flight_id = Column(Integer, ForeignKey('package_flights.id'), nullable=True)
    related_hotel_id = Column(Integer, ForeignKey('package_accommodations.id'), nullable=True)
    related_transfer_id = Column(Integer, ForeignKey('package_transfers.id'), nullable=True)
    related_activity_id = Column(Integer, ForeignKey('package_activities.id'), nullable=True)
    
    # Nueva lógica: Vinculación con sesión
    session_id = Column(String(255), index=True, nullable=True)
    has_escalated_issues = Column(Boolean, default=False)
    auto_resolved_issues_count = Column(Integer, default=0)
    escalated_issues_count = Column(Integer, default=0)
    
    # Proveedor asociado
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    provider_contacted_at = Column(DateTime, nullable=True)
    provider_response_time_minutes = Column(Integer, nullable=True)
    
    package = relationship("SoldPackage", back_populates="tickets")
    interactions = relationship("TicketInteraction", back_populates="ticket", cascade="all, delete-orphan")
    provider = relationship("Provider", foreign_keys=[provider_id])
    
    def to_dict(self) -> Dict:
        result = {
            "id": self.id,
            "ticket_number": self.ticket_number,
            "subject": self.ticket_subject,
            "category": self.ticket_category,
            "priority": self.priority,
            "status": self.status,
            "description": self.description,
            "auto_resolved": self.auto_resolved_by_agent,
            "session_id": self.session_id,
            "has_escalated_issues": self.has_escalated_issues,
            "auto_resolved_issues_count": self.auto_resolved_issues_count,
            "escalated_issues_count": self.escalated_issues_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "provider_id": self.provider_id,
            "provider_contacted_at": self.provider_contacted_at.isoformat() if self.provider_contacted_at else None,
            "provider_response_time": self.provider_response_time_minutes
        }
        
        # Incluir datos del proveedor si existe
        if self.provider:
            result["provider"] = self.provider.to_dict()
        
        return result


class TicketInteraction(Base):
    """Interacción/Mensaje en un ticket"""
    __tablename__ = "ticket_interactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False)
    
    interaction_type = Column(String(50), nullable=True)
    message = Column(Text, nullable=False)
    created_by = Column(String(100), nullable=True)
    attachments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_argentina)
    channel = Column(String(50), nullable=True)
    
    # Nueva lógica: Clasificación de issues
    interaction_category = Column(String(50), nullable=True)
    requires_escalation = Column(Boolean, default=False)
    auto_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    sequence_number = Column(Integer, nullable=True)
    
    # Proveedor asociado
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    provider_contact_shown = Column(Boolean, default=False)
    
    ticket = relationship("SupportTicket", back_populates="interactions")
    provider = relationship("Provider", foreign_keys=[provider_id])


class PostSaleSession(Base):
    """Sesión de post-venta (tracking de validación)"""
    __tablename__ = "postsale_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    package_id = Column(Integer, ForeignKey('sold_packages.id'), nullable=True)
    
    validated_at = Column(DateTime, nullable=True)
    validation_method = Column(String(50), nullable=True)
    last_interaction = Column(DateTime, nullable=True)
    total_messages = Column(Integer, default=0)
    tickets_created = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    # Nueva lógica: Ticket único por sesión
    active_ticket_id = Column(Integer, nullable=True)
    has_escalated_issues = Column(Boolean, default=False)
    auto_resolved_count = Column(Integer, default=0)
    escalated_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=now_argentina)
    
    package = relationship("SoldPackage", back_populates="sessions")