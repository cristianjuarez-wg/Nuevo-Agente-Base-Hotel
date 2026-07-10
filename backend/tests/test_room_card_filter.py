"""
Tests del filtro DETERMINÍSTICO de tarjetas de habitación (sin OpenAI).

Garantizan que el backend NUNCA muestre las 4 habitaciones ni la accesible sin pedido,
independientemente de lo que pase (o no pase) el LLM en `room_types`. La selección opera
sobre los dicts que devuelve get_availability, así que stubeamos esa función (no la DB).
"""
from unittest.mock import patch, MagicMock

# Fase 2.3: el handler y get_availability viven en el submódulo booking del paquete
# hotel_tools_pkg (antes en hotel_tools.py monolítico). El patch va sobre booking.
from app.services.hotel_tools_pkg import booking as hotel_tools


def _room(rt, cap, occupancy):
    """Un dict de habitación como el que arma get_availability."""
    return {
        "room_type": rt, "capacity": cap,
        "oversized": (cap - occupancy) >= 2,
        "total_price_usd": 100.0, "total_price_ars": 1000.0,
        "units_available": 1, "nights": 4, "bed_config": "", "images": [],
    }


def _run(args, ctx_extra=None, rooms=None, occupancy=2):
    """Ejecuta el handler con get_availability stubeado. Devuelve (out, rooms_offered)."""
    rooms = rooms if rooms is not None else [
        _room("King", 3, occupancy), _room("Twin", 3, occupancy),
        _room("Family Plan", 4, occupancy), _room("Doble Twin Accesible", 3, occupancy),
    ]
    ctx = {"db": MagicMock(), "message": "", "history": []}
    if ctx_extra:
        ctx.update(ctx_extra)
    base = {"check_in": "2026-08-20", "check_out": "2026-08-24", "guests": occupancy}
    base.update(args)
    with patch.object(hotel_tools, "get_availability", return_value=rooms):
        out = hotel_tools._handle_consultar_disponibilidad(base, ctx)
    return out, ctx["rooms_offered"]


def _titles(rooms):
    return [r["room_type"] for r in rooms]


def test_couple_excludes_accessible_and_caps():
    """Pareja sin room_types: King+Twin, sin accesible, ≤3, texto coherente."""
    out, offered = _run({"guests": 2}, {"message": "disponibilidad para 2 adultos"})
    titles = _titles(offered)
    assert "Doble Twin Accesible" not in titles
    assert len(offered) <= 3
    assert "King" in titles and "Twin" in titles
    # Para una pareja, la Family Plan (oversized) no debería estar.
    assert "Family Plan" not in titles
    assert "Accesible" not in out["tool_result"]


def test_accessibility_request_surfaces_accessible():
    """Si piden accesibilidad, la accesible aparece."""
    _, offered = _run({"guests": 2}, {"message": "necesito una habitación accesible, somos 2"})
    assert "Doble Twin Accesible" in _titles(offered)


def test_accessibility_request_in_history():
    """El pedido de accesibilidad puede venir de un turno anterior."""
    hist = [{"role": "user", "content": "viajo con alguien en silla de ruedas"}]
    _, offered = _run({"guests": 2}, {"message": "del 20 al 24, 2 adultos", "history": hist})
    assert "Doble Twin Accesible" in _titles(offered)


def test_family_of_four_shows_family_plan():
    """Familia de 4: la Family Plan es best-fit y debe estar (las de cap 3 no entran)."""
    rooms = [_room("Family Plan", 4, 4)]  # solo la que entra para 4
    _, offered = _run({"guests": 4}, {"message": "somos 4"}, rooms=rooms, occupancy=4)
    assert "Family Plan" in _titles(offered)


def test_llm_lists_accessible_without_request_is_filtered():
    """Si el LLM pasa la accesible en room_types pero nadie la pidió, se filtra."""
    _, offered = _run(
        {"guests": 2, "room_types": ["Twin", "Doble Twin Accesible"]},
        {"message": "2 adultos"},
    )
    titles = _titles(offered)
    assert "Doble Twin Accesible" not in titles
    assert "Twin" in titles


def test_wants_all_caps_at_three_no_accessible():
    """Pedir 'todas las opciones' muestra hasta 3 y sin la accesible (no la pidió)."""
    _, offered = _run({"guests": 2}, {"message": "mostrame todas las opciones"})
    titles = _titles(offered)
    assert len(offered) <= 3
    assert "Doble Twin Accesible" not in titles


def test_llm_valid_room_types_honored():
    """Si el LLM pasa tipos válidos no-accesibles, se honran."""
    _, offered = _run(
        {"guests": 2, "room_types": ["King"]},
        {"message": "2 adultos"},
    )
    assert _titles(offered) == ["King"]


def test_text_matches_cards():
    """El tool_result solo nombra las habitaciones seleccionadas (coherencia texto↔tarjetas)."""
    out, offered = _run({"guests": 2}, {"message": "2 adultos"})
    for r in offered:
        assert r["room_type"] in out["tool_result"]
    assert "Family Plan" not in out["tool_result"]
