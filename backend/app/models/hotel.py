"""
Modelos de dominio HOTEL (single-property).

Reemplazan a los modelos de turismo (postsale.py / lead.py / provider.py) para el
motor de reserva de la demo. Son intencionalmente SIMPLES: un catálogo de tipos de
habitación (`Room`) y reservas (`Booking`). La disponibilidad NO se almacena por día;
se calcula por solapamiento de fechas (ver routers/reservations.py).

Reutilizan el `Base` y el `engine` de models/database.py (misma BD SQLite).
"""
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.database import Base, engine


class Room(Base):
    """Tipo de habitación del hotel (no una unidad física individual)."""
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_type = Column(String, nullable=False, index=True)   # "King", "Twin", "Family Plan", ...
    description = Column(String, nullable=True)
    capacity = Column(Integer, nullable=False, default=2)     # huéspedes máx por habitación
    base_price_usd = Column(Float, nullable=False)           # precio por noche en USD
    base_price_ars = Column(Float, nullable=False)           # precio por noche en ARS
    total_units = Column(Integer, nullable=False, default=1)  # cuántas habitaciones de este tipo hay
    bed_config = Column(String, nullable=True)               # "1 cama king", "2 camas twin", ...
    view = Column(String, nullable=True)                     # "Lago o ciudad"
    images = Column(JSON, nullable=True, default=list)        # lista de URLs
    amenities = Column(JSON, nullable=True, default=list)     # lista de strings

    bookings = relationship("Booking", back_populates="room")

    def to_dict(self):
        return {
            "id": self.id,
            "room_type": self.room_type,
            "description": self.description,
            "capacity": self.capacity,
            "base_price_usd": self.base_price_usd,
            "base_price_ars": self.base_price_ars,
            "total_units": self.total_units,
            "bed_config": self.bed_config,
            "view": self.view,
            "images": self.images or [],
            "amenities": self.amenities or [],
        }


class Booking(Base):
    """Reserva de una habitación para un rango de fechas."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)  # ej "HTL-7F3A"
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)

    guest_name = Column(String, nullable=False)
    guest_email = Column(String, nullable=True)
    guest_phone = Column(String, nullable=True)

    check_in = Column(Date, nullable=False, index=True)
    check_out = Column(Date, nullable=False, index=True)
    guests = Column(Integer, nullable=False, default=1)
    nights = Column(Integer, nullable=False, default=1)
    total_price_usd = Column(Float, nullable=False)
    total_price_ars = Column(Float, nullable=False)

    # pending / confirmed / cancelled / completed
    status = Column(String, nullable=False, default="confirmed", index=True)
    # pending / paid / refunded  (demo: pago simulado → "paid")
    payment_status = Column(String, nullable=False, default="paid")

    source = Column(String, nullable=False, default="web")  # "web" | "agente"
    created_at = Column(DateTime, default=datetime.now)

    room = relationship("Room", back_populates="bookings")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "room_id": self.room_id,
            "room_type": self.room.room_type if self.room else None,
            "guest_name": self.guest_name,
            "guest_email": self.guest_email,
            "guest_phone": self.guest_phone,
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "guests": self.guests,
            "nights": self.nights,
            "total_price_usd": self.total_price_usd,
            "total_price_ars": self.total_price_ars,
            "status": self.status,
            "payment_status": self.payment_status,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HotelTicket(Base):
    """Ticket de soporte POST-VENTA de un huésped con reserva (modelo simple del hotel).

    Reemplaza al SupportTicket de turismo (atado a sold_packages y a vuelos/proveedores).
    Una sesión de post-venta del hotel = un ticket abierto contra una reserva (Booking).
    """
    __tablename__ = "hotel_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String, unique=True, nullable=False, index=True)  # "HT-XXXXXX"
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)

    subject = Column(String, nullable=False)
    category = Column(String, nullable=False, default="general")  # general/change/cancel/complaint/info
    priority = Column(String, nullable=False, default="medium")   # low/medium/high/urgent
    # open / in_progress / resolved / escalated
    status = Column(String, nullable=False, default="open", index=True)
    description = Column(String, nullable=True)

    # Trazabilidad del agente IA
    auto_resolved_by_agent = Column(String, nullable=True)  # última respuesta auto-resuelta
    escalated = Column(Integer, nullable=False, default=0)   # 0/1: requirió asesor humano

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    booking = relationship("Booking")

    def to_dict(self):
        return {
            "id": self.id,
            "ticket_number": self.ticket_number,
            "booking_id": self.booking_id,
            "session_id": self.session_id,
            "subject": self.subject,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "description": self.description,
            "escalated": bool(self.escalated),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Crear SOLO las tablas de hotel (Room, Booking, HotelTicket) de forma explícita, sin
# disparar el create_all global: otras tablas de Base (heredadas del proyecto) tienen FKs
# que solo resuelven si sus modelos están importados, y acá no queremos depender de ese orden.
Base.metadata.create_all(
    bind=engine,
    tables=[Room.__table__, Booking.__table__, HotelTicket.__table__],
)
