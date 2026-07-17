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

    def test_wa_sin_reserva_cae_a_preventa(self, db):
        # Teléfono de WhatsApp sin contacto/reserva → ya NO se exige el código: la consulta
        # cae a pre-venta (que atiende sin reserva y pide el código solo si hace falta).
        session_id = "wa_5491170009999"
        res = _gate(db).validate_access("hola, un problema con mi reserva", session_id, history=[])
        assert res["valid"] is False
        assert res.get("fallback_preventa") is True

    def test_wa_reserva_pasada_no_cuenta(self, db):
        # Reserva ya terminada (check_out < hoy) NO debe usarse → cae a pre-venta.
        phone = "+5491170000003"
        c = _mk_contact(db, phone)
        today = date.today()
        _mk_booking(db, c.id, today - timedelta(days=10), today - timedelta(days=7), "HTL-WAOLD")

        session_id = "wa_" + phone.lstrip("+")
        res = _gate(db).validate_access("consulta", session_id, history=[])
        assert res["valid"] is False
        assert res.get("fallback_preventa") is True

    def test_web_sin_codigo_cae_a_preventa(self, db):
        # Web sin reserva hallable → fallback a pre-venta, no el callejón "dame tu HTL".
        res = _gate(db).validate_access("hola, sobre mi reserva", "web-abc123", history=[])
        assert res["valid"] is False
        assert res.get("fallback_preventa") is True

    def test_codigo_en_mensaje_sigue_funcionando(self, db):
        # Si el huésped SÍ tipea el código (HTL-XXXX, 4 alfanuméricos), la vía actual lo
        # valida (no romper).
        _mk_booking(db, None, date.today(), date.today() + timedelta(days=2), "HTL-TY01")
        res = _gate(db).validate_access("mi código es HTL-TY01", "web-xyz", history=[])
        assert res["valid"] is True
        assert res["code"] == "HTL-TY01"

    def test_codigo_invalido_sigue_avisando(self, db):
        # Código tipeado que NO existe: el aviso "no encuentro esa reserva" se mantiene
        # (el usuario dio un código explícito; verificar es lo correcto, no el fallback).
        res = _gate(db).validate_access("mi código es HTL-ZZ99", "web-xyz", history=[])
        assert res["valid"] is False
        assert res.get("fallback_preventa") is None
        assert "HTL-ZZ99" in res["message"]

    @pytest.mark.asyncio
    async def test_run_gate_propaga_fallback_preventa(self, db):
        # run_gate propaga el fallback como handled=False + fallback_preventa (el llamador
        # cae a pre-venta en vez de responder el pedido de código).
        res = await _gate(db).run_gate("recomendame algo de la carta", "web-nueva", history=[])
        assert res["handled"] is False
        assert res.get("fallback_preventa") is True


def _mk_folio_order(db, session_id, booking_id, code="RST-T001"):
    from app.models.restaurant import RestaurantOrder
    o = RestaurantOrder(order_code=code, booking_id=booking_id, session_id=session_id,
                        payment_mode="folio", fulfillment="room_service",
                        total_usd=47, total_ars=69975, status="confirmado")
    db.add(o); db.commit()
    return o


class TestContinuidadFolio:
    """Continuidad de identidad: si el huésped ya identificó su reserva en ESTA sesión al
    cargar un pedido al folio (tipeó su HTL en el carrito), el gate NO se la re-pide.
    Reproduce el bug reportado: pedido a folio de HTL-Y3QM → '¿puedo hacer el checkout?'
    → el gate pedía el código que acababa de usar."""

    def test_pedido_a_folio_en_sesion_reconoce_la_reserva(self, db):
        today = date.today()
        # Reserva PREEXISTENTE (creada en OTRA sesión — session_id distinto al de la charla).
        bk = _mk_booking(db, None, today - timedelta(days=1), today + timedelta(days=2), "HTL-Y3Q1")
        _mk_folio_order(db, "web-charla-actual", bk.id, code="RST-F001")

        res = _gate(db).validate_access("puedo hacer el checkout por acá?",
                                        "web-charla-actual", history=[])
        assert res["valid"] is True
        assert res["code"] == "HTL-Y3Q1"

    def test_pedido_de_otra_sesion_no_filtra_la_reserva(self, db):
        # El pedido a folio fue en OTRA sesión: esta charla no tiene derecho a esa reserva.
        today = date.today()
        bk = _mk_booking(db, None, today - timedelta(days=1), today + timedelta(days=2), "HTL-Y3Q2")
        _mk_folio_order(db, "web-otra-charla", bk.id, code="RST-F002")

        res = _gate(db).validate_access("puedo hacer el checkout?", "web-esta-charla", history=[])
        assert res["valid"] is False
        assert res.get("fallback_preventa") is True

    def test_reserva_cancelada_no_cuenta(self, db):
        today = date.today()
        bk = _mk_booking(db, None, today - timedelta(days=1), today + timedelta(days=2),
                         "HTL-Y3Q3", status="cancelled")
        _mk_folio_order(db, "web-charla-c", bk.id, code="RST-F003")

        res = _gate(db).validate_access("una consulta de mi reserva", "web-charla-c", history=[])
        assert res["valid"] is False
        assert res.get("fallback_preventa") is True

    def test_mesa_asociada_a_reserva_tambien_reconoce(self, db):
        # Una MESA asociada a la reserva (codigo_reserva dado al reservarla) también
        # identifica al huésped en la sesión.
        from app.models.restaurant import TableReservation
        today = date.today()
        bk = _mk_booking(db, None, today - timedelta(days=1), today + timedelta(days=2), "HTL-Y3Q4")
        tr = TableReservation(code="MESA-T001", booking_id=bk.id, session_id="web-charla-m",
                              party_size=2, status="confirmada",
                              reserved_for=datetime.now() + timedelta(days=1))
        db.add(tr); db.commit()

        res = _gate(db).validate_access("hasta qué hora es el check-out?",
                                        "web-charla-m", history=[])
        assert res["valid"] is True
        assert res["code"] == "HTL-Y3Q4"
