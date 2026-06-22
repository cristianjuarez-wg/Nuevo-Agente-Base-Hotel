"""
Servicio de DATOS DE DEMOSTRACIÓN.

Genera un dataset coherente y distribuido en el tiempo (semestre pasado + próximo)
para que la demo del backoffice se vea poblada y realista, respetando la Visión 360°
del pasajero: un Contact con sus Bookings, Conversations (+mensajes), Leads y Tickets
enlazados.

Todo lo generado se marca con `is_demo=True`, de modo que `clear()` borra SOLO lo demo
sin tocar datos reales de prueba ni la configuración (habitaciones, promos, temas, KB).

Invocable desde:
  - CLI:        python seed_demo_data.py
  - Backoffice: POST /api/demo/populate  |  /clear  |  GET /api/demo/status
"""
import random
import string
from datetime import date, datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models.hotel import Room, RoomUnit, Booking, HotelTicket, TicketEvent
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.staff import StaffMember
from app.models.restaurant import (
    MenuItem, RestaurantOrder, OrderItem, ExtraCharge,
    TableReservation, Voucher, VoucherItem,
)
from app.services import exchange_rate_service, promotions_service
from app.services.contact_service import contact_service
from app.services.restaurant_menu_seed import menu_for_seed
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Reproducibilidad: misma semilla = mismo dataset (salvo fechas, relativas a hoy).
_RNG = random.Random(20260621)

# ── Volumen objetivo (realista medio) ───────────────────────────────────────
N_CONTACTS = 60
N_BOOKINGS = 140
N_LEADS = 40
N_CONVERSATIONS = 50
N_TICKETS = 25
N_STAFF = 5

# ── Pools de datos realistas (Argentina / Bariloche) ─────────────────────────
_FIRST_NAMES = [
    "Martín", "Sofía", "Juan", "Valentina", "Lucas", "Camila", "Mateo", "Julieta",
    "Tomás", "Catalina", "Benjamín", "Mía", "Santiago", "Emma", "Nicolás", "Olivia",
    "Joaquín", "Renata", "Felipe", "Isabella", "Agustín", "Delfina", "Ignacio", "Pilar",
    "Bruno", "Guadalupe", "Facundo", "Victoria", "Gonzalo", "Florencia", "Ramiro", "Antonia",
]
_LAST_NAMES = [
    "González", "Rodríguez", "Fernández", "López", "Martínez", "Pérez", "García", "Sánchez",
    "Romero", "Sosa", "Torres", "Álvarez", "Ruiz", "Díaz", "Acosta", "Benítez",
    "Medina", "Herrera", "Suárez", "Aguirre", "Giménez", "Molina", "Silva", "Castro",
]
_AREA_CODES = ["11", "261", "341", "351", "381", "299", "294", "223", "264", "388"]
_EMAIL_DOMAINS = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.ar"]

_LEAD_INTERESTS = [
    "Escapada de fin de semana", "Vacaciones de invierno (ski)", "Luna de miel",
    "Viaje familiar", "Aniversario", "Turismo aventura", "Descanso y spa",
    "Visita al Cerro Catedral", "Recorrido lacustre", "Semana de receso escolar",
]
_OBSTACLES = ["precio", "fechas", "tiempo", "informacion", "ninguno"]
_TICKET_SUBJECTS = [
    ("Cambio de fechas de mi reserva", "change"),
    ("Solicito factura A", "info"),
    ("Consulta sobre el desayuno", "general"),
    ("¿Tienen estacionamiento disponible?", "general"),
    ("Quisiera cancelar mi reserva", "cancel"),
    ("Problema con el aire acondicionado", "complaint"),
    ("Late check-out para el domingo", "change"),
    ("¿Aceptan mascotas?", "info"),
    ("Pedido de cuna para bebé", "general"),
    ("No recibí el voucher por mail", "complaint"),
]
_STAFF_SEED = [
    ("Carlos Bianchi", "owner"),
    ("Lucía Méndez", "staff"),
    ("Diego Ferreyra", "staff"),
    ("Paula Ríos", "staff"),
    ("Andrés Quiroga", "staff"),
]

