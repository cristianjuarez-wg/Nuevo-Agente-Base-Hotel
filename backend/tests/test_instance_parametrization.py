"""
Fase 3.5 — parametrización de instancia (bugs cazados por la prueba de fuego).

Verifica (sin OpenAI):
- format_price_pair muestra la moneda del perfil, con PARIDAD exacta para el Hampton (USD/ARS);
- build_facts_block / build_location_block se comportan bien por perfil;
- el perfil acepta contact_phone/contact_email y get_contact cae al Hampton por default.
"""
from app.utils.money import format_price_pair
from app.domains.hotel.prompts.identity_blocks import build_facts_block, build_location_block


# ── Moneda (bug #3) ──────────────────────────────────────────────────────────
def test_price_pair_hampton_paridad():
    prof = {"primary_currency": "USD", "secondary_currency": "ARS"}
    assert format_price_pair(120, 126000, prof) == "USD 120 / ARS 126,000"


def test_price_pair_otra_moneda_sin_ars():
    prof = {"primary_currency": "BRL", "secondary_currency": "USD"}
    out = format_price_pair(130, 0, prof)
    assert out == "BRL 130"
    assert "ARS" not in out  # el bug: mostraba ARS a un cliente BRL


def test_price_pair_ars_primaria():
    prof = {"primary_currency": "ARS", "secondary_currency": "USD"}
    assert format_price_pair(120, 126000, prof) == "ARS 126,000 / USD 120"


# ── Facts (bug #1) ───────────────────────────────────────────────────────────
def test_facts_block_hampton_vacio():
    # Sin facts (Hampton default) → vacío, para no cambiar su prompt.
    assert build_facts_block({"facts": []}) == ""


def test_facts_block_con_facts():
    out = build_facts_block({"facts": ["Tiene spa", "Desayuno incluido"]})
    assert "HECHOS DEL NEGOCIO" in out
    assert "Tiene spa" in out


# ── Ubicación (bug #2) ───────────────────────────────────────────────────────
def test_location_block_hampton_es_historico():
    out = build_location_block({"city": "Bariloche"})
    assert "Libertad 290" in out  # texto histórico exacto del Hampton


def test_location_block_otro_cliente_no_inventa():
    out = build_location_block({"city": "Florianópolis", "business_name": "Pousada Mar Azul"})
    assert "Libertad 290" not in out
    assert "Bariloche" not in out
    assert "info_hotel" in out  # remite a la tool, no inventa dirección


# ── Contacto (bug #4) ────────────────────────────────────────────────────────
def test_perfil_acepta_contacto(db):
    from app.services import business_profile_service as bps
    bps.update_profile(db, {"contact_phone": "+55 48 1234", "contact_email": "oi@pousada.com"})
    c = bps.get_contact(db)
    assert c["phone"] == "+55 48 1234"
    assert c["email"] == "oi@pousada.com"
