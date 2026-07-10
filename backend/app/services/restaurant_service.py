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
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rag.vector_store import get_vector_store
from app.services import exchange_rate_service
from app.models.restaurant import (
    MenuItem, RestaurantOrder, OrderItem, ExtraCharge, TableReservation, Voucher, VoucherItem,
)
from app.models.hotel import Booking, HotelTicket
from app.core.observability.logging_config import get_logger

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


def session_guest_preset(db: Session, session_id: Optional[str]) -> Dict:
    """Preset para la card de mesa cuando el huésped YA reservó en ESTA sesión web.

    Si hay una reserva (no cancelada) creada en la sesión, devuelve su nombre y un flag
    `guest_linked` para que la card no le pida el código (el backend asocia la mesa por
    session_id). Si no hay, devuelve {} y la card se comporta como hasta ahora (visitante).
    """
    if not session_id or session_id.startswith("wa_"):
        return {}
    booking = (
        db.query(Booking)
        .filter(Booking.session_id == session_id, Booking.status != "cancelled")
        .order_by(Booking.created_at.desc())
        .first()
    )
    if not booking:
        return {}
    return {"guest_linked": True, "nombre": booking.guest_name or None}


def folio_guest_preset(db: Session, booking_code: Optional[str], session_id: Optional[str]) -> Dict:
    """Preset para el CHECKOUT DE COMIDA: solo si el huésped está ALOJADO HOY (in-house).

    A diferencia de `session_guest_preset` (mesa, que acepta cualquier reserva), el cargo al
    folio EXIGE estar alojado hoy. Reutiliza `validate_booking` (que filtra checked_in):
    devuelve `{valid, booking_code, guest_name, room_number}` solo si está in-house; si no,
    `{}` y el checkout pide los datos como hasta ahora (caso reserva-futura / visitante).

    Fuentes en orden: (1) el código que el huésped ya validó en la charla (booking_code),
    (2) el booking creado en ESTA sesión web (no WhatsApp).
    """
    code = (booking_code or "").strip().upper() or None
    if not code and session_id and not session_id.startswith("wa_"):
        b = (
            db.query(Booking)
            .filter(Booking.session_id == session_id, Booking.status != "cancelled")
            .order_by(Booking.created_at.desc())
            .first()
        )
        code = b.code if b else None
    if not code:
        return {}
    res = validate_booking(db, code)
    return res if res.get("valid") else {}


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

    # Recalcular métricas 360° del contacto (gasto F&B, tipo) si el pedido es de un huésped
    # identificado (por contact_id directo o por la reserva a la que se cargó el folio).
    metrics_contact_id = order.contact_id or (booking.contact_id if booking else None)
    if metrics_contact_id:
        try:
            from app.services.contact_service import contact_service
            contact_service.update_contact_metrics(metrics_contact_id, db)
        except Exception as e:  # noqa: BLE001 — no romper el pedido por las métricas
            logger.warning("No se pudieron recalcular métricas tras el pedido", error=str(e))

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


def list_orders_for_contact(db: Session, contact_id: int) -> List[Dict]:
    """Todos los pedidos de un contacto: por `contact_id` directo y por `booking_id` de
    sus reservas (para pedidos que se cargaron al folio sin contact_id). Sin duplicados.
    Cada pedido viene con sus `items` (vía to_dict)."""
    from sqlalchemy import or_

    booking_ids = [
        b.id for b in db.query(Booking.id).filter(Booking.contact_id == contact_id).all()
    ]
    q = db.query(RestaurantOrder).filter(RestaurantOrder.status != "cancelado")
    if booking_ids:
        q = q.filter(or_(
            RestaurantOrder.contact_id == contact_id,
            RestaurantOrder.booking_id.in_(booking_ids),
        ))
    else:
        q = q.filter(RestaurantOrder.contact_id == contact_id)
    orders = q.order_by(RestaurantOrder.created_at.desc()).all()
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
# Reservas de MESA (Fase 2)
# ---------------------------------------------------------------------------
# Turnos del restaurante (constante única, fácil de editar). La card del chat los muestra;
# el server valida que la hora reservada sea uno de estos.
RESTAURANT_SLOTS = {
    "almuerzo": ["12:30", "13:00", "13:30", "14:00", "14:30"],
    "cena": ["20:00", "20:30", "21:00", "21:30", "22:00"],
}


def _all_slots() -> set:
    return {h for franja in RESTAURANT_SLOTS.values() for h in franja}


