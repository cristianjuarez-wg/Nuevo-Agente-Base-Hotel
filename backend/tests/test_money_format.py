"""
Fase 1.4 — format_money parametrizado por moneda.

Paridad: para USD y ARS reproduce el formato histórico exacto de los f-strings del
proyecto (USD {x:.0f} / ARS {y:,.0f}). Otras monedas funcionan sin código nuevo.
"""
from app.utils.money import format_money


def test_usd_formato_historico():
    assert format_money(990, "USD") == "USD 990"
    assert format_money(990, "USD") == f"USD {990:.0f}"


def test_ars_formato_historico_con_comas():
    assert format_money(1250000, "ARS") == "ARS 1,250,000"
    assert format_money(1250000, "ARS") == f"ARS {1250000:,.0f}"


def test_otra_moneda_sin_codigo():
    assert format_money(3500, "MXN") == "MXN 3500"
    assert format_money(200, "EUR") == "EUR 200"


def test_none_y_basura():
    assert format_money(None, "USD") == ""
    assert format_money("x", "USD") == "x USD"


def test_default_es_usd():
    assert format_money(100) == "USD 100"
