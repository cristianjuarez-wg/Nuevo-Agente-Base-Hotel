"""
Fase 1.6 — Test de aceptación multi-cliente.

Prueba el objetivo de la fase: con SOLO cambiar el BusinessProfile (sin tocar código),
la identidad compuesta del agente cambia de forma coherente (nombre, dialecto, ciudad,
moneda, facts). Determinista, sin LLM: se verifica el texto de los prompts renderizados.
"""
from app.prompts.identity_blocks import (
    build_identity_block,
    build_casual_identity_block,
    build_dialect_block,
    build_facts_block,
    build_temporal_block,
)


CANCUN = {
    "agent_display_name": "Sol",
    "role_descriptor": "asistente",
    "business_name": "Hotel Playa Azul Cancún",
    "brand_line": "",
    "vertical": "hotel",
    "city": "Cancún",
    "region_line": "frente al Caribe",
    "locale": "es_MX",
    "language": "es",
    "dialect_style": "es_neutro",
    "primary_currency": "MXN",
    "secondary_currency": None,
    "facts": ["Tiene spa y gimnasio 24h", "Desayuno buffet incluido"],
}


def test_identidad_cambia_con_el_perfil():
    ident = build_identity_block(CANCUN)
    assert "Sol" in ident
    assert "Hotel Playa Azul Cancún" in ident
    assert "asistente" in ident
    # NO debe traer la identidad del Hampton.
    assert "Hampton" not in ident
    assert "Bariloche" not in ident


def test_casual_cambia_con_el_perfil():
    c = build_casual_identity_block(CANCUN)
    assert "Sol" in c and "Cancún" in c
    assert "Hampton" not in c
    # es_neutro: no vosea
    assert "vos tenés" not in c


def test_dialecto_neutro_sin_voseo():
    d = build_dialect_block(CANCUN)
    assert "tú tienes" in d
    assert "vos tenés" not in d


def test_facts_del_cliente_presentes():
    f = build_facts_block(CANCUN)
    assert "Tiene spa y gimnasio 24h" in f
    assert "Desayuno buffet incluido" in f
    # (En el Hampton el bloque de facts es vacío: acá el cliente SÍ tiene spa.)


def test_temporal_usa_la_ciudad_del_perfil():
    t = build_temporal_block("lunes 01 de enero de 2026", "10:00", CANCUN)
    assert "Cancún" in t
    assert "Bariloche" not in t


def test_hampton_sigue_intacto():
    """Regresión: el perfil de fábrica no cambió (paridad con lo histórico)."""
    hampton = {
        "agent_display_name": "Aura", "role_descriptor": "concierge",
        "business_name": "Hampton by Hilton Bariloche",
        "brand_line": "el primer Hilton de la Patagonia", "city": "Bariloche",
        "dialect_style": "rioplatense_voseo", "facts": [],
    }
    assert "Hampton by Hilton Bariloche" in build_identity_block(hampton)
    assert "voseo" in build_dialect_block(hampton).lower()
    assert build_facts_block(hampton) == ""
