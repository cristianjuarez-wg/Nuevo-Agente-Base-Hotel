"""
Fase 1 — post-venta ahora recibe el perfil del huésped (antes NO).

Verifica: (a) con un huésped recurrente el prompt del post-venta incluye el PERFIL DEL HUÉSPED;
(b) REGRESIÓN: con una reserva FUTURA / primera estadía, el prompt NO empuja recurrencia (mismo
comportamiento que antes de la Fase 1), aunque ahora se inyecte el bloque.
"""
from datetime import date, timedelta

from app.models.contact import Contact
from app.models.hotel import Room, Booking
from app.services.hotel_postsale import HotelPostSaleService
from app.services.hotel_postsale_orchestrator import HotelPostSaleSDKOrchestrator


def _room(db):
    r = Room(room_type="King", capacity=2, base_price_usd=120, base_price_ars=126000,
             total_units=1, status="active")
    db.add(r); db.commit(); db.refresh(r)
    return r


def _booking(db, contact_id, code, *, future):
    if future:
        ci, co = date.today() + timedelta(days=20), date.today() + timedelta(days=22)
    else:
        ci, co = date.today() - timedelta(days=30), date.today() - timedelta(days=28)
    b = Booking(code=code, room_id=_room(db).id, contact_id=contact_id, guest_name="Marta Test",
                check_in=ci, check_out=co, guests=2, nights=2, total_price_usd=240,
                total_price_ars=252000, status="confirmed")
    db.add(b); db.commit(); db.refresh(b)
    return b


def test_postsale_recurrente_incluye_perfil(db):
    c = Contact(full_name="Marta Test", first_name="Marta", phone_number="+5491880000101")
    db.add(c); db.commit(); db.refresh(c)
    # Una estadía PASADA → recurrente/ya se hospedó.
    _booking(db, c.id, "HTL-PAST", future=False)
    # Y la reserva actual del contexto (otra, futura o presente da igual para el bloque).
    current = _booking(db, c.id, "HTL-CURR", future=False)

    orch = HotelPostSaleSDKOrchestrator()
    service = HotelPostSaleService(db)
    prompt = orch._build_instructions(service, current, history=[], session_id="wa_5491170000001")

    assert "PERFIL DEL HUÉSPED" in prompt, "el post-venta ahora debe recibir el perfil del huésped"
    assert "hospedó" in prompt or "RECURRENTE" in prompt


def test_postsale_primera_estadia_futura_no_fuerza_recurrencia(db):
    """REGRESIÓN: sin historial previo y reserva FUTURA, no debe aparecer perfil de recurrencia."""
    c = Contact(full_name="Nico Nuevo", first_name="Nico", phone_number="+5491880000102")
    db.add(c); db.commit(); db.refresh(c)
    current = _booking(db, c.id, "HTL-FUT", future=True)  # única reserva, futura

    orch = HotelPostSaleSDKOrchestrator()
    service = HotelPostSaleService(db)
    prompt = orch._build_instructions(service, current, history=[], session_id="wa_5491170000002")

    # Lo esencial: el bloque de PERFIL no debe marcar al huésped como recurrente ni "ya se hospedó".
    # (Nota: la palabra RECURRENTE aparece en la INSTRUCCIÓN reescrita del prompt; por eso chequeamos
    # las frases EXACTAS del render de perfil, no la palabra suelta.)
    assert "huésped RECURRENTE:" not in prompt
    assert "Ya se hospedó antes" not in prompt
    # La instrucción reescrita sigue prohibiendo asumir que vuelve.
    assert "NO asumas recurrencia" in prompt
    # Y la etapa futura está marcada en el contexto de la reserva.
    assert "FUTURA" in prompt