# Frases para construir conversaciones realistas (user / assistant alternados).
_USER_TURNS = [
    "Hola, quería consultar disponibilidad para una escapada.",
    "¿Tienen habitaciones para dos adultos?",
    "¿Cuál es el precio por noche?",
    "¿El desayuno está incluido?",
    "Me interesa, ¿cómo reservo?",
    "¿Tienen alguna promoción vigente?",
    "Perfecto, muchas gracias por la info.",
    "¿Hay estacionamiento en el hotel?",
    "¿Está cerca del centro?",
    "Lo voy a pensar y te confirmo.",
]
_ASSISTANT_TURNS = [
    "¡Hola! Con gusto te ayudo con tu estadía en el Hampton by Hilton Bariloche. ¿Para qué fechas?",
    "Sí, tenemos disponibilidad. La habitación King es ideal para dos adultos.",
    "El precio incluye desayuno buffet y WiFi. Te paso el detalle según tus fechas.",
    "Estamos a 150 metros del Centro Cívico, muy bien ubicados.",
    "Contamos con estacionamiento privado cubierto para huéspedes.",
    "¡Excelente! Te ayudo a concretar la reserva ahora mismo.",
    "Quedo a disposición para cualquier consulta. ¡Te esperamos en Bariloche!",
]


def _phone() -> str:
    area = _RNG.choice(_AREA_CODES)
    rest = "".join(_RNG.choice(string.digits) for _ in range(8 - (len(area) - 2)))
    return f"+549{area}{rest}"


_used_codes = set()


def _code(prefix: str, n: int = 4) -> str:
    """Código único con prefijo (evita colisiones en la corrida y contra la DB previa)."""
    while True:
        code = prefix + "".join(_RNG.choice(string.ascii_uppercase + string.digits) for _ in range(n))
        if code not in _used_codes:
            _used_codes.add(code)
            return code


# ── Conteos / estado ─────────────────────────────────────────────────────────
def counts(db: Session) -> Dict:
    """Cantidad de registros demo actuales (para mostrar en el backoffice)."""
    data = {
        "contacts": db.query(Contact).filter(Contact.is_demo.is_(True)).count(),
        "bookings": db.query(Booking).filter(Booking.is_demo.is_(True)).count(),
        "leads": db.query(Lead).filter(Lead.is_demo.is_(True)).count(),
        "conversations": db.query(Conversation).filter(Conversation.is_demo.is_(True)).count(),
        "messages": db.query(ConversationMessage).filter(ConversationMessage.is_demo.is_(True)).count(),
        "tickets": db.query(HotelTicket).filter(HotelTicket.is_demo.is_(True)).count(),
        "staff": db.query(StaffMember).filter(StaffMember.is_demo.is_(True)).count(),
        "menu_items": db.query(MenuItem).filter(MenuItem.is_demo.is_(True)).count(),
        "orders": db.query(RestaurantOrder).filter(RestaurantOrder.is_demo.is_(True)).count(),
    }
    data["has_data"] = any(v for k, v in data.items() if k != "has_data")
    return data


