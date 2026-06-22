"""
Servicio del RESTAURANTE: carta, pedidos, folio (room charge) y stats.

  - list_menu / CRUD de la carta (con re-ingesta al RAG, patrón promotions_service).
  - create_order: valida items contra la carta (precio SERVER-SIDE), crea el pedido,
    abre un ExtraCharge en el folio (si es room charge) y un HotelTicket "restaurant"
    para avisar al equipo.
  - stats: KPIs de F&B para Dashboard/Analíticas.

El precio NUNCA se confía del cliente/LLM: siempre se recalcula desde la carta.
"""
import secrets
import string
import hashlib
from datetime import datetime, date
from typing import List, Dict, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.config import settings
from app.services.vector_store import get_vector_store
from app.services import exchange_rate_service
from app.models.restaurant import MenuItem, RestaurantOrder, OrderItem, ExtraCharge
from app.models.hotel import Booking, HotelTicket
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _gen_code(prefix: str, n: int = 4) -> str:
    return prefix + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))


# ---------------------------------------------------------------------------
# Carta
# ---------------------------------------------------------------------------
def list_menu(db: Session, include_inactive: bool = False) -> List[Dict]:
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    q = db.query(MenuItem)
    if not include_inactive:
        q = q.filter(MenuItem.status == "active")
    items = q.order_by(MenuItem.category.asc(), MenuItem.name.asc()).all()
    return [it.to_dict(rate=rate) for it in items]


