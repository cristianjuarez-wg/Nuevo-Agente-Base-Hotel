"""
A3 — get_contact_360 devuelve los tickets REALES del contacto (antes era [] hardcodeado).
"""
from datetime import date, timedelta

from app.models.contact import Contact
from app.models.hotel import Room, Booking, HotelTicket
from app.services.contact_service import contact_service


def test_get_contact_360_incluye_tickets_reales(db):
    c = Contact(full_name="Tick Test", first_name="Tick", phone_number="+5491990002001")
    db.add(c); db.commit(); db.refresh(c)
    room = Room(room_type="King", capacity=2, base_price_usd=120, base_price_ars=126000,
                total_units=1, status="active")
    db.add(room); db.commit(); db.refresh(room)
    b = Booking(code="HTL-T360", room_id=room.id, contact_id=c.id, guest_name="Tick Test",
                check_in=date.today() - timedelta(days=5), check_out=date.today() - timedelta(days=3),
                guests=2, nights=2, total_price_usd=240, total_price_ars=252000, status="confirmed")
    db.add(b); db.commit(); db.refresh(b)
    db.add(HotelTicket(ticket_number="HT-360A", session_id="seed", booking_id=b.id,
                       subject="el aire no anda", category="complaint", status="resolved",
                       description="aire", resolution_note="se arregló"))
    # Un ticket de restaurante NO debe aparecer (avisos a cocina, no reclamos del huésped).
    db.add(HotelTicket(ticket_number="HT-360R", session_id="seed", booking_id=b.id,
                       subject="pedido cocina", category="restaurant", status="resolved",
                       description="cocina"))
    db.commit()

    result = contact_service.get_contact_360(c.id, db)
    subjects = [t["subject"] for t in result["tickets"]]
    assert "el aire no anda" in subjects           # ticket real presente (antes era [])
    assert "pedido cocina" not in subjects          # el de restaurante se excluye
    assert result["packages"] == []                 # packages sigue vacío (turismo retirado)
