"""
Servicio del motor de reserva (single-hotel).

Contiene la lógica de negocio de disponibilidad y creación de reservas, separada del
router para que las TOOLS del agente (hotel_tools.py) puedan reutilizarla directamente
sin pasar por HTTP — mismo patrón que en Freeway, donde las tools envuelven services.

Disponibilidad CALCULADA por solapamiento de fechas (no se almacena por día):
una Room está disponible en [check_in, check_out) si
    total_units − (bookings que solapan ese rango y no están cancelados) > 0.
"""
import secrets
import string
from datetime import date
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.models.hotel import Room, Booking, RoomUnit
from app.services import exchange_rate_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Estados que NO ocupan inventario (no cuentan para el solapamiento).
_NON_BLOCKING_STATUSES = {"cancelled"}


def _ars(usd: float, rate: float) -> float:
    """Convierte USD a ARS con la cotización vigente."""
    return round((usd or 0) * rate, 2)


def _generate_booking_code() -> str:
    """Código corto y legible para una reserva, ej. 'HTL-7F3A'."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"HTL-{suffix}"


def _nights_between(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def _units_booked(db: Session, room_id: int, check_in: date, check_out: date) -> int:
    """Cuántas unidades de un tipo de habitación están ocupadas en el rango dado.

    Dos rangos [a_in, a_out) y [b_in, b_out) se solapan si a_in < b_out y b_in < a_out.
    """
    overlapping = (
        db.query(Booking)
        .filter(
            Booking.room_id == room_id,
            Booking.check_in < check_out,
            Booking.check_out > check_in,
            ~Booking.status.in_(_NON_BLOCKING_STATUSES),
        )
        .count()
    )
    return overlapping


def _lock_overlapping_bookings(db: Session, room_id: int, check_in: date, check_out: date) -> None:
    """Toma un row-lock (FOR UPDATE) sobre las reservas solapadas del tipo, si el motor
    lo soporta (PostgreSQL). Serializa la validación+creación concurrente para evitar
    doble-booking. En SQLite no hace nada (no soporta FOR UPDATE y ya serializa writes).
    """
    try:
        if db.bind and db.bind.dialect.name == "postgresql":
            (
                db.query(Booking.id)
                .filter(
                    Booking.room_id == room_id,
                    Booking.check_in < check_out,
                    Booking.check_out > check_in,
                    ~Booking.status.in_(_NON_BLOCKING_STATUSES),
                )
                .with_for_update()
                .all()
            )
    except Exception as e:  # noqa: BLE001 — el lock es defensivo; un fallo no debe romper la reserva
        logger.warning("No se pudo tomar el lock de reservas (continuando)", error=str(e))


def _free_units(db: Session, room: Room, check_in: date, check_out: date) -> List[RoomUnit]:
    """Unidades FÍSICAS de un tipo libres en el rango (status available + sin solape).

    Una unidad está libre si su status es 'available' y no tiene ninguna reserva
    (no cancelada) que solape el rango pedido.
    """
    units = (
        db.query(RoomUnit)
        .filter(RoomUnit.room_id == room.id, RoomUnit.status == "available")
        .order_by(RoomUnit.number.asc())
        .all()
    )
    if not units:
        return []
    # IDs de unidades ocupadas por solape en ese rango.
    occupied = {
        b.room_unit_id
        for b in db.query(Booking).filter(
            Booking.room_id == room.id,
            Booking.room_unit_id.isnot(None),
            Booking.check_in < check_out,
            Booking.check_out > check_in,
            ~Booking.status.in_(_NON_BLOCKING_STATUSES),
        )
    }
    return [u for u in units if u.id not in occupied]


def _units_left(db: Session, room: Room, check_in: date, check_out: date) -> int:
    """Disponibilidad del tipo en el rango.

    Si el tipo ya tiene unidades físicas sembradas → cuenta unidades libres reales.
    Si aún no las tiene (transición) → cae al cálculo legacy total_units − ocupadas.
    """
    has_units = db.query(RoomUnit).filter(RoomUnit.room_id == room.id).first() is not None
    if has_units:
        return len(_free_units(db, room, check_in, check_out))
    return room.total_units - _units_booked(db, room.id, check_in, check_out)


def list_rooms(db: Session, include_inactive: bool = False) -> List[Dict]:
    """Catálogo de tipos de habitación.

    Para la landing/chat: solo activas. Para el backoffice (`include_inactive=True`):
    todas. El precio ARS se calcula al vuelo con la cotización vigente (el USD es la
    fuente de verdad; `base_price_ars` de la tabla quedó obsoleto).
    """
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    query = db.query(Room)
    if not include_inactive:
        # NULL se trata como activa (filas previas a la columna status).
        query = query.filter(or_(Room.status == "active", Room.status.is_(None)))
    rooms = query.order_by(Room.base_price_usd.asc()).all()
    result = []
    for r in rooms:
        info = r.to_dict()
        info["base_price_ars"] = _ars(r.base_price_usd, rate)
        result.append(info)
    return result


def get_availability(
    db: Session, check_in: date, check_out: date, guests: int = 1, children: int = 0,
) -> List[Dict]:
    """Tipos de habitación disponibles en el rango, con precio total calculado.

    Devuelve solo habitaciones con capacidad suficiente y unidades libres.
    OCUPACIÓN = adultos (`guests`) + niños (`children`). Los bebés/infantes NO cuentan
    para la capacidad (van en cuna) y por eso no son un parámetro acá.
    """
    if check_out <= check_in:
        raise ValueError("check_out debe ser posterior a check_in")

    occupancy = guests + max(children, 0)
    nights = _nights_between(check_in, check_out)
    rate = exchange_rate_service.get_current_rate(db)["rate"]
    results: List[Dict] = []

    rooms = (
        db.query(Room)
        .filter(
            Room.capacity >= occupancy,
            or_(Room.status == "active", Room.status.is_(None)),
        )
        .all()
    )
    for room in rooms:
        units_left = _units_left(db, room, check_in, check_out)
        if units_left <= 0:
            continue
        info = room.to_dict()
        info.update(
            {
                "units_available": units_left,
                "nights": nights,
                "base_price_ars": _ars(room.base_price_usd, rate),
                "total_price_usd": round(room.base_price_usd * nights, 2),
                "total_price_ars": _ars(room.base_price_usd * nights, rate),
                # Sobredimensionada para el grupo (al menos 2 plazas de más): se ofrece como
                # "más espacio si querés", no como primera opción.
                "oversized": (room.capacity - occupancy) >= 2,
            }
        )
        results.append(info)

    # Ordenar por ADECUACIÓN al grupo: la que mejor calza (menor holgura de capacidad)
    # primero; a igual holgura, la de menor capacidad y luego la más económica. Así el texto,
    # las tarjetas del chat y las cards de WhatsApp muestran primero lo más adecuado (una
    # pareja ve King/Twin antes que la Family Plan).
    results.sort(key=lambda r: (r["capacity"] - occupancy, r["capacity"], r["total_price_usd"]))
    return results


def create_booking(
    db: Session,
    *,
    room_type: Optional[str] = None,
    room_id: Optional[int] = None,
    check_in: date,
    check_out: date,
    guest_name: str,
    guest_email: Optional[str] = None,
    guest_phone: Optional[str] = None,
    guests: int = 1,
    children: int = 0,
    infants: int = 0,
    source: str = "web",
    session_id: Optional[str] = None,
    promo_name: Optional[str] = None,
) -> Dict:
    """Crea una reserva si hay disponibilidad. Pago SIMULADO → payment_status='paid'.

    Acepta `room_id` (preciso, desde la landing) o `room_type` (desde el agente, que
    razona en lenguaje natural). Valida disponibilidad ANTES de crear — es el punto
    "determinístico" que el agente NO puede saltarse.

    Si `promo_name` se indica y esa promo vigente APLICA a la estadía, el total se
    recalcula con el descuento (server-side, sin confiar en números del LLM) y se
    guarda el precio sin promo en `full_price_usd` para trazabilidad.

    Returns: dict con la reserva creada (incluye `code`) o un dict {"error": ...}.
    """
    if check_out <= check_in:
        return {"error": "El check-out debe ser posterior al check-in."}

    # Resolver la habitación
    room = None
    if room_id is not None:
        room = db.query(Room).filter(Room.id == room_id).first()
    elif room_type:
        room = (
            db.query(Room)
            .filter(Room.room_type.ilike(f"%{room_type.strip()}%"))
            .first()
        )
    if room is None:
        return {"error": "No se encontró ese tipo de habitación."}

    occupancy = guests + max(children, 0)
    if room.capacity < occupancy:
        return {
            "error": f"La habitación '{room.room_type}' admite hasta {room.capacity} "
            f"huéspedes (se pidieron {occupancy}, sin contar bebés en cuna)."
        }

    # LOCK PESIMISTA (anti doble-booking): serializa las reservas concurrentes del mismo
    # tipo de habitación. En PostgreSQL (Render) tomamos un row-lock sobre las reservas
    # solapadas del tipo, de modo que dos requests simultáneos no vean ambos la última
    # unidad libre. En SQLite (local) no hay FOR UPDATE, pero SQLite ya serializa las
    # escrituras, así que el riesgo no aplica. La validación + creación van en la misma
    # transacción (sin commit intermedio hasta crear el Booking).
    _lock_overlapping_bookings(db, room.id, check_in, check_out)

    # Validación determinística de disponibilidad + auto-asignación de unidad física.
    # Si el tipo tiene unidades sembradas, tomamos la primera libre y la asignamos.
    # Si no (transición), validamos por conteo legacy y la reserva queda sin unidad.
    has_units = db.query(RoomUnit).filter(RoomUnit.room_id == room.id).first() is not None
    assigned_unit = None
    if has_units:
        free = _free_units(db, room, check_in, check_out)
        if not free:
            return {"error": f"No hay disponibilidad de '{room.room_type}' para esas fechas."}
        assigned_unit = free[0]  # primera libre (orden por número)
    else:
        if room.total_units - _units_booked(db, room.id, check_in, check_out) <= 0:
            return {"error": f"No hay disponibilidad de '{room.room_type}' para esas fechas."}

    nights = _nights_between(check_in, check_out)
    rate = exchange_rate_service.get_current_rate(db)["rate"]

    # Precio base (sin promo). Si se pidió aplicar una promo y APLICA realmente a esta
    # estadía, recalculamos el total con el descuento — server-side, fuente de verdad.
    base_total_usd = round(room.base_price_usd * nights, 2)
    total_usd = base_total_usd
    full_price_usd = None
    applied_promo_name = None
    if promo_name:
        from app.services import promotions_service
        promo = next(
            (p for p in promotions_service.get_vigentes(db) if p.name == promo_name), None
        )
        if promo:
            oferta = promotions_service.aplicar_descuento(promo, room.base_price_usd, nights)
            if oferta:
                total_usd = oferta["final_price_usd"]
                full_price_usd = oferta["full_price_usd"]
                applied_promo_name = oferta["promo_name"]

    clean_phone = (guest_phone or "").strip() or None
    clean_email = (guest_email or "").strip() or None

    # En WhatsApp el teléfono real está en el session_id ("wa_<telefono>"). Si el agente
    # no capturó un guest_phone explícito, usamos ese número como identidad del huésped.
    if not clean_phone and session_id and session_id.startswith("wa_"):
        clean_phone = "+" + session_id[3:]

    # Identidad 360°: vincular la reserva a un Contact (clave = teléfono). Email enriquece.
    # El conteo de compras y el contact_type se recalculan en update_contact_metrics()
    # DESPUÉS de persistir el Booking (fuente de verdad = Bookings vinculados).
    contact_id = None
    if clean_phone:
        try:
            from app.services.contact_service import contact_service
            contact = contact_service.get_or_create_contact(
                phone=clean_phone, name=guest_name.strip(), email=clean_email, db=db
            )
            if contact:
                contact_id = contact.id
        except Exception as e:  # noqa: BLE001 — no bloquear la reserva por la vinculación
            logger.warning("No se pudo vincular la reserva a un Contact", error=str(e))

    booking = Booking(
        code=_generate_booking_code(),
        room_id=room.id,
        room_unit_id=assigned_unit.id if assigned_unit else None,
        contact_id=contact_id,
        session_id=session_id,
        guest_name=guest_name.strip(),
        guest_email=clean_email,
        guest_phone=clean_phone,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        children=max(children, 0),
        infants=max(infants, 0),
        nights=nights,
        total_price_usd=total_usd,
        total_price_ars=_ars(total_usd, rate),
        promo_name=applied_promo_name,
        full_price_usd=full_price_usd,
        status="confirmed",
        payment_status="paid",  # pago simulado
        source=source,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Recalcular métricas agregadas del Contact (purchases_made, contact_type, etc.).
    if contact_id:
        try:
            from app.services.contact_service import contact_service
            contact_service.update_contact_metrics(contact_id, db)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo actualizar métricas del Contact", error=str(e))

        # Vincular la conversación de esta sesión al Contact (si existe): así la bandeja
        # muestra el nombre del huésped en vez de "Sin nombre" tras reservar.
        if session_id:
            try:
                from app.services.contact_service import contact_service
                contact_service.link_conversation_by_session(session_id, contact_id, db)
            except Exception as e:  # noqa: BLE001
                logger.warning("No se pudo vincular la conversación al Contact tras reservar",
                               session_id=session_id, error=str(e))

    # Marcar como CONVERTIDO el lead que originó esta reserva (si existe). Cubre AMBOS
    # caminos (agente y web), que pasan por acá. Best-effort: un fallo NUNCA debe romper
    # la reserva (ya está commiteada arriba).
    try:
        from app.services.lead_service import lead_service
        lead_service.mark_lead_converted(
            db, session_id=session_id, contact_id=contact_id, booking_code=booking.code,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo marcar el lead como convertido", error=str(e))

    logger.info(
        "Booking created",
        code=booking.code,
        room_type=room.room_type,
        source=source,
        contact_id=contact_id,
        check_in=str(check_in),
        check_out=str(check_out),
    )
    return booking.to_dict()


def get_booking(db: Session, code: str) -> Optional[Dict]:
    """Consulta una reserva por su código (usado por la landing, el agente y posventa)."""
    booking = db.query(Booking).filter(Booking.code == code.strip().upper()).first()
    return booking.to_dict() if booking else None


def list_bookings(db: Session) -> List[Dict]:
    """Todas las reservas (para el backoffice)."""
    bookings = db.query(Booking).order_by(Booking.check_in.asc()).all()
    return [b.to_dict() for b in bookings]


def delete_booking(db: Session, code: str) -> bool:
    """Elimina una reserva por su código. Devuelve True si existía y se borró.

    Al liberar inventario, recalculamos las métricas del contacto vinculado (si lo hay)
    para que su contador de compras quede consistente.
    """
    booking = db.query(Booking).filter(Booking.code == code.strip().upper()).first()
    if booking is None:
        return False

    contact_id = booking.contact_id

    # Los tickets de soporte tienen booking_id NOT NULL → borrarlos primero para no
    # dejar registros huérfanos que rompan la integridad referencial.
    from app.models.hotel import HotelTicket
    db.query(HotelTicket).filter(HotelTicket.booking_id == booking.id).delete(
        synchronize_session=False
    )

    db.delete(booking)
    db.commit()

    if contact_id:
        try:
            from app.services.contact_service import ContactService
            ContactService().update_contact_metrics(contact_id, db)
        except Exception as e:  # noqa: BLE001 — el borrado ya ocurrió; no romper por métricas
            logger.warning("No se pudieron recalcular métricas tras borrar reserva", error=str(e))

    logger.info("Reserva eliminada", code=code)
    return True
