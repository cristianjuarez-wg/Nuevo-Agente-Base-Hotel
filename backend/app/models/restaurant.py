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
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if rate:
            d["amount_ars"] = round((self.amount_usd or 0) * rate, 2)
        return d


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
        ],
    )
except Exception:  # noqa: BLE001 — el create_all definitivo corre en run_light_migrations
    pass
