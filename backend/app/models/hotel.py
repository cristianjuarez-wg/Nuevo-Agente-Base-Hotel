"""
Modelos de dominio HOTEL (single-property).

Reemplazan a los modelos de turismo (postsale.py / lead.py / provider.py) para el
motor de reserva de la demo. Son intencionalmente SIMPLES: un catálogo de tipos de
habitación (`Room`) y reservas (`Booking`). La disponibilidad NO se almacena por día;
se calcula por solapamiento de fechas (ver routers/reservations.py).

Reutilizan el `Base` y el `engine` de models/database.py (misma BD SQLite).
"""
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, date

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
    status = Column(String, nullable=False, default="active") # "active" | "inactive"

    bookings = relationship("Booking", back_populates="room")
    units = relationship("RoomUnit", back_populates="room", cascade="all, delete-orphan")

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
            "status": self.status or "active",
        }


class RoomUnit(Base):
    """Habitación física individual (unidad) de un tipo. Ej: King 101, King 102…

    Una `Room` (tipo) agrupa N `RoomUnit`. A diferencia de `total_units` (un contador),
    cada unidad tiene número propio y puede asignarse a una reserva concreta, lo que
    permite saber en qué habitación está cada huésped (recepción/housekeeping).
    """
    __tablename__ = "room_units"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    number = Column(String(10), nullable=False, index=True)  # "101", "201", "001"…
    floor = Column(Integer, nullable=True)
    # available / maintenance / blocked  (las dos últimas la sacan del inventario vendible)
    status = Column(String(20), nullable=False, default="available")

    room = relationship("Room", back_populates="units")
    bookings = relationship("Booking", back_populates="room_unit")

    def to_dict(self):
        return {
            "id": self.id,
            "room_id": self.room_id,
            "room_type": self.room.room_type if self.room else None,
            "number": self.number,
            "floor": self.floor,
            "status": self.status,
        }


