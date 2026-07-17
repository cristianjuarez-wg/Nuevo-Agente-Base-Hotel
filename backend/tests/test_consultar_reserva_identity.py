"""
Fase 1 — Verificación de identidad en consultar_reserva.

Segundo factor de verificación: apellido o teléfono del contacto de la reserva.
"""
from datetime import date, timedelta

from app.models.contact import Contact
from app.models.hotel import Room, Booking
from app.services.hotel_tools_pkg.booking import _handle_consultar_reserva
from app.services import reservation_service


def _seed_room(db):
    room = Room(
        room_type="King",
        capacity=2,
        base_price_usd=120,
        base_price_ars=126000,
        total_units=1,
        status="active",
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


def _contact_with_last_name(db, phone, last_name):
    contact = Contact(
        phone_number=phone,
        first_name="Ana",
        last_name=last_name,
        full_name=f"Ana {last_name}",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def test_consultar_reserva_sin_factor_pide_verificacion(db):
    room = _seed_room(db)
    contact = _contact_with_last_name(db, "+5491112345670", "García")
    booking = reservation_service.create_booking(
        db,
        room_id=room.id,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guest_name="Ana García",
        guest_phone=contact.phone_number,
        guests=2,
    )
    ctx = {"db": db}
    result = _handle_consultar_reserva({"code": booking["code"]}, ctx)
    assert ("segundo factor" in result["tool_result"].lower()
            or "apellido" in result["tool_result"].lower())
    assert "booking" not in result


def test_consultar_reserva_apellido_correcto(db):
    room = _seed_room(db)
    contact = _contact_with_last_name(db, "+5491112345671", "García")
    booking = reservation_service.create_booking(
        db,
        room_id=room.id,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guest_name="Ana García",
        guest_phone=contact.phone_number,
        guests=2,
    )
    ctx = {"db": db}
    result = _handle_consultar_reserva({"code": booking["code"], "apellido": "García"}, ctx)
    assert booking["code"] in result["tool_result"]
    assert result.get("booking") is not None
    assert ctx.get("booking_code") == booking["code"]


def test_consultar_reserva_apellido_incorrecto_rechaza(db):
    room = _seed_room(db)
    contact = _contact_with_last_name(db, "+5491112345672", "García")
    booking = reservation_service.create_booking(
        db,
        room_id=room.id,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guest_name="Ana García",
        guest_phone=contact.phone_number,
        guests=2,
    )
    ctx = {"db": db}
    result = _handle_consultar_reserva({"code": booking["code"], "apellido": "Pérez"}, ctx)
    assert "no coincide" in result["tool_result"].lower()
    assert "booking" not in result


def test_consultar_reserva_telefono_correcto(db):
    room = _seed_room(db)
    contact = _contact_with_last_name(db, "+5491112345673", "García")
    booking = reservation_service.create_booking(
        db,
        room_id=room.id,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guest_name="Ana García",
        guest_phone=contact.phone_number,
        guests=2,
    )
    ctx = {"db": db}
    result = _handle_consultar_reserva({"code": booking["code"], "telefono": "1112345673"}, ctx)
    assert booking["code"] in result["tool_result"]
    assert result.get("booking") is not None


def test_consultar_reserva_apellido_normalizado_sin_tildes(db):
    room = _seed_room(db)
    contact = Contact(
        phone_number="+5491112345679",
        first_name="María",
        last_name="Gómez López",
        full_name="María Gómez López",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    booking = Booking(
        code="HTL-TEST01",
        room_id=room.id,
        contact_id=contact.id,
        guest_name="María Gómez López",
        guest_phone="+5491112345679",
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guests=2,
        nights=2,
        total_price_usd=240,
        total_price_ars=252000,
        status="confirmed",
        payment_status="paid",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    ctx = {"db": db}
    # Apellido con tildes vs sin tildes debe coincidir.
    result = _handle_consultar_reserva({"code": "HTL-TEST01", "apellido": "Gomez Lopez"}, ctx)
    assert "HTL-TEST01" in result["tool_result"]
    assert result.get("booking") is not None


def test_consultar_reserva_sin_contacto_pide_apellido(db):
    room = _seed_room(db)
    booking = Booking(
        code="HTL-TEST02",
        room_id=room.id,
        contact_id=None,
        guest_name="Pedro Sincontacto",
        guest_phone=None,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guests=1,
        nights=2,
        total_price_usd=240,
        total_price_ars=252000,
        status="confirmed",
        payment_status="paid",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    ctx = {"db": db}
    result = _handle_consultar_reserva({"code": "HTL-TEST02"}, ctx)
    assert "apellido" in result["tool_result"].lower()
    assert "booking" not in result

    # Con el apellido pasa (no hay contacto para contradecir, decisión conservadora).
    result2 = _handle_consultar_reserva({"code": "HTL-TEST02", "apellido": "Cualquiera"}, ctx)
    assert "HTL-TEST02" in result2["tool_result"]
    assert result2.get("booking") is not None
