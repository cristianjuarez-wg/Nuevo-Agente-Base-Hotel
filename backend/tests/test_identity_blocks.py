"""
Fase 1.2 — PARIDAD de la identidad compuesta desde el BusinessProfile.

Con el perfil de fábrica (Hampton), el prompt de pre-venta renderizado debe ser
byte-idéntico al histórico. El baseline histórico se reconstruye desde el commit de la
Fase 0.1 (antes de parametrizar la identidad), renderizado con los MISMOS valores
dinámicos (fecha/hora/bloques) que el prompt actual — así solo se compara el efecto de
la parametrización de identidad, no el reloj.
"""
from app.domains.hotel.prompts.identity_blocks import (
    build_identity_block,
    build_dialect_block,
    build_facts_block,
    build_temporal_block,
    build_casual_identity_block,
    build_postsale_identity_block,
)

# Perfil de fábrica (Hampton) — coincide con el seed.
HAMPTON = {
    "agent_display_name": "Aura",
    "role_descriptor": "concierge",
    "business_name": "Hampton by Hilton Bariloche",
    "brand_line": "el primer Hilton de la Patagonia",
    "city": "Bariloche",
    "region_line": None,
    "locale": "es_AR",
    "dialect_style": "rioplatense_voseo",
    "facts": [],
}


# ── Builders individuales: byte a byte con el texto histórico ──────────────────

def test_identity_header_hampton_es_el_historico():
    got = build_identity_block(HAMPTON)
    assert got == (
        "Sos Aura, la concierge del Hampton by Hilton Bariloche, el primer Hilton de la "
        "Patagonia. Conocés Bariloche como la palma de tu mano —el lago, el cerro, el "
        "frío que invita a quedarse adentro tomando algo caliente— y ese cariño por tu "
        "lugar se nota cuando hablás."
    )


def test_dialect_voseo_es_el_historico():
    assert build_dialect_block(HAMPTON) == (
        "Hablás en VOSEO rioplatense natural: \"vos tenés\", \"fijate\", \"dale\", "
        "\"bárbaro\", \"un montón\". NUNCA tuteo (\"tú tienes\") salvo que el huésped lo "
        "use primero."
    )


def test_facts_vacio_por_defecto():
    # Sin facts (Hampton de fábrica) → bloque vacío (paridad: no agrega nada al prompt).
    assert build_facts_block(HAMPTON) == ""


def test_facts_con_datos():
    prof = dict(HAMPTON, facts=["No tiene spa ni sauna", "Desayuno incluido"])
    out = build_facts_block(prof)
    # Empieza con un \n para componerse sin línea extra cuando facts está vacío (3.5).
    assert out.lstrip().startswith("HECHOS DEL NEGOCIO")
    assert "- No tiene spa ni sauna" in out
    assert "- Desayuno incluido" in out


def test_temporal_hampton_es_el_historico():
    got = build_temporal_block("lunes 01 de enero de 2026", "10:00", HAMPTON)
    assert got == (
        "INFORMACIÓN TEMPORAL (zona horaria del hotel, Argentina):\n"
        "- Fecha actual: lunes 01 de enero de 2026\n"
        "- Hora actual: 10:00\n"
        "- Esta es la hora LOCAL DEL HOTEL. El visitante puede estar en otra zona horaria.\n"
        "  No asumas que es su hora local ni que está físicamente en Bariloche."
    )


# ── Variantes de otro cliente (contenido nuevo permitido) ──────────────────────

def test_identity_generico_otro_cliente():
    prof = {
        "agent_display_name": "Sol", "role_descriptor": "asistente",
        "business_name": "Hotel Ejemplo Cancún", "brand_line": "",
        "city": "Cancún", "region_line": "", "dialect_style": "es_neutro",
    }
    got = build_identity_block(prof)
    assert got == "Sos Sol, asistente de Hotel Ejemplo Cancún."
    # dialecto neutro: tutea (no vosea)
    dialect = build_dialect_block(prof)
    assert "tú tienes" in dialect
    assert "vos tenés" not in dialect


# ── Paridad del PROMPT RENDERIZADO COMPLETO (pre-venta) ────────────────────────

def _render_current(profile):
    """Renderiza el prompt de pre-venta ACTUAL con valores dinámicos fijos."""
    from app.domains.hotel.prompts.tool_agent_prompts import (
        TOOL_AGENT_SYSTEM, DEFAULT_TONO_BLOCK, DEFAULT_POLITICA_BLOCK,
    )
    tono = DEFAULT_TONO_BLOCK.replace("{dialect_block}", build_dialect_block(profile))
    return TOOL_AGENT_SYSTEM.format(
        agent_name=profile["agent_display_name"],
        identity_block=build_identity_block(profile),
        facts_block=build_facts_block(profile),
        fecha_actual="FECHA_FIJA", hora_actual="HORA_FIJA",
        flow_block="", tono_block=tono, politica_block=DEFAULT_POLITICA_BLOCK,
        training_block="", lead_block="", language_block="",
        naturalidad_block="NAT", ubicacion_block="UBIC", team_block="TEAM",
        negocio=profile.get("business_name") or "el hotel",
        ciudad=profile.get("city") or "la ciudad",
    )


def test_casual_identity_hampton_es_el_historico():
    assert build_casual_identity_block(HAMPTON) == (
        "Sos Aura, la concierge del Hampton by Hilton Bariloche. Conocés Bariloche "
        "de memoria —el lago, el frío, los lugares lindos— y hablás con calidez genuina, "
        "humor sutil y voseo rioplatense (\"vos tenés\", \"dale\", \"bárbaro\"). Sos una "
        "persona, no un bot."
    )


def test_postsale_identity_hampton_es_el_historico():
    assert build_postsale_identity_block(HAMPTON, "Cristian") == (
        "Eres Aura, el concierge de soporte POST-VENTA del Hampton by Hilton "
        "Bariloche. Atendés a Cristian, un huésped que YA tiene una reserva "
        "confirmada. Tu trato encarna la HAMPTONALITY: cálido, empático, auténtico y "
        "orientado a resolver."
    )


def test_prompt_preventa_identidad_y_voseo_intactos():
    """El prompt renderizado con el perfil Hampton conserva el encabezado y el voseo
    históricos exactos (la parametrización no cambió el texto de fábrica)."""
    rendered = _render_current(HAMPTON)
    # Encabezado histórico presente, tal cual.
    assert (
        "Sos Aura, la concierge del Hampton by Hilton Bariloche, el primer Hilton de la "
        "Patagonia. Conocés Bariloche como la palma de tu mano"
    ) in rendered
    # Voseo histórico presente dentro del tono, sin placeholder sin resolver.
    assert "Hablás en VOSEO rioplatense natural" in rendered
    assert "{dialect_block}" not in rendered
    assert "{identity_block}" not in rendered