def create_table_reservation(
    db: Session,
    *,
    fecha: str,                          # "YYYY-MM-DD"
    hora: str,                           # "HH:MM" (debe ser un turno válido)
    party_size: int,
    guest_name: Optional[str] = None,
    guest_phone: Optional[str] = None,
    contact_id: Optional[int] = None,
    booking_code: Optional[str] = None,  # si es huésped, asocia su reserva
    session_id: Optional[str] = None,
    notes: Optional[str] = None,
    channel: str = "web",
) -> Dict:
    """Crea una reserva de mesa. No exige estar in-house (la mesa es pública).

    Valida que la hora sea un turno válido y que la fecha/hora sea futura. Si viene un
    `booking_code`, la asocia al Booking/Contact (huésped). Genera un ticket de aviso al salón.
    """
    if not fecha or not hora:
        return {"error": "Faltan la fecha o el turno de la reserva."}
    if hora not in _all_slots():
        return {"error": "Ese horario no es un turno disponible del restaurante."}
    party_size = max(1, int(party_size or 1))

    try:
        reserved_for = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        return {"error": "Fecha u hora con formato inválido."}
    if reserved_for < datetime.now():
        return {"error": "La fecha y hora de la reserva ya pasaron."}

    # Si es huésped (trae código), resolver Booking/Contact. No exige in-house.
    booking = None
    if booking_code:
        booking = db.query(Booking).filter(
            Booking.code == booking_code.strip().upper()
        ).first()
        if booking:
            contact_id = contact_id or booking.contact_id

    reservation = TableReservation(
        code=_gen_code("MESA-"),
        contact_id=contact_id,
        booking_id=booking.id if booking else None,
        session_id=session_id,
        guest_name=guest_name or (booking.guest_name if booking else None),
        guest_phone=guest_phone or (booking.guest_phone if booking else None),
        party_size=party_size,
        reserved_for=reserved_for,
        status="confirmada",
        notes=(notes or "").strip() or None,
        channel=channel,
    )
    db.add(reservation)
    db.flush()

    # Ticket de aviso al salón (igual patrón que los pedidos).
    quien = reservation.guest_name or "Visitante"
    cuando = reserved_for.strftime("%d/%m %H:%M")
    db.add(HotelTicket(
        ticket_number=_gen_code("HT-", 6),
        booking_id=booking.id if booking else None,
        session_id=session_id or reservation.code,
        subject=f"Reserva de mesa {reservation.code} — {cuando}"
                + ("" if booking else " (visitante)"),
        category="table_reservation", priority="medium", status="open",
        description=f"{quien}: mesa para {party_size} persona(s) el {cuando}."
        + (f" Notas: {notes}" if notes else ""),
    ))

    db.commit()
    db.refresh(reservation)
    logger.info("Table reservation created", code=reservation.code,
                reserved_for=reserved_for.isoformat(), party=party_size,
                guest=bool(booking))

    if contact_id:
        try:
            from app.services.contact_service import contact_service
            contact_service.update_contact_metrics(contact_id, db)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudieron recalcular métricas tras la reserva de mesa", error=str(e))

    result = reservation.to_dict()
    if booking:
        result["booking_code"] = booking.code
    return result


def list_table_reservations(db: Session, scope: Optional[str] = None) -> List[Dict]:
    """Reservas de mesa ordenadas por fecha ASC (agenda: del próximo al más lejano).

    `scope` opcional: "today" | "week" | "upcoming" para los filtros del backoffice.
    """
    q = db.query(TableReservation)
    today = date.today()
    if scope == "today":
        start = datetime(today.year, today.month, today.day)
        end = start + timedelta(days=1)
        q = q.filter(TableReservation.reserved_for >= start, TableReservation.reserved_for < end)
    elif scope == "week":
        start = datetime(today.year, today.month, today.day)
        end = start + timedelta(days=7)
        q = q.filter(TableReservation.reserved_for >= start, TableReservation.reserved_for < end)
    elif scope == "upcoming":
        q = q.filter(TableReservation.reserved_for >= datetime.now())
    reservations = q.order_by(TableReservation.reserved_for.asc()).all()
    return [r.to_dict() for r in reservations]


def set_table_reservation_status(db: Session, code: str, status: str) -> Optional[Dict]:
    valid = ("confirmada", "sentada", "no_show", "cancelada")
    if status not in valid:
        return None
    r = db.query(TableReservation).filter(
        TableReservation.code == (code or "").strip().upper()
    ).first()
    if not r:
        return None
    r.status = status
    db.commit()
    db.refresh(r)
    return r.to_dict()


