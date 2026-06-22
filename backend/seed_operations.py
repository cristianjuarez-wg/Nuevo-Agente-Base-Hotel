"""
Seed de EJEMPLOS OPERATIVOS para la demo del "empleado digital" (Fase 4).

Crea tickets de servicio REPRESENTATIVOS del ciclo nuevo, cada uno en un estado distinto y
CON SU BITÁCORA (TicketEvent) — para que el backoffice muestre el flujo completo del agente
sin depender de generarlo todo en vivo:

  1) ASIGNADO          — Aura creó y asignó; el equipo aún no respondió.
  2) PRE-RESUELTO      — el staff lo resolvió por WhatsApp; espera validación del huésped.
  3) RESUELTO (loop)   — historia completa: Aura creó→asignó, Carlos resolvió, huésped validó.
  4) RESUELTO directo  — incidencia ORIGINADA por el staff (sin huésped a validar).
  5) REABIERTO         — el huésped rechazó la resolución; volvió al equipo.

Idempotente: usa números de ticket fijos con prefijo OPS- y no duplica. is_demo=True.
Requiere que existan staff con área (seed_staff.py) y reservas (seed_hotel/demo).
Ejecutar:  python seed_operations.py
"""
from datetime import timedelta

from app.models.database import SessionLocal
from app.models.hotel import Booking, HotelTicket, TicketEvent
from app.models.staff import StaffMember
from app.utils.timezone_utils import now_argentina


def _staff_by_area(db, area: str):
    return (
        db.query(StaffMember)
        .filter(StaffMember.role == "staff", StaffMember.active == True, StaffMember.area == area)  # noqa: E712
        .first()
    )


def _a_booking_with_room(db):
    """Una reserva confirmada con habitación asignada (para anclar el ticket a un huésped)."""
    return (
        db.query(Booking)
        .filter(Booking.status == "confirmed", Booking.room_unit_id.isnot(None))
        .first()
    )


def _any_confirmed_booking(db):
    return db.query(Booking).filter(Booking.status == "confirmed").first()


def _ticket(db, number, booking, subject, description, category="service_request"):
    """Crea (o devuelve) un ticket de demo con número fijo. Idempotente."""
    existing = db.query(HotelTicket).filter(HotelTicket.ticket_number == number).first()
    if existing:
        return existing, False
    t = HotelTicket(
        ticket_number=number,
        booking_id=booking.id if booking else None,
        session_id=(f"wa_{booking.guest_phone.lstrip('+')}" if booking and booking.guest_phone else "staff"),
        subject=subject,
        category=category,
        description=description,
        is_demo=True,
    )
    db.add(t)
    db.flush()
    return t, True


def _ev(db, ticket, minutes_ago, actor_type, actor_name, action, note):
    """Agrega un evento a la bitácora con timestamp relativo (para un timeline natural)."""
    e = TicketEvent(
        ticket_id=ticket.id, actor_type=actor_type, actor_name=actor_name,
        action=action, note=note,
    )
    db.add(e)
    db.flush()
    # Forzamos el created_at escalonado (no usamos el default 'now' para que el orden tenga sentido).
    e.created_at = now_argentina().replace(tzinfo=None) - timedelta(minutes=minutes_ago)