# ── Limpieza ──────────────────────────────────────────────────────────────────
def clear(db: Session) -> Dict:
    """Borra SOLO los registros marcados is_demo=True, en orden inverso de FKs."""
    before = counts(db)
    # Orden: hijos → padres para no violar FKs.
    # IDs de contactos y reservas demo: las reservas de mesa y vouchers creados EN VIVO
    # por el agente tienen is_demo=False pero referencian a esos contactos/reservas, así
    # que hay que borrarlos también o el DELETE de Contact/Booking viola la FK (Postgres).
    demo_contact_ids = [c.id for c in db.query(Contact.id).filter(Contact.is_demo.is_(True))]
    demo_booking_ids = [b.id for b in db.query(Booking.id).filter(Booking.is_demo.is_(True))]
    demo_ticket_ids = [t.id for t in db.query(HotelTicket.id).filter(HotelTicket.is_demo.is_(True))]

    # Restaurante: vouchers (+items) y reservas de mesa que cuelgan de demo.
    demo_voucher_ids = [v.id for v in db.query(Voucher.id).filter(
        Voucher.is_demo.is_(True) | Voucher.contact_id.in_(demo_contact_ids or [-1])
    )]
    if demo_voucher_ids:
        db.query(VoucherItem).filter(VoucherItem.voucher_id.in_(demo_voucher_ids)).delete(synchronize_session=False)
        db.query(Voucher).filter(Voucher.id.in_(demo_voucher_ids)).delete(synchronize_session=False)
    db.query(TableReservation).filter(
        TableReservation.is_demo.is_(True)
        | TableReservation.contact_id.in_(demo_contact_ids or [-1])
        | TableReservation.booking_id.in_(demo_booking_ids or [-1])
    ).delete(synchronize_session=False)

    demo_order_ids = [o.id for o in db.query(RestaurantOrder.id).filter(RestaurantOrder.is_demo.is_(True))]
    if demo_order_ids:
        db.query(OrderItem).filter(OrderItem.order_id.in_(demo_order_ids)).delete(synchronize_session=False)
    db.query(ExtraCharge).filter(ExtraCharge.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(RestaurantOrder).filter(RestaurantOrder.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(MenuItem).filter(MenuItem.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(ConversationMessage).filter(ConversationMessage.is_demo.is_(True)).delete(synchronize_session=False)
    # Bitácora de tickets (cuelga de hotel_tickets; bulk-delete no dispara el cascade ORM).
    if demo_ticket_ids:
        db.query(TicketEvent).filter(TicketEvent.ticket_id.in_(demo_ticket_ids)).delete(synchronize_session=False)
    db.query(HotelTicket).filter(HotelTicket.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(Booking).filter(Booking.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.is_demo.is_(True)).delete(synchronize_session=False)
    db.query(StaffMember).filter(StaffMember.is_demo.is_(True)).delete(synchronize_session=False)
    db.commit()
    logger.info("Demo data cleared", **{k: before[k] for k in before if k != "has_data"})
    return {k: before[k] for k in before if k != "has_data"}


# ── Población ─────────────────────────────────────────────────────────────────
def populate(db: Session) -> Dict:
    """Genera el dataset demo completo. Si ya hay datos demo, los regenera (limpia + crea)."""
    # Regenerar: empezamos limpio para no acumular y refrescar fechas a hoy.
    clear(db)

    # Precargar códigos existentes para no colisionar con reservas reales que queden.
    _used_codes.clear()
    _used_codes.update(c[0] for c in db.query(Booking.code).all())
    _used_codes.update(t[0] for t in db.query(HotelTicket.ticket_number).all())

    rooms = db.query(Room).order_by(Room.base_price_usd.asc()).all()
    if not rooms:
        raise RuntimeError("No hay habitaciones (Room). Ejecutá seed_hotel.py primero.")

    rate = exchange_rate_service.get_current_rate(db)["rate"]
    today = date.today()
    now = datetime.now()

    # 1) Equipo
    for name, role in _STAFF_SEED[:N_STAFF]:
        db.add(StaffMember(name=name, phone=_phone(), role=role, active=True, is_demo=True))
    db.commit()

    # 2) Contactos
    contacts: List[Contact] = []
    used_phones = set()
    for _ in range(N_CONTACTS):
        first = _RNG.choice(_FIRST_NAMES)
        last = _RNG.choice(_LAST_NAMES)
        phone = _phone()
        while phone in used_phones:
            phone = _phone()
        used_phones.add(phone)
        has_email = _RNG.random() < 0.7
        email = None
        if has_email:
            email = f"{first.lower()}.{last.lower()}{_RNG.randint(1, 99)}@{_RNG.choice(_EMAIL_DOMAINS)}"
            email = email.replace("í", "i").replace("é", "e").replace("á", "a").replace("ó", "o").replace("ú", "u")
        first_contact = now - timedelta(days=_RNG.randint(1, 210))
        c = Contact(
            phone_number=phone, email=email,
            first_name=first, last_name=last, full_name=f"{first} {last}",
            first_contact_date=first_contact, last_interaction_date=first_contact,
            contact_type="lead", is_active=True, is_demo=True,
        )
        db.add(c)
        contacts.append(c)
    db.commit()
    for c in contacts:
        db.refresh(c)

    # 3) Reservas distribuidas en el tiempo.
    #    50% pasadas (completed), 20% en curso/próximas 2 semanas, 30% futuras (confirmed).
    session_counter = 0
    bookings: List[Booking] = []
    for i in range(N_BOOKINGS):
        contact = _RNG.choice(contacts)
        room = _RNG.choice(rooms)
        nights = _RNG.choice([2, 2, 3, 3, 4, 5, 7])
        bucket = _RNG.random()
        if bucket < 0.50:           # pasada
            check_in = today - timedelta(days=_RNG.randint(nights + 1, 180))
            status = "completed"
        elif bucket < 0.70:         # en curso / próximas 2 semanas
            check_in = today + timedelta(days=_RNG.randint(-2, 14))
            status = "confirmed"
        else:                       # futura (próximo semestre)
            check_in = today + timedelta(days=_RNG.randint(15, 180))
            status = "confirmed"
        check_out = check_in + timedelta(days=nights)

        # ~8% canceladas (de cualquier bucket).
        if _RNG.random() < 0.08:
            status = "cancelled"

        # Precio (USD fuente de verdad). ~15% con promo aplicable.
        base_total_usd = round(room.base_price_usd * nights, 2)
        total_usd = base_total_usd
        full_price_usd = None
        promo_name = None
        if _RNG.random() < 0.15:
            best = promotions_service.mejor_promo(db, room.base_price_usd, nights)
            if best:
                total_usd = best["final_price_usd"]
                full_price_usd = best["full_price_usd"]
                promo_name = best["promo_name"]

        guests = _RNG.choice([1, 2, 2, 2, 3])
        children = _RNG.choice([0, 0, 0, 1, 2]) if room.capacity >= 3 else 0
        session_counter += 1
        session_id = f"demo-{session_counter:04d}"
        source = _RNG.choice(["web", "web", "agente", "agente", "agente"])

        b = Booking(
            code=_code("HTL-"),
            room_id=room.id,
            contact_id=contact.id,
            session_id=session_id,
            guest_name=contact.full_name,
            guest_email=contact.email,
            guest_phone=contact.phone_number,
            check_in=check_in, check_out=check_out,
            guests=guests, children=children, infants=0, nights=nights,
            total_price_usd=total_usd,
            total_price_ars=round(total_usd * rate, 2),
            promo_name=promo_name, full_price_usd=full_price_usd,
            status=status, payment_status="paid", source=source,
            generated_by="aura", created_at=check_in - timedelta(days=_RNG.randint(2, 40)),
            is_demo=True,
        )
        db.add(b)
        bookings.append(b)
    db.commit()
    for b in bookings:
        db.refresh(b)

    # Asignar unidad física a reservas activas/futuras no canceladas.
    _assign_units(db, bookings, today)

    # 4) Leads (mezcla de contactos con y sin reserva).
    for _ in range(N_LEADS):
        contact = _RNG.choice(contacts)
        lead_type = _RNG.choices(["CALIENTE", "TIBIO", "FRIO"], weights=[3, 4, 3])[0]
        score = {"CALIENTE": _RNG.randint(8, 10), "TIBIO": _RNG.randint(5, 7), "FRIO": _RNG.randint(1, 4)}[lead_type]
        created = now - timedelta(days=_RNG.randint(1, 180))
        db.add(Lead(
            session_id=f"demo-lead-{_RNG.randint(1000, 9999)}",
            contact_id=contact.id,
            channel=_RNG.choice(["web", "whatsapp"]),
            generated_by="aura",
            name=contact.first_name, last_name=contact.last_name,
            phone=contact.phone_number, email=contact.email,
            lead_type=lead_type, interest_score=score,
            obstacle=_RNG.choice(_OBSTACLES), contact_readiness=(lead_type == "CALIENTE"),
            main_interest=_RNG.choice(_LEAD_INTERESTS),
            kanban_stage=_RNG.choice(["new", "new", "contacted", "won", "lost"]),
            status=_RNG.choice(["active", "active", "contacted", "converted", "inactive"]),
            created_at=created, updated_at=created, is_demo=True,
        ))
    db.commit()

    # 5) Conversaciones + mensajes (vinculadas a contactos; algunas a una reserva).
    for _ in range(N_CONVERSATIONS):
        contact = _RNG.choice(contacts)
        started = now - timedelta(days=_RNG.randint(1, 180), hours=_RNG.randint(0, 23))
        channel = _RNG.choice(["web", "whatsapp"])
        ctx_type = _RNG.choice(["pre_sale", "pre_sale", "post_sale"])
        sess = f"demo-conv-{_RNG.randint(10000, 99999)}"
        n_msgs = _RNG.randint(4, 12)
        conv = Conversation(
            session_id=sess, contact_id=contact.id,
            context_type=ctx_type, channel=channel,
            started_at=started, last_message_at=started + timedelta(minutes=n_msgs * 2),
            status=_RNG.choice(["completed", "completed", "active", "abandoned"]),
            message_count=n_msgs, is_demo=True,
        )
        db.add(conv)
        db.flush()  # para tener conv.id
        t = started
        for seq in range(n_msgs):
            is_user = (seq % 2 == 0)
            content = _RNG.choice(_USER_TURNS if is_user else _ASSISTANT_TURNS)
            t = t + timedelta(minutes=_RNG.randint(1, 4))
            db.add(ConversationMessage(
                conversation_id=conv.id, session_id=sess,
                role="user" if is_user else "assistant",
                content=content, sequence_number=seq + 1,
                created_at=t, context_type=ctx_type, is_demo=True,
            ))
    db.commit()

    # 6) Tickets de post-venta (contra reservas pasadas o en curso).
    elegibles = [b for b in bookings if b.status != "cancelled" and b.check_in <= today + timedelta(days=7)]
    _RNG.shuffle(elegibles)
    for b in elegibles[:N_TICKETS]:
        subject, category = _RNG.choice(_TICKET_SUBJECTS)
        escalated = _RNG.random() < 0.3
        status = "escalated" if escalated else _RNG.choice(["resolved", "resolved", "open", "in_progress"])
        created = (datetime.combine(b.check_in, datetime.min.time())
                   + timedelta(days=_RNG.randint(0, max(1, b.nights))))
        db.add(HotelTicket(
            ticket_number=_code("HT-", 6),
            booking_id=b.id, session_id=b.session_id or f"demo-tk-{b.id}",
            subject=subject, category=category,
            priority=_RNG.choice(["low", "medium", "medium", "high"]),
            status=status,
            description=subject,
            auto_resolved_by_agent=(None if escalated else "Resuelto automáticamente por Aura."),
            escalated=1 if escalated else 0,
            created_at=created, updated_at=created, is_demo=True,
        ))
    db.commit()

    # 7) Restaurante: carta + pedidos + folios + preferencias dietéticas.
    _seed_restaurant(db, contacts, bookings, today, rate)

    # 8) Recalcular métricas de cada contacto (fuente de verdad = registros reales).
    for c in contacts:
        try:
            contact_service.update_contact_metrics(c.id, db)
        except Exception as e:  # noqa: BLE001
            logger.warning("update_contact_metrics demo falló", contact_id=c.id, error=str(e))

    result = counts(db)
    logger.info("Demo data populated", **{k: result[k] for k in result if k != "has_data"})
    return {k: result[k] for k in result if k != "has_data"}


def _assign_units(db: Session, bookings: List[Booking], today: date) -> None:
    """Asigna una RoomUnit libre a las reservas activas/futuras no canceladas."""
    pending = sorted(
        [b for b in bookings if b.room_unit_id is None and b.check_out >= today and b.status != "cancelled"],
        key=lambda x: x.check_in,
    )
    for b in pending:
        units = (
            db.query(RoomUnit)
            .filter(RoomUnit.room_id == b.room_id, RoomUnit.status == "available")
            .order_by(RoomUnit.number.asc())
            .all()
        )
        occupied = {
            x.room_unit_id
            for x in db.query(Booking).filter(
                Booking.room_id == b.room_id,
                Booking.room_unit_id.isnot(None),
                Booking.check_in < b.check_out,
                Booking.check_out > b.check_in,
                Booking.status != "cancelled",
            )
        }
        free = next((u for u in units if u.id not in occupied), None)
        if free:
            b.room_unit_id = free.id
    db.commit()


# Preferencias posibles para sembrar en ~30% de los contactos. Mezcla dietas y
# alergias a propósito; `_split_prefs` las separa en los campos correctos (las
# alergias son seguridad alimentaria y van aparte de las dietas).
_DIETARY_POOL = [
    ["vegetariano"], ["sin_tacc"], ["vegano"], ["vegetariano", "sin_tacc"],
    ["alergia_frutos_secos"], ["sin_lactosa"], ["alergia_mariscos", "vegetariano"],
]


def _split_prefs(items: List[str]) -> Dict[str, List[str]]:
    """Separa una lista de preferencias en {'dietary': [...], 'allergies': [...]}.

    Reutiliza la misma clasificación que el flujo en vivo (`_clasificar_preferencia`)
    para que el seed y el agente coincidan. A las alergias les quita el prefijo
    'alergia_' para guardar el alérgeno limpio (ej: 'alergia_frutos_secos' → 'frutos_secos').
    """
    from app.services.hotel_tools import _clasificar_preferencia

    dietary: List[str] = []
    allergies: List[str] = []
    for raw in items:
        if _clasificar_preferencia(raw) == "allergies":
            allergies.append(raw.replace("alergia_", "", 1))
        else:
            dietary.append(raw)
    out: Dict[str, List[str]] = {}
    if dietary:
        out["dietary"] = dietary
    if allergies:
        out["allergies"] = allergies
    return out

# Notas posibles de pedidos.
_ORDER_NOTES = [None, None, "Sin sal, por favor.", "Para compartir.", "Bien cocido.", "Sin picante."]


def _seed_restaurant(db: Session, contacts: List[Contact], bookings: List[Booking],
                     today: date, rate: float) -> None:
    """Siembra la carta real, pedidos demo (con folios) y preferencias dietéticas."""
    import json

    # 1) Carta (MenuItem) — solo si no hay carta demo ya (clear la borró).
    menu_rows = menu_for_seed(rate)
    menu_items: List[MenuItem] = []
    for row in menu_rows:
        mi = MenuItem(
            name=row["name"], description=row["description"], category=row["category"],
            price_usd=row["price_usd"], image_url=row["image_url"],
            allergens=row["allergens"], tags=row["tags"],
            available=True, status="active", only_dinner=row["only_dinner"],
            is_demo=True,
        )
        db.add(mi)
        menu_items.append(mi)
    db.commit()
    for mi in menu_items:
        db.refresh(mi)

    # 2) Preferencias en ~30% de los contactos. Dietas y alergias quedan separadas.
    for c in contacts:
        if _RNG.random() < 0.30:
            picked = _RNG.choice(_DIETARY_POOL)
            c.preferences = json.dumps(_split_prefs(picked), ensure_ascii=False)
    db.commit()

    # 3) Pedidos demo. Reservas en curso → algunos al folio (ExtraCharge).
    in_house = [b for b in bookings
                if b.status != "cancelled" and b.check_in <= today <= b.check_out]

    # 2b) Garantía para la demo: al menos UN huésped alojado hoy debe tener una alergia
    # registrada, para poder mostrar siempre el flujo de seguridad alimentaria del agente.
    if in_house:
        demo_booking = in_house[0]
        demo_contact = db.query(Contact).filter(Contact.id == demo_booking.contact_id).first()
        if demo_contact:
            demo_contact.preferences = json.dumps(
                _split_prefs(["alergia_frutos_secos", "vegetariano"]), ensure_ascii=False
            )
            db.commit()
    past = [b for b in bookings if b.status == "completed"]
    N_ORDERS = 25
    for i in range(N_ORDERS):
        # 60% de pedidos ligados a una reserva (en curso o pasada); 40% "de afuera".
        booking = None
        if _RNG.random() < 0.6 and (in_house or past):
            booking = _RNG.choice(in_house or past)
        contact = booking and db.query(Contact).filter(Contact.id == booking.contact_id).first()
        if contact is None:
            contact = _RNG.choice(contacts)

        # Armar 1-4 líneas.
        chosen = _RNG.sample(menu_items, _RNG.randint(1, 4))
        items = [{"menu_item_id": mi.id, "qty": _RNG.choice([1, 1, 2]), "notes": None} for mi in chosen]
        total_usd = round(sum(
            next(m for m in menu_items if m.id == it["menu_item_id"]).price_usd * it["qty"]
            for it in items
        ), 2)

        is_in_house = booking is not None and booking in in_house
        fulfillment = _RNG.choice(["room_service", "salon", "retiro"]) if is_in_house else _RNG.choice(["salon", "retiro"])
        payment_mode = "folio" if (is_in_house and _RNG.random() < 0.7) else "link"
        channel = _RNG.choice(["web", "whatsapp"])
        status = _RNG.choice(["entregado", "entregado", "confirmado", "en_preparacion", "pendiente"])
        created = (datetime.combine(booking.check_in, datetime.min.time()) + timedelta(days=_RNG.randint(0, max(1, booking.nights)))
                   if booking else now_minus_days(_RNG.randint(0, 60)))

        order = RestaurantOrder(
            order_code=_code("RST-"),
            contact_id=contact.id if contact else None,
            booking_id=booking.id if booking else None,
            session_id=(booking.session_id if booking else f"demo-rst-{i}"),
            channel=channel, fulfillment=fulfillment, payment_mode=payment_mode,
            total_usd=total_usd, total_ars=round(total_usd * rate, 2),
            status=status, guest_name=(contact.full_name if contact else None),
            notes=_RNG.choice(_ORDER_NOTES), created_at=created, updated_at=created,
            is_demo=True,
        )
        order.items = [
            OrderItem(
                menu_item_id=it["menu_item_id"],
                name_snapshot=next(m for m in menu_items if m.id == it["menu_item_id"]).name,
                qty=it["qty"],
                unit_price_usd=next(m for m in menu_items if m.id == it["menu_item_id"]).price_usd,
            )
            for it in items
        ]
        db.add(order)
        db.flush()

        # Folio: si es room charge sobre reserva en curso.
        if payment_mode == "folio" and booking is not None:
            db.add(ExtraCharge(
                booking_id=booking.id, order_id=order.id, category="restaurant",
                description=f"Pedido {order.order_code}",
                amount_usd=total_usd, status="pendiente",
                created_at=created, is_demo=True,
            ))
    db.commit()


def now_minus_days(days: int) -> datetime:
    return datetime.now() - timedelta(days=days)