# ---------------------------------------------------------------------------
# RAG: la carta se re-ingesta para que info_hotel la encuentre
# ---------------------------------------------------------------------------
def _build_chunks(doc_source: str, text: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(text)
    doc_id = hashlib.md5(doc_source.encode()).hexdigest()[:12]
    return [
        {
            "text": piece,
            "metadata": {
                "doc_id": doc_id, "chunk_index": i, "status": "active",
                "source": doc_source, "filename": doc_source,
            },
        }
        for i, piece in enumerate(pieces)
    ]


async def reingest(item: MenuItem) -> dict:
    vs = get_vector_store()
    source = item.doc_source
    deleted = added = 0
    try:
        deleted = vs.delete_by_source(source).get("deleted", 0)
    except Exception as e:
        logger.warning("menu reingest: delete falló", source=source, error=str(e))
    if item.status == "active":
        text = item.to_ingest_text().strip()
        if text:
            try:
                added = (await vs.add_documents(_build_chunks(source, text))).get("added", 0)
            except Exception as e:
                logger.error("menu reingest: add falló", source=source, error=str(e))
    return {"deleted": deleted, "added": added}


async def remove_from_index(item: MenuItem) -> dict:
    vs = get_vector_store()
    deleted = 0
    try:
        deleted = vs.delete_by_source(item.doc_source).get("deleted", 0)
    except Exception as e:
        logger.warning("menu remove_from_index falló", error=str(e))
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
def _resolve_active_booking(db: Session, contact_id: Optional[int], session_id: Optional[str]) -> Optional[Booking]:
    """Reserva ACTIVA (hospedado hoy) del contacto/sesión, para el room charge."""
    today = date.today()
    q = db.query(Booking).filter(
        Booking.status != "cancelled",
        Booking.check_in <= today, Booking.check_out >= today,
    )
    if contact_id:
        b = q.filter(Booking.contact_id == contact_id).first()
        if b:
            return b
    if session_id:
        return q.filter(Booking.session_id == session_id).first()
    return None


def validate_booking(db: Session, code: str) -> Dict:
    """Valida un código de reserva para habilitar el room charge.

    Devuelve si la reserva existe y está IN-HOUSE (check-in hecho, check-out pendiente).
    Solo expone nombre y número de habitación para que el huésped confirme que es la suya.
    """
    booking = db.query(Booking).filter(Booking.code == (code or "").strip().upper()).first()
    if not booking:
        return {"valid": False, "reason": "no_existe"}
    in_house = booking.stay_status() == "checked_in"
    if not in_house:
        return {"valid": False, "in_house": False, "reason": "no_alojado"}
    return {
        "valid": True,
        "in_house": True,
        "booking_code": booking.code,
        "guest_name": (booking.guest_name or "").split(" ")[0] if booking.guest_name else None,
        "room_number": booking.room_unit.number if booking.room_unit else None,
    }


def _booking_for_folio(db: Session, booking_code: Optional[str], contact_id: Optional[int],
                       session_id: Optional[str]) -> Optional[Booking]:
    """Resuelve la reserva para cargar al folio, REVALIDANDO que esté in-house.

    Prioridad: (1) booking_code validado (web), (2) contacto/sesión (WhatsApp).
    Devuelve None si no hay una reserva in-house (entonces NO se puede cargar al folio).
    """
    if booking_code:
        b = db.query(Booking).filter(Booking.code == booking_code.strip().upper()).first()
        if b and b.stay_status() == "checked_in":
            return b
        return None
    b = _resolve_active_booking(db, contact_id, session_id)
    if b and b.stay_status() == "checked_in":
        return b
    return None


def create_order(
    db: Session,
    *,
    items: List[Dict],                 # [{"menu_item_id": int, "qty": int, "notes": str}]
    contact_id: Optional[int] = None,
    booking_id: Optional[int] = None,
    booking_code: Optional[str] = None,  # código validado desde la web (huésped)
    session_id: Optional[str] = None,
    channel: str = "web",
    fulfillment: str = "salon",        # room_service | salon | retiro
    payment_mode: str = "link",        # folio | link
    guest_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict:
    """Crea un pedido validando precios server-side.

    El cargo al FOLIO solo se acepta si hay una reserva IN-HOUSE (se revalida acá; no se
    confía en el cliente). Todo pedido —con o sin reserva— genera un ticket al equipo.
    """
    if not items:
        return {"error": "El pedido no tiene ítems."}

    rate = exchange_rate_service.get_current_rate(db)["rate"]

    # Validar items contra la carta y armar líneas con precio real.
    order_items: List[OrderItem] = []
    total_usd = 0.0
    detalle_lines = []
    for raw in items:
        mid = raw.get("menu_item_id")
        qty = max(1, int(raw.get("qty") or 1))
        mi = db.query(MenuItem).filter(MenuItem.id == mid, MenuItem.status == "active").first()
        if not mi:
            return {"error": f"Ítem inválido o no disponible (id={mid})."}
        line_usd = round(mi.price_usd * qty, 2)
        total_usd += line_usd
        order_items.append(OrderItem(
            menu_item_id=mi.id, name_snapshot=mi.name, qty=qty,
            unit_price_usd=mi.price_usd, notes=(raw.get("notes") or "").strip() or None,
        ))
        detalle_lines.append(f"{qty}x {mi.name}")
    total_usd = round(total_usd, 2)

    # Resolver la reserva para folio, REVALIDANDO in-house (seguridad server-side).
    booking = None
    if booking_id:
        b = db.query(Booking).filter(Booking.id == booking_id).first()
        booking = b if (b and b.stay_status() == "checked_in") else None
    if booking is None:
        booking = _booking_for_folio(db, booking_code, contact_id, session_id)

    # Solo se carga al folio si hay reserva in-house. Si no, pago directo (link).
    if payment_mode == "folio" and booking is None:
        payment_mode = "link"
    # Sin reserva no puede haber room service "a la habitación": cae a salón.
    if booking is None and fulfillment == "room_service":
        fulfillment = "salon"

    order = RestaurantOrder(
        order_code=_gen_code("RST-"),
        contact_id=contact_id,
        booking_id=booking.id if booking else None,
        session_id=session_id,
        channel=channel, fulfillment=fulfillment, payment_mode=payment_mode,
        total_usd=total_usd, total_ars=round(total_usd * rate, 2),
        status="pendiente",
        guest_name=guest_name or (booking.guest_name if booking else None),
        notes=(notes or "").strip() or None,
    )
    order.items = order_items
    db.add(order)
    db.flush()  # para tener order.id

    # Folio (room charge): abre un ExtraCharge pendiente sobre la reserva.
    if payment_mode == "folio" and booking is not None:
        db.add(ExtraCharge(
            booking_id=booking.id, order_id=order.id, category="restaurant",
            description=f"Pedido {order.order_code}: " + ", ".join(detalle_lines),
            amount_usd=total_usd, status="pendiente",
        ))

    # Ticket al equipo SIEMPRE (con o sin reserva), para que cocina/mozos se enteren.
    dest = {"room_service": "Room service", "salon": "Salón", "retiro": "Retiro"}.get(fulfillment, fulfillment)
    quien = (booking.guest_name if booking else (guest_name or "Visitante"))
    db.add(HotelTicket(
        ticket_number=_gen_code("HT-", 6),
        booking_id=booking.id if booking else None,
        session_id=session_id or order.order_code,
        subject=f"Pedido restaurante {order.order_code} — {dest}"
                + ("" if booking else " (visitante)"),
        category="restaurant", priority="high", status="open",
        description=f"{quien}: " + ", ".join(detalle_lines)
        + (f". Notas: {notes}" if notes else "")
        + f". Pago: {'a la habitación' if payment_mode == 'folio' else 'link de pago'}.",
    ))

    db.commit()
    db.refresh(order)
    logger.info("Restaurant order created", code=order.order_code,
                total_usd=total_usd, mode=payment_mode, fulfillment=fulfillment,
                booking=bool(booking))

    result = order.to_dict()
    result["payment_mode"] = payment_mode
    if booking:
        result["folio"] = booking.folio_summary()
        result["booking_code"] = booking.code
    return result


def get_order(db: Session, order_code: str) -> Optional[Dict]:
    o = db.query(RestaurantOrder).filter(RestaurantOrder.order_code == order_code.strip().upper()).first()
    return o.to_dict() if o else None


def list_orders(db: Session) -> List[Dict]:
    orders = db.query(RestaurantOrder).order_by(RestaurantOrder.created_at.desc()).all()
    return [o.to_dict() for o in orders]


def set_order_status(db: Session, order_code: str, status: str) -> Optional[Dict]:
    o = db.query(RestaurantOrder).filter(RestaurantOrder.order_code == order_code.strip().upper()).first()
    if not o:
        return None
    o.status = status
    o.updated_at = datetime.now()
    db.commit()
    db.refresh(o)
    return o.to_dict()


# ---------------------------------------------------------------------------
# Folio
# ---------------------------------------------------------------------------
def get_folio(db: Session, booking_code: str) -> Optional[Dict]:
    booking = db.query(Booking).filter(Booking.code == booking_code.strip().upper()).first()
    if not booking:
        return None
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    summary = booking.folio_summary()
    summary["stay_ars"] = round(summary["stay_usd"] * rate, 2)
    summary["folio_total_ars"] = round(summary["folio_total_usd"] * rate, 2)
    return {
        "booking_code": booking.code,
        "guest_name": booking.guest_name,
        "summary": summary,
        "charges": [c.to_dict(rate=rate) for c in (booking.extra_charges or [])],
    }


def settle_folio(db: Session, booking_code: str) -> Optional[Dict]:
    booking = db.query(Booking).filter(Booking.code == booking_code.strip().upper()).first()
    if not booking:
        return None
    for c in booking.extra_charges or []:
        if c.status != "saldado":
            c.status = "saldado"
    db.commit()
    return get_folio(db, booking_code)


# ---------------------------------------------------------------------------
# Stats (Dashboard / Analíticas)
# ---------------------------------------------------------------------------
def stats(db: Session) -> Dict:
    today = date.today()
    orders = db.query(RestaurantOrder).filter(RestaurantOrder.status != "cancelado").all()
    revenue_usd = round(sum(o.total_usd or 0 for o in orders), 2)
    today_count = sum(1 for o in orders if o.created_at and o.created_at.date() == today)

    # Top platos.
    counter: Dict[str, int] = {}
    for o in orders:
        for it in o.items:
            counter[it.name_snapshot] = counter.get(it.name_snapshot, 0) + (it.qty or 1)
    top = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "orders_total": len(orders),
        "orders_today": today_count,
        "revenue_fnb_usd": revenue_usd,
        "top_dishes": [{"name": n, "qty": q} for n, q in top],
    }
