"""
Tests del fix P4: el gate de post-venta no le pide el código a un huésped de WhatsApp
que ya identificamos por su teléfono (tiene reserva vigente). Web y "sin reserva" siguen
pidiendo el código.

Deterministas, sin OpenAI (validate_access es síncrono y no llama al LLM). DB en memoria.
"""
from datetime import date, datetime, timedelta

import pytest

_bk_seq = 0
_room_id = None


def _ensure_room(db):
    global _room_id
    if _room_id is not None:
        return _room_id
    from app.models.hotel import Room
    r = Room(room_type="Test", base_price_usd=100, base_price_ars=100000,
             capacity=2, total_units=1)
    db.add(r); db.commit()
    _room_id = r.id
    return _room_id


def _mk_booking(db, contact_id, check_in, check_out, code, status="confirmed"):
    global _bk_seq
    from app.models.hotel import Booking
    _bk_seq += 1
    b = Booking(
        code=code, contact_id=contact_id, room_id=_ensure_room(db),
        guest_name="Test", check_in=check_in, check_out=check_out, guests=2,
        status=status, total_price_usd=200, total_price_ars=200000,
        created_at=datetime.now(),
    )
    db.add(b); db.commit()
    return b


def _gate(db):
    from app.services.hotel_postsale import HotelPostSaleService
    svc = HotelPostSaleService.__new__(HotelPostSaleService)
    svc.db = db
    return svc


def _mk_contact(db, phone):
    from app.models.contact import Contact
    c = Contact(phone_number=phone)
    db.add(c); db.commit()
    return c


class TestWhatsappPostsaleGate:
    def test_wa_con_reserva_activa_no_pide_codigo(self, db):
        # Huésped de WhatsApp alojado HOY, mensaje sin código → entra directo con su booking.
        phone = "+5491170000001"
        c = _mk_contact(db, phone)
        today = date.today()
        bk = _mk_booking(db, c.id, today - timedelta(days=1), today + timedelta(days=2), "HTL-WA01")

        session_id = "wa_" + phone.lstrip("+")
        res = _gate(db).validate_access("el aire de mi pieza no anda", session_id, history=[])
        assert res["valid"] is True
        assert res["code"] == "HTL-WA01"
        assert res["booking"].id == bk.id

    def test_wa_con_reserva_futura_cercana_no_pide_codigo(self, db):
        # Reserva que empieza mañana (consulta antes del check-in) → también la toma.
        phone = "+5491170000002"
        c = _mk_contact(db, phone)
        today = date.today()
        _mk_booking(db, c.id, today + timedelta(days=1), today + timedelta(days=3), "HTL-WA02")

        session_id = "wa_" + phone.lstrip("+")
        res = _gate(db).validate_access("una consulta sobre mi reserva", session_id, history=[])
        assert res["valid"] is True
        assert res["code"] == "HTL-WA02"

    def test_wa_sin_reserva_pide_codigo(self, db):
        # Teléfono de WhatsApp sin contacto/reserva → comportamiento de hoy (pide el código).
        session_id = "wa_5491170009999"
        res = _gate(db).validate_access("hola, un problema con mi reserva", session_id, history=[])
        assert res["valid"] is False
        assert "HTL-XXXX" in res["message"]

    def test_wa_reserva_pasada_no_cuenta(self, db):
        # Reserva ya terminada (check_out < hoy) NO debe usarse → pide el código.
        phone = "+5491170000003"
        c = _mk_contact(db, phone)
        today = date.today()
        _mk_booking(db, c.id, today - timedelta(days=10), today - timedelta(days=7), "HTL-WAOLD")

        session_id = "wa_" + phone.lstrip("+")
        res = _gate(db).validate_access("consulta", session_id, history=[])
        assert res["valid"] is False
        assert "HTL-XXXX" in res["message"]

    def test_web_sin_codigo_pide_codigo(self, db):
        # Web no tiene teléfono → debe seguir pidiendo el código (sin cambios).
        res = _gate(db).validate_access("hola, sobre mi reserva", "web-abc123", history=[])
        assert res["valid"] is False
        assert "HTL-XXXX" in res["message"]

    def test_codigo_en_mensaje_sigue_funcionando(self, db):
        # Si el huésped SÍ tipea el código (HTL-XXXX, 4 alfanuméricos), la vía actual lo
        # valida (no romper).
        _mk_booking(db, None, date.today(), date.today() + timedelta(days=2), "HTL-TY01")
        res = _gate(db).validate_access("mi código es HTL-TY01", "web-xyz", history=[])
        assert res["valid"] is True
        assert res["code"] == "HTL-TY01"