class Booking(Base):
    """Reserva de una habitación para un rango de fechas."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)  # ej "HTL-7F3A"
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)

    # Unidad física asignada (King 101…). Nullable: reservas históricas o aún sin asignar.
    room_unit_id = Column(Integer, ForeignKey("room_units.id"), nullable=True, index=True)

    # Identidad del huésped (Visión 360°): la reserva pertenece a un Contact.
    # session_id da trazabilidad a la conversación de chat que la originó.
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)

    guest_name = Column(String, nullable=False)
    guest_email = Column(String, nullable=True)
    guest_phone = Column(String, nullable=True)

    check_in = Column(Date, nullable=False, index=True)
    check_out = Column(Date, nullable=False, index=True)
    guests = Column(Integer, nullable=False, default=1)       # adultos (compatibilidad)
    children = Column(Integer, nullable=False, default=0)     # niños 3-17 (cuentan ocupación)
    infants = Column(Integer, nullable=False, default=0)      # bebés 0-2 en cuna (NO ocupan)
    nights = Column(Integer, nullable=False, default=1)
    total_price_usd = Column(Float, nullable=False)
    total_price_ars = Column(Float, nullable=False)

    # Promo aplicada (si hubo). full_price_usd = precio sin descuento, para trazabilidad.
    promo_name = Column(String, nullable=True)
    full_price_usd = Column(Float, nullable=True)

    # pending / confirmed / cancelled / completed
    status = Column(String, nullable=False, default="confirmed", index=True)
    # pending / paid / refunded  (demo: pago simulado → "paid")
    payment_status = Column(String, nullable=False, default="paid")

    source = Column(String, nullable=False, default="web")  # "web" | "agente"
    # Origen de DOS DIMENSIONES (preparatorias para carga humana futura):
    #   generated_by: "aura" (IA) | "human" (equipo). created_by: empleado que la cargó.
    # Hoy no se setean (todo es Aura); el origen se deriva de source+session_id.
    generated_by = Column(String(20), nullable=True)   # default conceptual: "aura"
    created_by = Column(String(120), nullable=True)    # autor humano (futuro)
    created_at = Column(DateTime, default=datetime.now)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    room = relationship("Room", back_populates="bookings")
    room_unit = relationship("RoomUnit", back_populates="bookings")
    # Cargos extra al folio (consumos de restaurante, etc.). Lazy: solo se carga al pedirlo.
    extra_charges = relationship(
        "ExtraCharge",
        primaryjoin="Booking.id == foreign(ExtraCharge.booking_id)",
        viewonly=True,
        lazy="select",
    )

    def origin(self) -> dict:
        """Origen unificado de la reserva (icono+etiqueta consistentes en el backoffice)."""
        from app.core.origin import origin_from_booking
        return origin_from_booking(self.source, self.session_id, self.generated_by)

    def folio_summary(self) -> dict:
        """Resumen del folio: estadía + cargos extra. `extra_charges` se carga lazy."""
        charges = list(self.extra_charges or [])
        extras_usd = round(sum(c.amount_usd or 0 for c in charges), 2)
        pending_usd = round(sum(c.amount_usd or 0 for c in charges if c.status != "saldado"), 2)
        return {
            "stay_usd": self.total_price_usd or 0,
            "extras_usd": extras_usd,
            "folio_total_usd": round((self.total_price_usd or 0) + extras_usd, 2),
            "folio_pending_usd": pending_usd,
            "charges_count": len(charges),
        }

    def stay_status(self) -> str:
        """Estado temporal de la estadía respecto a HOY (derivado, no se persiste).

        Fuente única de verdad para Reservas, Pasajeros y Dashboard:
          - "cancelled": la reserva está cancelada (prevalece sobre lo temporal).
          - "checked_in": el huésped está alojado AHORA (check_in <= hoy <= check_out).
          - "upcoming": la estadía es futura (check_in > hoy).
          - "past": la estadía ya terminó (check_out < hoy).
        """
        if self.status == "cancelled":
            return "cancelled"
        today = date.today()
        if self.check_in and self.check_out:
            if self.check_in <= today <= self.check_out:
                return "checked_in"
            if self.check_in > today:
                return "upcoming"
            if self.check_out < today:
                return "past"
        return "upcoming"

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "room_id": self.room_id,
            "room_type": self.room.room_type if self.room else None,
            "room_unit_id": self.room_unit_id,
            "room_number": self.room_unit.number if self.room_unit else None,
            "contact_id": self.contact_id,
            "session_id": self.session_id,
            "stay_status": self.stay_status(),
            "guest_name": self.guest_name,
            "guest_email": self.guest_email,
            "guest_phone": self.guest_phone,
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "guests": self.guests,
            "children": self.children or 0,
            "infants": self.infants or 0,
            "nights": self.nights,
            "total_price_usd": self.total_price_usd,
            "total_price_ars": self.total_price_ars,
            "promo_name": self.promo_name,
            "full_price_usd": self.full_price_usd,
            "status": self.status,
            "payment_status": self.payment_status,
            "source": self.source,
            "origin": self.origin(),
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
    # Nullable: un pedido de restaurante de un VISITANTE de afuera (sin reserva) también
    # genera ticket de aviso al equipo, sin booking asociado.
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    session_id = Column(String, nullable=False, index=True)

    subject = Column(String, nullable=False)
    category = Column(String, nullable=False, default="general")  # general/change/cancel/complaint/info/service_request
    priority = Column(String, nullable=False, default="medium")   # low/medium/high/urgent
    # Estados base: open / in_progress / resolved / escalated.
    # Estados del ciclo OPERATIVO (Fase 4, "empleado digital"):
    #   asignado     → enrutado a un área/persona del equipo, esperando que lo resuelvan.
    #   pre_resuelto → el staff lo marcó resuelto; esperando validación del huésped.
    #   resuelto     → cierre definitivo (validado por el huésped, o sin huésped a validar).
    status = Column(String, nullable=False, default="open", index=True)
    description = Column(String, nullable=True)

    # Trazabilidad del agente IA
    auto_resolved_by_agent = Column(String, nullable=True)  # última respuesta auto-resuelta
    escalated = Column(Integer, nullable=False, default=0)   # 0/1: requirió asesor humano

    # --- Ciclo operativo (Fase 4): asignación al equipo + loop de doble validación ---
    assigned_staff_id = Column(Integer, ForeignKey("staff_members.id"), nullable=True, index=True)
    assigned_area = Column(String(20), nullable=True)        # snapshot del área asignada
    origin = Column(String(20), nullable=False, default="guest")  # "guest" | "staff" (quién lo originó)
    resolution_note = Column(String, nullable=True)          # nota del staff al resolver ("reparado el aire 401")
    resolved_by_staff_id = Column(Integer, ForeignKey("staff_members.id"), nullable=True)
    guest_validated = Column(Integer, nullable=False, default=0)  # 0/1: el huésped confirmó la resolución

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    booking = relationship("Booking")
    assigned_staff = relationship("StaffMember", foreign_keys=[assigned_staff_id])

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
            # Ciclo operativo (Fase 4)
            "origin": self.origin,
            "assigned_staff_id": self.assigned_staff_id,
            "assigned_area": self.assigned_area,
            "assigned_staff_name": self.assigned_staff.name if self.assigned_staff else None,
            "resolution_note": self.resolution_note,
            "guest_validated": bool(self.guest_validated),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Crear SOLO las tablas de hotel (Room, Booking, HotelTicket) de forma explícita, sin
# disparar el create_all global: otras tablas de Base (heredadas del proyecto) tienen FKs
# que solo resuelven si sus modelos están importados, y acá no queremos depender de ese orden.
Base.metadata.create_all(
    bind=engine,
    tables=[Room.__table__, RoomUnit.__table__, Booking.__table__, HotelTicket.__table__],
)


def _ensure_booking_columns():
    """Migración ligera idempotente: agrega columnas nuevas a `bookings` si faltan.

    `create_all` no altera tablas existentes. En bases ya creadas (Render/PostgreSQL,
    SQLite local) agregamos children/infants con ADD COLUMN IF NOT EXISTS-equivalente,
    tolerando ambos motores. Evita tener que configurar Alembic para un cambio menor.
    """
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(engine)
        existing = {c["name"] for c in inspector.get_columns("bookings")}
        to_add = []
        if "children" not in existing:
            to_add.append("children")
        if "infants" not in existing:
            to_add.append("infants")
        if not to_add:
            return
        with engine.begin() as conn:
            for col in to_add:
                conn.execute(text(f"ALTER TABLE bookings ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"))
    except Exception:
        # No bloquear el arranque por la migración; las columnas tienen default en el modelo.
        pass


_ensure_booking_columns()
