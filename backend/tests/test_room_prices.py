"""
Tarea B — precios por moneda (room_prices).

Verifica (sin OpenAI): backfill idempotente, resolución de precio por moneda (fila explícita →
conversión → fallback), y que format_price_pair muestra el precio real en la moneda del perfil.
"""
from app.models.hotel import Room
from app.models.room_price import RoomPrice
from app.services import room_price_service
from app.utils.money import format_price_pair


def _mk_room(db, rtype="King", usd=120.0, ars=126000.0):
    r = Room(room_type=rtype, capacity=2, base_price_usd=usd, base_price_ars=ars, total_units=1,
             status="active")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_backfill_puebla_usd_ars(db):
    r = _mk_room(db)
    room_price_service.backfill_from_legacy(db)
    filas = {rp.currency: rp.amount for rp in db.query(RoomPrice).filter(RoomPrice.room_id == r.id)}
    assert filas == {"USD": 120.0, "ARS": 126000.0}


def test_backfill_idempotente(db):
    r = _mk_room(db)
    room_price_service.backfill_from_legacy(db)
    room_price_service.backfill_from_legacy(db)  # 2da vez no duplica
    n = db.query(RoomPrice).filter(RoomPrice.room_id == r.id).count()
    assert n == 2


def test_price_in_fila_explicita_gana(db):
    r = _mk_room(db)
    room_price_service.set_prices(db, r.id, {"BRL": 650, "USD": 130})
    assert room_price_service.price_in(db, r, "BRL") == 650
    assert room_price_service.price_in(db, r, "USD") == 130


def test_price_in_fallback_a_usd(db):
    # Sin fila para MXN ni cotización del par → cae al USD guardado (no inventa).
    r = _mk_room(db, usd=200.0)
    assert room_price_service.price_in(db, r, "MXN") == 200.0


def test_format_price_pair_brl_real():
    prof = {"primary_currency": "BRL", "secondary_currency": "USD"}
    # con amount_primary (de room_prices) muestra el precio real, no el USD etiquetado
    assert format_price_pair(130, 0, prof, amount_primary=650) == "BRL 650"


def test_format_price_pair_hampton_paridad():
    prof = {"primary_currency": "USD", "secondary_currency": "ARS"}
    assert format_price_pair(120, 126000, prof) == "USD 120 / ARS 126,000"
