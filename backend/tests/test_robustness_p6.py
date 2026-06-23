"""
Tests de los fixes de robustez P6 (hallazgos menores de la auditoría):

#1 find_staff_member: matching único (exacto + tolerante) compartido por resolve_role y
   el ruteo, para que el ruteo no rechace a un staffer reconocido por el match tolerante.
#2 get_leads_summary: un lead se cuenta cerrado solo si tiene una reserva creada EN O
   DESPUÉS del lead (no por una compra vieja del contacto).
#3 get_revenue: ingresos por estadía prorrateada (mismo criterio que ocupación).
#4 _pick_staff: un 'pre_resuelto' viejo no cuenta como carga en el round-robin.

Deterministas, sin OpenAI. Usan el fixture `db` en memoria del conftest.
"""
from datetime import date, datetime, timedelta

import pytest

_bk_seq = 0
_room_id = None


def _ensure_room(db):
    """Crea (una vez) un Room de prueba y devuelve su id (Booking.room_id es NOT NULL)."""
    global _room_id
    if _room_id is not None:
        return _room_id
    from app.models.hotel import Room
    r = Room(room_type="Test", base_price_usd=100, base_price_ars=100000,
             capacity=2, total_units=1)
    db.add(r); db.commit()
    _room_id = r.id
    return _room_id


def _mk_booking(db, contact_id, check_in, check_out, usd, created_at):
    """Crea un Booking con todos los campos NOT NULL poblados."""
    global _bk_seq
    from app.models.hotel import Booking
    _bk_seq += 1
    b = Booking(
        code=f"HTL-P6{_bk_seq:04d}", contact_id=contact_id, room_id=_ensure_room(db),
        guest_name="Test", check_in=check_in, check_out=check_out, guests=2,
        status="confirmed", total_price_usd=usd, total_price_ars=usd * 1000,
        created_at=created_at,
    )
    db.add(b); db.commit()
    return b


# ---------------------------------------------------------------------------
# #1 — find_staff_member: match tolerante compartido
# ---------------------------------------------------------------------------
class TestFindStaffMemberTolerant:
    def test_reconoce_por_match_tolerante(self, db):
        from app.models.staff import StaffMember
        from app.services.role_service import find_staff_member, resolve_role

        # Teléfono guardado SIN el "9" móvil argentino; el mensaje llega CON el 9.
        db.add(StaffMember(name="Ana", phone="+542944123456", area="recepcion",
                           role="staff", active=True))
        db.commit()

        incoming = "+5492944123456"  # mismo número con el 9
        member = find_staff_member(incoming, db)
        assert member is not None, "debe reconocerlo por el match tolerante"
        assert member.name == "Ana"
        # Y resolve_role coincide (misma fuente de verdad).
        assert resolve_role(incoming, db) == "staff"

    def test_sin_match_es_none(self, db):
        from app.services.role_service import find_staff_member
        assert find_staff_member("+5491100000000", db) is None


# ---------------------------------------------------------------------------
# #2 — get_leads_summary: cerrado = reserva creada en/después del lead
# ---------------------------------------------------------------------------
class TestLeadsConversion:
    def test_compra_vieja_no_cuenta_como_cerrado(self, db):
        from app.models.contact import Contact
        from app.models.lead import Lead
        from app.models.hotel import Booking
        from app.services import business_metrics

        c = Contact(phone_number="+5491150000001", purchases_made=1)
        db.add(c); db.commit()
        # Reserva ANTERIOR al lead (compra vieja del contacto).
        _mk_booking(db, c.id, date(2026, 1, 1), date(2026, 1, 3), 200, datetime(2026, 1, 1))
        # Lead generado DESPUÉS, sin reserva nueva.
        db.add(Lead(session_id="web-p6-a", contact_id=c.id, lead_type="FRIO", interest_score=10, created_at=datetime(2026, 6, 1)))
        db.commit()

        r = business_metrics.get_leads_summary(db, date(2026, 6, 1), date(2026, 6, 30))
        assert r["generated"] == 1
        assert r["closed"] == 0, "una compra ANTERIOR al lead no debe contar como conversión"

    def test_reserva_posterior_si_cuenta(self, db):
        from app.models.contact import Contact
        from app.models.lead import Lead
        from app.models.hotel import Booking
        from app.services import business_metrics

        c = Contact(phone_number="+5491150000002", purchases_made=1)
        db.add(c); db.commit()
        db.add(Lead(session_id="web-p6-b", contact_id=c.id, lead_type="FRIO", interest_score=10, created_at=datetime(2026, 6, 5)))
        db.commit()
        # Reserva creada DESPUÉS del lead.
        _mk_booking(db, c.id, date(2026, 7, 1), date(2026, 7, 3), 200, datetime(2026, 6, 10))

        r = business_metrics.get_leads_summary(db, date(2026, 6, 1), date(2026, 6, 30))
        assert r["closed"] == 1, "una reserva creada tras el lead SÍ es conversión"


# ---------------------------------------------------------------------------
# #3 — get_revenue: prorrateo por estadía dentro del rango
# ---------------------------------------------------------------------------
class TestRevenueProrated:
    def test_ingreso_prorrateado_por_noches_en_rango(self, db):
        from app.models.hotel import Booking
        from app.services import business_metrics

        # Estadía de 4 noches en un rango AISLADO (mar 2099, sin otros bookings de tests),
        # USD 400 → USD 100/noche. El rango cubre solo 2 noches → debe facturar USD 200.
        _mk_booking(db, None, date(2099, 3, 1), date(2099, 3, 5), 400, datetime(2026, 6, 1))

        r = business_metrics.get_revenue(db, date(2099, 3, 1), date(2099, 3, 3))
        assert r["usd"] == 200.0, "debe prorratear: 2 de 4 noches caen en el rango"
        assert r["nights"] == 2


# ---------------------------------------------------------------------------
# #4 — _pick_staff: 'pre_resuelto' viejo no cuenta como carga
# ---------------------------------------------------------------------------
class TestPickStaffStaleLoad:
    def test_pre_resuelto_viejo_no_pesa_en_balanceo(self, db):
        from app.models.staff import StaffMember
        from app.models.hotel import HotelTicket
        from app.services import operations_service

        s1 = StaffMember(name="S1", phone="+5491160000001", area="mantenimiento",
                        role="staff", active=True)
        s2 = StaffMember(name="S2", phone="+5491160000002", area="mantenimiento",
                        role="staff", active=True)
        db.add_all([s1, s2]); db.commit()

        old = datetime.now() - timedelta(days=10)  # pre_resuelto viejo (sin validar)
        # S1 tiene un pre_resuelto VIEJO (no debería contar como carga).
        db.add(HotelTicket(ticket_number="HT-P6OLD", session_id="x", subject="x",
                          category="service_request", status="pre_resuelto",
                          assigned_staff_id=s1.id, updated_at=old))
        db.commit()

        # Con el fix, S1 tiene carga 0 (su pre_resuelto es stale) → debe ser el elegido.
        chosen = operations_service._pick_staff(db, "mantenimiento")
        assert chosen is not None
        assert chosen.id == s1.id, "un pre_resuelto viejo no debe penalizar a S1 en el balanceo"