def seed():
    db = SessionLocal()
    try:
        maint = _staff_by_area(db, "mantenimiento")
        house = _staff_by_area(db, "housekeeping")
        recep = _staff_by_area(db, "recepcion")
        if not maint:
            print("[seed_ops] No hay staff de mantenimiento. Corré seed_staff.py primero. Abortando.")
            return

        b_room = _a_booking_with_room(db)
        b_any = b_room or _any_confirmed_booking(db)
        if not b_any:
            print("[seed_ops] No hay reservas para anclar los tickets. Abortando.")
            return

        created = 0

        # 1) ASIGNADO — esperando al equipo.
        t1, isnew = _ticket(
            db, "OPS-ASGN01", b_room or b_any,
            "Pedido de servicio (mantenimiento)",
            "El televisor de la habitación no enciende.",
        )
        if isnew:
            t1.status = "asignado"; t1.priority = "medium"; t1.origin = "guest"
            t1.assigned_area = "mantenimiento"; t1.assigned_staff_id = maint.id
            _ev(db, t1, 18, "agent", "Aura", "created", "Pedido del huésped: el TV no enciende.")
            _ev(db, t1, 17, "agent", "Aura", "assigned", f"→ Mantenimiento · {maint.name}")
            created += 1

        # 2) PRE-RESUELTO — staff resolvió, espera validación del huésped.
        t2, isnew = _ticket(
            db, "OPS-PRES01", b_room or b_any,
            "Pedido de servicio (mantenimiento)",
            "El aire acondicionado no enfría.",
        )
        if isnew:
            t2.status = "pre_resuelto"; t2.priority = "high"; t2.origin = "guest"
            t2.assigned_area = "mantenimiento"; t2.assigned_staff_id = maint.id
            t2.resolved_by_staff_id = maint.id
            t2.resolution_note = "Recargué el gas del aire y quedó enfriando bien."
            _ev(db, t2, 95, "agent", "Aura", "created", "Pedido del huésped: el aire no enfría.")
            _ev(db, t2, 94, "agent", "Aura", "assigned", f"→ Mantenimiento · {maint.name}")
            _ev(db, t2, 20, "staff", maint.name, "pre_resolved", "Recargué el gas del aire.")
            created += 1

        # 3) RESUELTO — loop completo (la historia estrella de la demo).
        t3, isnew = _ticket(
            db, "OPS-DONE01", b_room or b_any,
            "Pedido de servicio (housekeeping)",
            "Faltan toallas en la habitación.",
        )
        if isnew:
            t3.status = "resuelto"; t3.priority = "low"; t3.origin = "guest"
            t3.assigned_area = "housekeeping"
            t3.assigned_staff_id = (house.id if house else maint.id)
            t3.resolved_by_staff_id = (house.id if house else maint.id)
            t3.resolution_note = "Llevé toallas limpias y repuse amenities."
            t3.guest_validated = 1
            who = house.name if house else maint.name
            _ev(db, t3, 240, "agent", "Aura", "created", "Pedido del huésped: faltan toallas.")
            _ev(db, t3, 239, "agent", "Aura", "assigned", f"→ Housekeeping · {who}")
            _ev(db, t3, 210, "staff", who, "pre_resolved", "Llevé toallas y repuse amenities.")
            _ev(db, t3, 200, "guest", "Huésped", "validated", "Confirmó que quedó resuelto.")
            created += 1

        # 4) RESUELTO directo — incidencia ORIGINADA por el staff (sin huésped a validar).
        t4, isnew = _ticket(
            db, "OPS-STAFF1", None,
            "Incidencia (mantenimiento)",
            "Fuga de agua en las tuberías del garage, zona de estacionamiento.",
        )
        if isnew:
            t4.status = "resuelto"; t4.priority = "high"; t4.origin = "staff"
            t4.assigned_area = "mantenimiento"; t4.assigned_staff_id = maint.id
            t4.resolved_by_staff_id = maint.id
            t4.resolution_note = "Ajusté la unión que perdía; sin más pérdidas."
            _ev(db, t4, 300, "agent", "Aura", "created", "Incidencia reportada por el equipo: fuga en el garage.")
            _ev(db, t4, 299, "agent", "Aura", "assigned", f"→ Mantenimiento · {maint.name}")
            _ev(db, t4, 250, "staff", maint.name, "resolved", "Ajusté la unión que perdía.")
            created += 1

        # 5) REABIERTO — el huésped rechazó la resolución; volvió al equipo.
        t5, isnew = _ticket(
            db, "OPS-REOP01", b_room or b_any,
            "Pedido de servicio (mantenimiento)",
            "La ducha pierde agua caliente.",
        )
        if isnew:
            t5.status = "asignado"; t5.priority = "medium"; t5.origin = "guest"
            t5.assigned_area = "mantenimiento"; t5.assigned_staff_id = maint.id
            _ev(db, t5, 180, "agent", "Aura", "created", "Pedido del huésped: la ducha pierde agua caliente.")
            _ev(db, t5, 179, "agent", "Aura", "assigned", f"→ Mantenimiento · {maint.name}")
            _ev(db, t5, 120, "staff", maint.name, "pre_resolved", "Cambié el flexible de la ducha.")
            _ev(db, t5, 90, "guest", "Huésped", "reopened", "El huésped indica que sigue el problema.")
            created += 1

        db.commit()

        total_ops = db.query(HotelTicket).filter(HotelTicket.ticket_number.like("OPS-%")).count()
        print(f"[seed_ops] Ejemplos operativos: {created} creados (total OPS-: {total_ops}).")
        if created == 0:
            print("[seed_ops] (idempotente: ya existían, no se duplicó nada)")
    finally:
        db.close()


if __name__ == "__main__":
    import app.main  # noqa: F401 — registra todos los modelos antes de tocar la DB
    seed()
