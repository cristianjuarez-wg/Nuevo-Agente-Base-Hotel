"""
Modelos del RESTAURANTE (PLAZA - Hampton's Kitchen House).

  - MenuItem:        la carta (platos/bebidas). Precio en USD (fuente de verdad);
                     el ARS se calcula al vuelo con la cotización vigente.
  - RestaurantOrder: un pedido del huésped/visitante (room service, salón o retiro).
  - OrderItem:       cada línea del pedido (plato + cantidad + precio snapshot).
  - ExtraCharge:     cargo al FOLIO de una reserva (room charge). Folio abierto que
                     se salda al check-out.

El precio se valida SIEMPRE server-side contra la carta — nunca se confía en el
número que mande el cliente/LLM.
"""
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.models.database import Base, engine
from app.utils.timezone_utils import iso_business


class MenuItem(Base):
    """Un ítem de la carta del restaurante."""
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    # "tapas" | "plato" | "sandwich" | "ensalada" | "pizza" | "postre" |
    # "cerveza" | "trago" | "vino" | "cafeteria" | "merienda" | "bebida"
    category = Column(String, nullable=False, default="plato", index=True)
    price_usd = Column(Float, nullable=False)             # fuente de verdad
    image_url = Column(String, nullable=True)
    allergens = Column(JSON, nullable=True, default=list)  # ["gluten","lacteos","frutos_secos",...]
    tags = Column(JSON, nullable=True, default=list)       # ["vegetariano","vegano","sin_tacc","picante"]
    available = Column(Boolean, nullable=False, default=True)   # hay stock hoy
    status = Column(String, nullable=False, default="active")   # "active" | "inactive"
    only_dinner = Column(Boolean, nullable=False, default=False)  # ej. ojo de bife solo cena
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_demo = Column(Boolean, default=False, index=True)

    @property
    def doc_source(self) -> str:
        """Identificador determinístico para ChromaDB."""
        return f"kb-menu-{self.id}"

    def to_ingest_text(self) -> str:
        parts = [f"Plato del restaurante: {self.name} (categoría: {self.category})"]
        if self.description:
            parts.append(self.description)
        if self.tags:
            parts.append("Apto: " + ", ".join(self.tags))
        if self.allergens:
            parts.append("Contiene: " + ", ".join(self.allergens))
        parts.append(f"Precio: USD {self.price_usd:.0f}")
        return "\n".join(parts)

    def to_dict(self, rate: float = None):
        d = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "price_usd": self.price_usd,
            "image_url": self.image_url,
            "allergens": self.allergens or [],
            "tags": self.tags or [],
            "available": bool(self.available),
            "status": self.status,
            "only_dinner": bool(self.only_dinner),
        }
        if rate:
            d["price_ars"] = round((self.price_usd or 0) * rate, 2)
        return d


class RestaurantOrder(Base):
    """Pedido del restaurante (de un huésped o un visitante de afuera)."""
    __tablename__ = "restaurant_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String, unique=True, nullable=False, index=True)  # "RST-XXXX"
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)

    channel = Column(String, nullable=False, default="web")        # "web" | "whatsapp"
    fulfillment = Column(String, nullable=False, default="salon")  # "room_service" | "salon" | "retiro"
    payment_mode = Column(String, nullable=False, default="link")  # "folio" | "link"

    total_usd = Column(Float, nullable=False, default=0)
    total_ars = Column(Float, nullable=False, default=0)
    # "pendiente" | "confirmado" | "en_preparacion" | "entregado" | "cancelado"
    status = Column(String, nullable=False, default="pendiente", index=True)
    guest_name = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_demo = Column(Boolean, default=False, index=True)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "order_code": self.order_code,
            "contact_id": self.contact_id,
            "booking_id": self.booking_id,
            "session_id": self.session_id,
            "channel": self.channel,
            "fulfillment": self.fulfillment,
            "payment_mode": self.payment_mode,
            "total_usd": self.total_usd,
            "total_ars": self.total_ars,
            "status": self.status,
            "guest_name": self.guest_name,
            "notes": self.notes,
            "items": [it.to_dict() for it in self.items],
            "created_at": iso_business(self.created_at),
        }


class OrderItem(Base):
    """Una línea de un pedido (plato + cantidad + precio congelado)."""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("restaurant_orders.id"), nullable=False, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True, index=True)
    name_snapshot = Column(String, nullable=False)
    qty = Column(Integer, nullable=False, default=1)
    unit_price_usd = Column(Float, nullable=False, default=0)
    notes = Column(String, nullable=True)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    order = relationship("RestaurantOrder", back_populates="items")

    def to_dict(self):
        return {
            "id": self.id,
            "menu_item_id": self.menu_item_id,
            "name": self.name_snapshot,
            "qty": self.qty,
            "unit_price_usd": self.unit_price_usd,
            "notes": self.notes,
        }


class ExtraCharge(Base):
    """Cargo al FOLIO de una reserva (room charge). Folio abierto → se salda al check-out."""
    __tablename__ = "extra_charges"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("restaurant_orders.id"), nullable=True, index=True)
    category = Column(String, nullable=False, default="restaurant")  # restaurant/minibar/spa/...
    description = Column(String, nullable=False)
    amount_usd = Column(Float, nullable=False, default=0)
    status = Column(String, nullable=False, default="pendiente")  # "pendiente" | "saldado"
    created_at = Column(DateTime, default=datetime.now, index=True)
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self, rate: float = None):
        d = {
            "id": self.id,
            "booking_id": self.booking_id,
            "order_id": self.order_id,
            "category": self.category,
            "description": self.description,
            "amount_usd": self.amount_usd,
            "status": self.status,
            "created_at": iso_business(self.created_at),
        }
        if rate:
            d["amount_ars"] = round((self.amount_usd or 0) * rate, 2)
        return d


