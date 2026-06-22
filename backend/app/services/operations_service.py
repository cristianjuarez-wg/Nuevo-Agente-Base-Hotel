"""
Servicio de OPERACIONES — el "empleado digital" (Fase 4).

Centraliza el ciclo de vida operativo de un ticket de servicio, separado del orquestador
para no inflarlo:

  intake (huésped o staff) → classify_and_assign → notify_staff_assignment
      → [staff resuelve] mark_pre_resolved → notify_guest_validation
      → [huésped valida] guest_validate → resuelto

Decisiones:
- La ASIGNACIÓN es por ÁREA del equipo (StaffMember.area). El agente puede pasar un
  `area_hint`; si no, clasificamos por palabras clave sobre el texto del ticket.
- La DOBLE VALIDACIÓN aplica solo si hay un huésped CONTACTABLE (reserva con teléfono o
  sesión de WhatsApp). Tareas internas (fuga en el garage, wake-up call) se cierran directo.
- Los envíos de WhatsApp son best-effort: si el canal no está configurado (local sin
  Twilio), el flujo sigue y el estado igual avanza (se ve en el backoffice).

Estados de status usados acá: "asignado", "pre_resuelto", "resuelto" (ver HotelTicket).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.hotel import HotelTicket, Booking, TicketEvent
from app.models.staff import StaffMember
from app.services.whatsapp_service import whatsapp_service

logger = get_logger(__name__)

# Nombre legible del agente para la bitácora (lo gestionado por la IA).
AGENT_NAME = "Aura"


def log_event(db: Session, ticket: HotelTicket, action: str,
              actor_type: str = "agent", actor_name: Optional[str] = None,
              note: Optional[str] = None) -> None:
    """Registra una acción del ticket en su bitácora (quién hizo qué).

    actor_type: "agent" (Aura) | "staff" (equipo) | "human" (backoffice) | "guest".
    Best-effort: un fallo de la bitácora nunca debe romper la transición del ticket.
    """
    try:
        if actor_type == "agent" and not actor_name:
            actor_name = AGENT_NAME
        db.add(TicketEvent(
            ticket_id=ticket.id, actor_type=actor_type,
            actor_name=actor_name, action=action, note=(note or None),
        ))
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo registrar el evento del ticket",
                       ticket_number=getattr(ticket, "ticket_number", None), error=str(e))

# Áreas operativas válidas (espejo de StaffMember.area y del `tipo` de solicitar_servicio).
AREAS = ("mantenimiento", "recepcion", "housekeeping", "general")

# Mapa del `tipo` de solicitar_servicio → área del equipo.
_TIPO_TO_AREA = {
    "mantenimiento": "mantenimiento",
    "housekeeping": "housekeeping",
    "recepcion": "recepcion",
    "room_service": "recepcion",
    "general": "general",
}

# Clasificación por palabras clave (fallback cuando no hay area_hint claro).
_AREA_KEYWORDS = {
    "mantenimiento": (
        "aire", "calefacc", "calefaccion", "ac ", "a/c", "tv", "televis", "wifi", "wi-fi",
        "luz", "lámpara", "lampara", "enchufe", "canilla", "grifo", "ducha", "agua caliente",
        "caño", "cano", "tuber", "fuga", "perdida de agua", "pérdida", "cerradura", "puerta",
        "ventana", "calefón", "calefon", "termo", "no funciona", "no anda", "roto", "rota",
        "gotea", "inundac", "humedad",
    ),
    "housekeeping": (
        "toalla", "toallas", "limpieza", "limpiar", "amenities", "shampoo", "jabón", "jabon",
        "sábana", "sabana", "almohada", "frazada", "manta", "papel higiénico", "papel higienico",
        "blanco", "blancos", "mucama",
    ),
    "recepcion": (
        "llave", "tarjeta", "check", "checkout", "check-out", "late checkout", "factura",
        "wake", "despertar", "llamen", "llamar", "taxi", "remis", "remís", "equipaje",
        "valija", "valijas", "guardar", "información", "informacion",
    ),
}


def classify_area(text: str, area_hint: Optional[str] = None) -> str:
    """Decide el área operativa de un ticket. Prioriza el hint del agente; si no, keywords."""
    if area_hint:
        hint = area_hint.strip().lower()
        if hint in AREAS:
            return hint
        mapped = _TIPO_TO_AREA.get(hint)
        if mapped:
            return mapped
    low = (text or "").lower()
    for area, kws in _AREA_KEYWORDS.items():
        if any(kw in low for kw in kws):
            return area
    return "general"


def _pick_staff(db: Session, area: str) -> Optional[StaffMember]:
    """Elige el StaffMember activo del área. Round-robin simple: el de menor carga abierta.

    Cae a "general" si el área no tiene a nadie, y a cualquier staff activo como último recurso.
    """
    def _candidates(a: str):
        return (
            db.query(StaffMember)
            .filter(StaffMember.role == "staff", StaffMember.active == True, StaffMember.area == a)  # noqa: E712
            .all()
        )

    pool = _candidates(area) or (_candidates("general") if area != "general" else [])
    if not pool:
        # Último recurso: cualquier staff activo (no owner).
        pool = (
            db.query(StaffMember)
            .filter(StaffMember.role == "staff", StaffMember.active == True)  # noqa: E712
            .all()
        )
    if not pool:
        return None

    # Balanceo simple: quien tenga menos tickets "asignado"/"pre_resuelto" encima.
    def _load(s: StaffMember) -> int:
        return (
            db.query(HotelTicket)
            .filter(
                HotelTicket.assigned_staff_id == s.id,
                HotelTicket.status.in_(["asignado", "pre_resuelto"]),
            )
            .count()
        )

    return min(pool, key=_load)


def classify_and_assign(
    db: Session, ticket: HotelTicket, area_hint: Optional[str] = None,
    actor_type: str = "agent", actor_name: Optional[str] = None,
) -> Optional[StaffMember]:
    """Clasifica el ticket por área y lo asigna a un miembro del equipo.

    Setea assigned_area / assigned_staff_id y pasa el status a "asignado". Devuelve el
    StaffMember asignado (o None si el equipo no tiene a nadie cargado todavía).
    `actor_type` indica quién enrutó: "agent" (Aura, por defecto) o "human" (backoffice).
    """
    text = f"{ticket.subject or ''} {ticket.description or ''}"
    area = classify_area(text, area_hint)
    staff = _pick_staff(db, area)

    ticket.assigned_area = area
    ticket.status = "asignado"
    if staff:
        ticket.assigned_staff_id = staff.id
    db.commit()

    area_label = area.capitalize()
    note = f"→ {area_label}" + (f" · {staff.name}" if staff else " (sin nadie del área)")
    log_event(db, ticket, "assigned", actor_type=actor_type, actor_name=actor_name, note=note)

    logger.info(
        "Ticket operativo asignado",
        ticket_number=ticket.ticket_number, area=area,
        assigned_to=(staff.name if staff else None),
    )
    return staff


def _room_label(ticket: HotelTicket) -> str:
    """Etiqueta de la habitación del ticket, si la reserva tiene una unidad asignada."""
    booking = ticket.booking
    if booking and booking.room_unit and booking.room_unit.number:
        return f"habitación {booking.room_unit.number}"
    if booking and booking.guest_name:
        return f"reserva de {booking.guest_name}"
    return "tarea general"


def notify_staff_assignment(staff: Optional[StaffMember], ticket: HotelTicket) -> bool:
    """Avisa por WhatsApp al staff asignado, con el detalle y cómo cerrar el caso.

    Best-effort: si no hay staff o el canal no está configurado, devuelve False sin romper.
    """
    if not staff or not staff.phone:
        logger.info("Sin staff asignable para notificar", ticket_number=ticket.ticket_number)
        return False

    where = _room_label(ticket)
    detail = (ticket.description or ticket.subject or "").strip()
    body = (
        f"🛎️ *Nuevo pedido* — {where}\n"
        f"Área: {ticket.assigned_area or 'general'} · Ticket {ticket.ticket_number}\n\n"
        f"“{detail}”\n\n"
        f"Cuando lo resuelvas, respondé *LISTO {ticket.ticket_number}* "
        f"o mandá un audio diciendo qué resolviste (ej.: «reparado el aire de la 401»)."
    )
    ok = whatsapp_service.send_text(staff.phone, body)
    logger.info(
        "Notificación al staff", ticket_number=ticket.ticket_number,
        staff=staff.name, sent=ok,
    )
    return ok


# ---------------------------------------------------------------------------
# Loop de doble validación (Fase 4c) — el staff resuelve, el huésped valida.
# ---------------------------------------------------------------------------
def _guest_whatsapp_phone(ticket: HotelTicket) -> Optional[str]:
    """Teléfono del huésped para avisarle por WhatsApp, o None si no hay canal de WhatsApp.

    Solo aplica a tickets originados en WhatsApp (session wa_...) o con teléfono en la reserva.
    """
    booking = ticket.booking
    if ticket.session_id and ticket.session_id.startswith("wa_"):
        return "+" + ticket.session_id[len("wa_"):]
    if booking and booking.guest_phone:
        return booking.guest_phone
    return None


def _guest_can_validate(ticket: HotelTicket) -> bool:
    """True si hay un huésped que puede validar la resolución (por chat web o WhatsApp).

    Un ticket originado por el huésped tiene su `session_id` de conversación (web o wa); por
    ahí mismo va a validar. Tickets internos del staff (session 'staff', sin huésped) NO se
    validan: se cierran directo.
    """
    if ticket.origin == "staff":
        return False
    sid = ticket.session_id or ""
    return bool(sid and sid != "staff")


def mark_pre_resolved(
    db: Session, ticket: HotelTicket, staff: Optional[StaffMember], note: str,
    actor_type: str = "staff", actor_name: Optional[str] = None,
) -> str:
    """El staff marca el ticket como resuelto → queda pre_resuelto a la espera del huésped.

    Si NO hay huésped contactable (tarea interna), se cierra directo a "resuelto".
    `actor_type` = "staff" (WhatsApp) o "human" (botón del backoffice). Devuelve el status final.
    """
    ticket.resolution_note = (note or "").strip()[:1000]
    if staff:
        ticket.resolved_by_staff_id = staff.id
    who = actor_name or (staff.name if staff else None)
    clean_note = (note or "").strip()[:120]

    if _guest_can_validate(ticket):
        ticket.status = "pre_resuelto"
        db.commit()
        log_event(db, ticket, "pre_resolved", actor_type=actor_type, actor_name=who, note=clean_note)
        # Si el huésped tiene WhatsApp, le mandamos el aviso ahora. Si vino por chat web,
        # verá el aviso en su próximo mensaje (lo cierra el flujo de validación del huésped).
        phone = _guest_whatsapp_phone(ticket)
        if phone:
            notify_guest_validation(ticket, phone)
        logger.info("Ticket pre-resuelto (esperando validación del huésped)",
                    ticket_number=ticket.ticket_number)
    else:
        ticket.status = "resuelto"
        db.commit()
        log_event(db, ticket, "resolved", actor_type=actor_type, actor_name=who,
                  note=(clean_note or "Sin huésped a validar"))
        logger.info("Ticket resuelto directo (sin huésped a validar)",
                    ticket_number=ticket.ticket_number)
    return ticket.status


def notify_guest_validation(ticket: HotelTicket, phone: Optional[str] = None) -> bool:
    """Avisa al huésped que su pedido se resolvió y le pide confirmar."""
    phone = phone or _guest_whatsapp_phone(ticket)
    if not phone:
        return False
    where = _room_label(ticket)
    note = (ticket.resolution_note or "tu pedido").strip()
    body = (
        f"✅ ¡Listo! Resolvimos tu pedido en {where}: “{note}”.\n\n"
        f"¿Quedó todo bien? Respondé *SÍ* para confirmar, o contanos si seguís con el "
        f"inconveniente y lo retomamos enseguida. 🙌"
    )
    return whatsapp_service.send_text(phone, body)


def guest_validate(db: Session, ticket: HotelTicket, ok: bool) -> str:
    """El huésped valida (o no) la resolución.

    ok=True  → "resuelto" definitivo (guest_validated=1).
    ok=False → reabre como "asignado" y re-notifica al staff.
    Devuelve el status final.
    """
    if ok:
        ticket.status = "resuelto"
        ticket.guest_validated = 1
        db.commit()
        log_event(db, ticket, "validated", actor_type="guest", actor_name="Huésped",
                  note="Confirmó que quedó resuelto")
        logger.info("Ticket validado por el huésped → resuelto",
                    ticket_number=ticket.ticket_number)
    else:
        ticket.status = "asignado"
        db.commit()
        log_event(db, ticket, "reopened", actor_type="guest", actor_name="Huésped",
                  note="El huésped indica que sigue el problema")
        staff = (
            db.query(StaffMember).filter(StaffMember.id == ticket.assigned_staff_id).first()
            if ticket.assigned_staff_id else None
        )
        if staff:
            body = (
                f"⚠️ El huésped indica que el problema del ticket {ticket.ticket_number} "
                f"({_room_label(ticket)}) sigue sin resolverse. ¿Podés revisarlo de nuevo? "
                f"Cuando esté, respondé *LISTO {ticket.ticket_number}*."
            )
            whatsapp_service.send_text(staff.phone, body)
        logger.info("Ticket rechazado por el huésped → reabierto",
                    ticket_number=ticket.ticket_number)
    return ticket.status


# ---------------------------------------------------------------------------
# Intake originado por el STAFF (Fase 4b) — crear y resolver tickets desde el equipo.
# ---------------------------------------------------------------------------
import re as _re
import secrets as _secrets
import string as _string

_TICKET_RE = _re.compile(r"\bHT-[A-Z0-9]{6}\b")
_ROOM_RE = _re.compile(r"\b(?:hab(?:itaci[oó]n)?\.?\s*)?(\d{2,4})\b", _re.IGNORECASE)


def _gen_ticket_number() -> str:
    suffix = "".join(_secrets.choice(_string.ascii_uppercase + _string.digits) for _ in range(6))
    return f"HT-{suffix}"


def create_staff_ticket(
    db: Session, description: str, area_hint: Optional[str] = None,
    session_id: str = "", subject: Optional[str] = None,
) -> tuple[HotelTicket, Optional[StaffMember]]:
    """Crea un ticket ORIGINADO por el staff (incidencia/pedido interno) y lo asigna.

    Sin booking (tarea interna). Devuelve (ticket, staff_asignado).
    """
    ticket = HotelTicket(
        ticket_number=_gen_ticket_number(),
        booking_id=None,
        session_id=session_id or "staff",
        subject=(subject or (description or "")[:80] or "Incidencia operativa"),
        category="service_request",
        priority="medium",
        status="open",
        description=(description or "")[:1000],
        origin="staff",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    # El staff originó la incidencia hablándole a Aura; Aura la registró.
    log_event(db, ticket, "created", actor_type="agent",
              note=f"Incidencia reportada por el equipo: {(description or '')[:80]}")
    staff = classify_and_assign(db, ticket, area_hint=area_hint)
    notify_staff_assignment(staff, ticket)
    logger.info("Ticket originado por staff", ticket_number=ticket.ticket_number,
                area=ticket.assigned_area)
    return ticket, staff


def match_open_ticket(
    db: Session, reference: str, staff: Optional[StaffMember] = None
) -> tuple[Optional[HotelTicket], list]:
    """Busca el ticket abierto/asignado que el staff quiere resolver.

    Estrategia:
      1. Si el texto trae un número HT-XXXXXX, match directo.
      2. Si trae un número de habitación, buscar entre los tickets 'asignado' cuya reserva
         tenga esa habitación (acotado al área del staff si se conoce).
      3. Si el staff tiene UN solo ticket asignado, devolverlo.
    Devuelve (ticket | None, candidatos) — si hay >1 candidato, el ticket es None y el
    orquestador debe desambiguar.
    """
    text = (reference or "").upper()

    m = _TICKET_RE.search(text)
    if m:
        t = db.query(HotelTicket).filter(HotelTicket.ticket_number == m.group(0)).first()
        return (t, [t] if t else [])

    base = db.query(HotelTicket).filter(HotelTicket.status == "asignado")
    if staff:
        base = base.filter(HotelTicket.assigned_staff_id == staff.id)
    open_tickets = base.order_by(HotelTicket.created_at.desc()).all()

    # Match por número de habitación.
    room_match = _ROOM_RE.search(reference or "")
    if room_match:
        room_no = room_match.group(1)
        by_room = [
            t for t in open_tickets
            if t.booking and t.booking.room_unit and str(t.booking.room_unit.number) == room_no
        ]
        if len(by_room) == 1:
            return (by_room[0], by_room)
        if len(by_room) > 1:
            return (None, by_room)

    # Único ticket asignado al staff → es ese.
    if len(open_tickets) == 1:
        return (open_tickets[0], open_tickets)

    return (None, open_tickets)


def list_staff_tickets(db: Session, staff: StaffMember) -> list:
    """Tickets activos (asignado/pre_resuelto) del staff, para '¿qué tengo pendiente?'."""
    return (
        db.query(HotelTicket)
        .filter(
            HotelTicket.assigned_staff_id == staff.id,
            HotelTicket.status.in_(["asignado", "pre_resuelto"]),
        )
        .order_by(HotelTicket.priority.desc(), HotelTicket.created_at.asc())
        .all()
    )


def find_pending_validation_ticket(db: Session, session_id: str) -> Optional[HotelTicket]:
    """Busca un ticket pre_resuelto para esta sesión (para detectar la validación del huésped).

    Busca por session_id directo y, si la sesión es de WhatsApp, también por el teléfono del
    huésped en la reserva asociada.
    """
    q = (
        db.query(HotelTicket)
        .filter(HotelTicket.status == "pre_resuelto")
        .filter(HotelTicket.session_id == session_id)
        .order_by(HotelTicket.updated_at.desc())
    )
    return q.first()