# ---------------------------------------------------------------------------
# Vouchers (Fase 3) — compra anticipada de un visitante de afuera
# ---------------------------------------------------------------------------
def _validate_items_and_total(db: Session, items: List[Dict]):
    """Valida ítems contra la carta y recalcula el total SERVER-SIDE.

    Devuelve (lineas, total_usd, detalle_txt) o ({"error": ...},) si algo es inválido.
    Reusado por el voucher (mismo criterio que create_order: el precio nunca se confía).
    """
    lines = []
    total_usd = 0.0
    detalle = []
    for raw in items:
        mid = raw.get("menu_item_id")
        qty = max(1, int(raw.get("qty") or 1))
        mi = db.query(MenuItem).filter(MenuItem.id == mid, MenuItem.status == "active").first()
        if not mi:
            return None, None, None, f"Ítem inválido o no disponible (id={mid})."
        total_usd += round(mi.price_usd * qty, 2)
        lines.append((mi, qty))
        detalle.append(f"{qty}x {mi.name}")
    return lines, round(total_usd, 2), ", ".join(detalle), None


def create_voucher(
    db: Session,
    *,
    items: List[Dict],
    buyer_name: Optional[str] = None,
    buyer_phone: Optional[str] = None,
    contact_id: Optional[int] = None,
    session_id: Optional[str] = None,
    notes: Optional[str] = None,
    channel: str = "web",
) -> Dict:
    """Emite un voucher de compra anticipada (visitante). Total recalculado server-side."""
    if not items:
        return {"error": "El voucher no tiene ítems."}

    rate = exchange_rate_service.get_current_rate(db)["rate"]
    lines, total_usd, detalle, err = _validate_items_and_total(db, items)
    if err:
        return {"error": err}

    voucher = Voucher(
        code=_gen_code("VCH-"),
        contact_id=contact_id,
        session_id=session_id,
        buyer_name=(buyer_name or "").strip() or None,
        buyer_phone=(buyer_phone or "").strip() or None,
        total_usd=total_usd, total_ars=round(total_usd * rate, 2),
        status="emitido",
        notes=(notes or "").strip() or None,
        channel=channel,
    )
    voucher.items = [
        VoucherItem(menu_item_id=mi.id, name_snapshot=mi.name, qty=qty, unit_price_usd=mi.price_usd)
        for (mi, qty) in lines
    ]
    db.add(voucher)
    db.flush()

    # Ticket informativo (baja prioridad): un voucher no va a cocina, pero el equipo lo registra.
    db.add(HotelTicket(
        ticket_number=_gen_code("HT-", 6),
        booking_id=None,
        session_id=session_id or voucher.code,
        subject=f"Voucher {voucher.code} emitido (visitante)",
        category="voucher", priority="low", status="open",
        description=f"{voucher.buyer_name or 'Visitante'}: {detalle}. Total USD {total_usd:.0f}. "
                    "Pendiente de canje.",
    ))

    db.commit()
    db.refresh(voucher)
    logger.info("Voucher created", code=voucher.code, total_usd=total_usd)

    if contact_id:
        try:
            from app.services.contact_service import contact_service
            contact_service.update_contact_metrics(contact_id, db)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudieron recalcular métricas tras el voucher", error=str(e))

    return voucher.to_dict()


def list_vouchers(db: Session, status: Optional[str] = None) -> List[Dict]:
    q = db.query(Voucher)
    if status and status != "all":
        q = q.filter(Voucher.status == status)
    vouchers = q.order_by(Voucher.created_at.desc()).all()
    return [v.to_dict() for v in vouchers]


def get_voucher(db: Session, code: str) -> Optional[Dict]:
    v = db.query(Voucher).filter(Voucher.code == (code or "").strip().upper()).first()
    return v.to_dict() if v else None


def redeem_voucher(db: Session, code: str) -> Dict:
    """Canjea un voucher (staff, backoffice). Sólo si está 'emitido'."""
    v = db.query(Voucher).filter(Voucher.code == (code or "").strip().upper()).first()
    if not v:
        return {"error": "Voucher no encontrado."}
    if v.status == "canjeado":
        return {"error": "Ese voucher ya fue canjeado.", "voucher": v.to_dict()}
    if v.status == "cancelado":
        return {"error": "Ese voucher está cancelado.", "voucher": v.to_dict()}
    v.status = "canjeado"
    v.redeemed_at = datetime.now()
    db.commit()
    db.refresh(v)
    logger.info("Voucher redeemed", code=v.code)
    return v.to_dict()


def link_voucher_to_table(db: Session, voucher_code: str, reservation_code: str) -> Optional[Dict]:
    """Asocia un voucher a una reserva de mesa (combo)."""
    v = db.query(Voucher).filter(Voucher.code == (voucher_code or "").strip().upper()).first()
    r = db.query(TableReservation).filter(
        TableReservation.code == (reservation_code or "").strip().upper()
    ).first()
    if not v or not r:
        return None
    v.table_reservation_id = r.id
    db.commit()
    db.refresh(v)
    return v.to_dict()


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