class TableReservation(Base):
    """Reserva de MESA del restaurante (no es un pedido de comida).

    La usan tanto visitantes de afuera como huéspedes alojados (que pueden asociarla a su
    reserva HTL-XXXX, sin obligación de comer/pagar nada al reservar). Se ve en el backoffice
    como una AGENDA ordenada por `reserved_for` (del próximo al más lejano).
    """
    __tablename__ = "table_reservations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)   # "MESA-XXXX"
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)  # si es huésped
    session_id = Column(String, nullable=True, index=True)

    guest_name = Column(String, nullable=True)
    guest_phone = Column(String, nullable=True)
    party_size = Column(Integer, nullable=False, default=2)           # personas
    reserved_for = Column(DateTime, nullable=False, index=True)       # fecha + hora del turno
    # confirmada | sentada | no_show | cancelada
    status = Column(String, nullable=False, default="confirmada", index=True)
    notes = Column(Text, nullable=True)
    channel = Column(String, nullable=False, default="web")           # web | whatsapp

    created_at = Column(DateTime, default=datetime.now, index=True)
    is_demo = Column(Boolean, default=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "contact_id": self.contact_id,
            "booking_id": self.booking_id,
            "session_id": self.session_id,
            "guest_name": self.guest_name,
            "guest_phone": self.guest_phone,
            "party_size": self.party_size,
            "reserved_for": iso_business(self.reserved_for),
            "status": self.status,
            "notes": self.notes,
            "channel": self.channel,
            "is_guest": self.booking_id is not None,
            "created_at": iso_business(self.created_at),
        }


class Voucher(Base):
    """Voucher de restaurante (compra anticipada de un VISITANTE de afuera).

    Contiene platos de la carta (snapshot de precio) que el visitante pagó por adelantado y
    canjea cuando va al hotel. El huésped alojado NO usa voucher (se le carga al folio). El
    canje lo hace el staff desde el backoffice. Puede asociarse a una reserva de mesa (combo).
    """
    __tablename__ = "vouchers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)   # "VCH-XXXX"
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    table_reservation_id = Column(Integer, ForeignKey("table_reservations.id"), nullable=True)

    buyer_name = Column(String, nullable=True)
    buyer_phone = Column(String, nullable=True)
    total_usd = Column(Float, nullable=False, default=0)
    total_ars = Column(Float, nullable=False, default=0)
    # emitido | canjeado | cancelado
    status = Column(String, nullable=False, default="emitido", index=True)
    redeemed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    channel = Column(String, nullable=False, default="web")

    created_at = Column(DateTime, default=datetime.now, index=True)
    is_demo = Column(Boolean, default=False, index=True)

    items = relationship("VoucherItem", back_populates="voucher", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "contact_id": self.contact_id,
            "session_id": self.session_id,
            "table_reservation_id": self.table_reservation_id,
            "buyer_name": self.buyer_name,
            "buyer_phone": self.buyer_phone,
            "total_usd": self.total_usd,
            "total_ars": self.total_ars,
            "status": self.status,
            "redeemed_at": iso_business(self.redeemed_at),
            "notes": self.notes,
            "channel": self.channel,
            "items": [it.to_dict() for it in self.items],
            "created_at": iso_business(self.created_at),
        }


class VoucherItem(Base):
    """Una línea de un voucher (plato + cantidad + precio congelado)."""
    __tablename__ = "voucher_items"

    id = Column(Integer, primary_key=True, index=True)
    voucher_id = Column(Integer, ForeignKey("vouchers.id"), nullable=False, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True, index=True)
    name_snapshot = Column(String, nullable=False)
    qty = Column(Integer, nullable=False, default=1)
    unit_price_usd = Column(Float, nullable=False, default=0)

    # Dato de demostración (generado por el seed). Permite limpiar solo lo demo.
    is_demo = Column(Boolean, default=False, index=True)

    voucher = relationship("Voucher", back_populates="items")

    def to_dict(self):
        return {
            "id": self.id,
            "menu_item_id": self.menu_item_id,
            "name": self.name_snapshot,
            "qty": self.qty,
            "unit_price_usd": self.unit_price_usd,
        }


# Crea las tablas del restaurante. Las FKs a contacts/bookings requieren que esos
# modelos ya estén registrados en la metadata; en el arranque normal de la app y en los
# seeds eso se garantiza (se importan todos los modelos antes). Si se importa este módulo
# de forma aislada, el create_all puede fallar por orden de tablas — lo toleramos.
try:
    Base.metadata.create_all(
        bind=engine,
        tables=[
            MenuItem.__table__,
            RestaurantOrder.__table__,
            OrderItem.__table__,
            ExtraCharge.__table__,
            TableReservation.__table__,
            Voucher.__table__,
            VoucherItem.__table__,
        ],
    )
except Exception:  # noqa: BLE001 — el create_all definitivo corre en run_light_migrations
    pass
