"""
Router del RESTAURANTE.

  Carta (backoffice):
    GET    /api/restaurant/menu
    POST   /api/restaurant/menu
    PUT    /api/restaurant/menu/{id}
    PATCH  /api/restaurant/menu/{id}/status
    DELETE /api/restaurant/menu/{id}

  Carta pública (sitio/carrito):
    GET    /api/restaurant/menu/public

  Pedidos:
    GET    /api/restaurant/orders            (backoffice)
    GET    /api/restaurant/orders/{code}
    POST   /api/restaurant/orders            (lo usa la pantalla de carrito)
    PATCH  /api/restaurant/orders/{code}/status

  Folio:
    GET    /api/restaurant/folio/{booking_code}
    POST   /api/restaurant/folio/{booking_code}/settle

  Reservas de mesa (Fase 2):
    GET    /api/restaurant/slots
    GET    /api/restaurant/table-reservations
    POST   /api/restaurant/table-reservations
    PATCH  /api/restaurant/table-reservations/{code}/status

  Vouchers (Fase 3):
    GET    /api/restaurant/vouchers
    GET    /api/restaurant/vouchers/{code}
    POST   /api/restaurant/vouchers
    POST   /api/restaurant/vouchers/{code}/redeem

  Stats:
    GET    /api/restaurant/stats
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.restaurant import MenuItem
from app.services import restaurant_service, exchange_rate_service
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/restaurant", tags=["Restaurant"])


# ── Schemas ──────────────────────────────────────────────────────────────────
class MenuItemPayload(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    category: str = "plato"
    price_usd: float = Field(..., ge=0)
    image_url: Optional[str] = None
    allergens: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    available: Optional[bool] = True
    status: Optional[str] = "active"
    only_dinner: Optional[bool] = False


class StatusUpdate(BaseModel):
    status: str


class OrderItemPayload(BaseModel):
    menu_item_id: int
    qty: int = Field(1, ge=1)
    notes: Optional[str] = None


class OrderPayload(BaseModel):
    items: List[OrderItemPayload]
    session_id: Optional[str] = None
    contact_id: Optional[int] = None
    booking_id: Optional[int] = None
    booking_code: Optional[str] = None   # código validado (huésped desde la web)
    channel: str = "web"
    fulfillment: str = "salon"       # room_service | salon | retiro
    payment_mode: str = "link"       # folio | link
    guest_name: Optional[str] = None
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: str


class TableReservationPayload(BaseModel):
    fecha: str                          # "YYYY-MM-DD"
    hora: str                           # "HH:MM" (turno válido)
    party_size: int = Field(2, ge=1)
    guest_name: Optional[str] = None
    guest_phone: Optional[str] = None
    booking_code: Optional[str] = None  # si es huésped
    contact_id: Optional[int] = None
    session_id: Optional[str] = None
    notes: Optional[str] = None
    channel: str = "web"


class TableReservationStatusUpdate(BaseModel):
    status: str


class VoucherPayload(BaseModel):
    items: List[OrderItemPayload]
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    contact_id: Optional[int] = None
    session_id: Optional[str] = None
    notes: Optional[str] = None
    channel: str = "web"


# ── Carta ────────────────────────────────────────────────────────────────────
@router.get("/menu", dependencies=[Depends(require_admin_key)])
def list_menu_admin(db: Session = Depends(get_db)):
    items = restaurant_service.list_menu(db, include_inactive=True)
    return {"menu": items, "exchange_rate": exchange_rate_service.get_current_rate(db)}


@router.get("/menu/public")
def list_menu_public(db: Session = Depends(get_db)):
    return {"menu": restaurant_service.list_menu(db, include_inactive=False)}


@router.post("/menu/seed", dependencies=[Depends(require_admin_key)])
def seed_menu(force: bool = False, db: Session = Depends(get_db)):
    """Siembra la carta real (restaurant_menu_seed.MENU) — solo la carta, nada más.

    Idempotente: si ya hay ítems en la carta no hace nada (a menos que ?force=true,
    que borra la carta demo previa y la vuelve a crear). Pensado para poblar la carta
    en un entorno nuevo (p. ej. Render) sin correr el populate completo de la demo.
    """
    from app.services.restaurant_menu_seed import menu_for_seed

    existing = db.query(MenuItem).count()
    if existing and not force:
        return {"ok": True, "seeded": 0, "existing": existing,
                "message": "Ya hay carta cargada; usá ?force=true para recrearla."}

    if force:
        db.query(MenuItem).filter(MenuItem.is_demo.is_(True)).delete(synchronize_session=False)
        db.commit()

    rate = exchange_rate_service.get_current_rate(db)["rate"]
    rows = menu_for_seed(rate)
    for row in rows:
        db.add(MenuItem(
            name=row["name"], description=row["description"], category=row["category"],
            price_usd=row["price_usd"], image_url=row["image_url"],
            allergens=row["allergens"], tags=row["tags"],
            available=True, status="active", only_dinner=row["only_dinner"],
            is_demo=True,
        ))
    db.commit()
    logger.info("Menu seeded", count=len(rows), force=force)
    return {"ok": True, "seeded": len(rows), "force": force}


@router.post("/menu", dependencies=[Depends(require_admin_key)])
async def create_menu_item(payload: MenuItemPayload, db: Session = Depends(get_db)):
    item = MenuItem(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        category=payload.category or "plato",
        price_usd=payload.price_usd,
        image_url=(payload.image_url or "").strip() or None,
        allergens=payload.allergens or [],
        tags=payload.tags or [],
        available=payload.available if payload.available is not None else True,
        status=payload.status or "active",
        only_dinner=bool(payload.only_dinner),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    await restaurant_service.reingest(item)
    logger.info("Menu item created", id=item.id, name=item.name)
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    return item.to_dict(rate=rate)


@router.put("/menu/{item_id}", dependencies=[Depends(require_admin_key)])
async def update_menu_item(item_id: int, payload: MenuItemPayload, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Ítem no encontrado.")
    item.name = payload.name.strip()
    item.description = (payload.description or "").strip() or None
    item.category = payload.category or "plato"
    item.price_usd = payload.price_usd
    item.image_url = (payload.image_url or "").strip() or None
    item.allergens = payload.allergens or []
    item.tags = payload.tags or []
    item.available = payload.available if payload.available is not None else True
    if payload.status:
        item.status = payload.status
    item.only_dinner = bool(payload.only_dinner)
    db.commit()
    db.refresh(item)
    await restaurant_service.reingest(item)
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    return item.to_dict(rate=rate)


@router.patch("/menu/{item_id}/status", dependencies=[Depends(require_admin_key)])
async def update_menu_status(item_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    if payload.status not in ("active", "inactive"):
        raise HTTPException(400, "Estado inválido.")
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Ítem no encontrado.")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    await restaurant_service.reingest(item)
    return item.to_dict()


@router.delete("/menu/{item_id}", dependencies=[Depends(require_admin_key)])
async def delete_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Ítem no encontrado.")
    await restaurant_service.remove_from_index(item)
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": item_id}


# ── Pedidos ──────────────────────────────────────────────────────────────────
@router.get("/orders", dependencies=[Depends(require_admin_key)])
def list_orders(db: Session = Depends(get_db)):
    return {"orders": restaurant_service.list_orders(db)}


@router.get("/orders/{code}")
def get_order(code: str, db: Session = Depends(get_db)):
    o = restaurant_service.get_order(db, code)
    if not o:
        raise HTTPException(404, "Pedido no encontrado.")
    return o


@router.get("/validate-booking/{code}")
def validate_booking(code: str, db: Session = Depends(get_db)):
    """Valida un código de reserva (existe + in-house) para habilitar el room charge."""
    return restaurant_service.validate_booking(db, code)


@router.post("/orders")
def create_order(payload: OrderPayload, db: Session = Depends(get_db)):
    result = restaurant_service.create_order(
        db,
        items=[i.model_dump() for i in payload.items],
        contact_id=payload.contact_id,
        booking_id=payload.booking_id,
        booking_code=payload.booking_code,
        session_id=payload.session_id,
        channel=payload.channel,
        fulfillment=payload.fulfillment,
        payment_mode=payload.payment_mode,
        guest_name=payload.guest_name,
        notes=payload.notes,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.patch("/orders/{code}/status", dependencies=[Depends(require_admin_key)])
def patch_order_status(code: str, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    o = restaurant_service.set_order_status(db, code, payload.status)
    if not o:
        raise HTTPException(404, "Pedido no encontrado.")
    return o


# ── Folio ────────────────────────────────────────────────────────────────────
@router.get("/folio/{booking_code}", dependencies=[Depends(require_admin_key)])
def get_folio(booking_code: str, db: Session = Depends(get_db)):
    folio = restaurant_service.get_folio(db, booking_code)
    if not folio:
        raise HTTPException(404, "Reserva no encontrada.")
    return folio


@router.post("/folio/{booking_code}/settle", dependencies=[Depends(require_admin_key)])
def settle_folio(booking_code: str, db: Session = Depends(get_db)):
    folio = restaurant_service.settle_folio(db, booking_code)
    if not folio:
        raise HTTPException(404, "Reserva no encontrada.")
    return folio


# ── Reservas de mesa (Fase 2) ────────────────────────────────────────────────
@router.get("/slots")
def restaurant_slots():
    """Turnos disponibles del restaurante (almuerzo/cena). Los consume la card del chat."""
    return {"slots": restaurant_service.RESTAURANT_SLOTS}


@router.get("/table-reservations", dependencies=[Depends(require_admin_key)])
def list_table_reservations(scope: Optional[str] = None, db: Session = Depends(get_db)):
    """Agenda de reservas de mesa (orden por fecha ASC). scope: today | week | upcoming."""
    return {"reservations": restaurant_service.list_table_reservations(db, scope=scope)}


@router.post("/table-reservations")
def create_table_reservation(payload: TableReservationPayload, db: Session = Depends(get_db)):
    result = restaurant_service.create_table_reservation(
        db,
        fecha=payload.fecha,
        hora=payload.hora,
        party_size=payload.party_size,
        guest_name=payload.guest_name,
        guest_phone=payload.guest_phone,
        contact_id=payload.contact_id,
        booking_code=payload.booking_code,
        session_id=payload.session_id,
        notes=payload.notes,
        channel=payload.channel,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.patch("/table-reservations/{code}/status", dependencies=[Depends(require_admin_key)])
def patch_table_reservation_status(code: str, payload: TableReservationStatusUpdate, db: Session = Depends(get_db)):
    r = restaurant_service.set_table_reservation_status(db, code, payload.status)
    if not r:
        raise HTTPException(404, "Reserva de mesa no encontrada o estado inválido.")
    return r


# ── Vouchers (Fase 3) ─────────────────────────────────────────────────────────
@router.get("/vouchers", dependencies=[Depends(require_admin_key)])
def list_vouchers(status: Optional[str] = None, db: Session = Depends(get_db)):
    return {"vouchers": restaurant_service.list_vouchers(db, status=status)}


@router.get("/vouchers/{code}")
def get_voucher(code: str, db: Session = Depends(get_db)):
    v = restaurant_service.get_voucher(db, code)
    if not v:
        raise HTTPException(404, "Voucher no encontrado.")
    return v


@router.post("/vouchers")
def create_voucher(payload: VoucherPayload, db: Session = Depends(get_db)):
    result = restaurant_service.create_voucher(
        db,
        items=[i.model_dump() for i in payload.items],
        buyer_name=payload.buyer_name,
        buyer_phone=payload.buyer_phone,
        contact_id=payload.contact_id,
        session_id=payload.session_id,
        notes=payload.notes,
        channel=payload.channel,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/vouchers/{code}/redeem", dependencies=[Depends(require_admin_key)])
def redeem_voucher(code: str, db: Session = Depends(get_db)):
    result = restaurant_service.redeem_voucher(db, code)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── Stats ────────────────────────────────────────────────────────────────────
@router.get("/stats", dependencies=[Depends(require_admin_key)])
def restaurant_stats(db: Session = Depends(get_db)):
    return restaurant_service.stats(db)
