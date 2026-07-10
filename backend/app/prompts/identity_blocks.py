"""
Bloques de IDENTIDAD compuestos desde el BusinessProfile (Fase 1).

Funciones puras: reciben el dict del perfil (business_profile_service.get_profile) y
devuelven el texto que antes estaba hardcodeado en los prompts ("Hampton by Hilton
Bariloche", voseo, "no hay spa ni sauna", fecha/hora en zona AR).

PARIDAD: con el perfil de fábrica (Hampton), cada builder devuelve EXACTAMENTE el texto
histórico. Lo verifica tests/test_identity_blocks.py contra snapshots del original.
"""
from typing import Optional


# ── Dialecto ──────────────────────────────────────────────────────────────────
# La variante rioplatense_voseo es byte-idéntica al texto histórico del DEFAULT_TONO_BLOCK.
_DIALECT = {
    "rioplatense_voseo": (
        "Hablás en VOSEO rioplatense natural: \"vos tenés\", \"fijate\", \"dale\", "
        "\"bárbaro\", \"un montón\". NUNCA tuteo (\"tú tienes\") salvo que el huésped lo "
        "use primero."
    ),
    "es_neutro": (
        "Hablás un español NEUTRO y claro (sin voseo ni modismos locales fuertes): "
        "\"tú tienes\", \"mira\", \"perfecto\". Cálido pero entendible para cualquier "
        "hispanohablante."
    ),
    "es_tuteo": (
        "Hablas con TUTEO natural: \"tú tienes\", \"fíjate\", \"genial\". Cercano y "
        "cordial, sin sonar acartonado."
    ),
    "en": (
        "You speak natural, warm English: friendly and hospitable, never stiff or corporate."
    ),
}


def build_dialect_block(profile: dict) -> str:
    """Instrucción de dialecto/voz según profile['dialect_style']. Default: voseo."""
    return _DIALECT.get(profile.get("dialect_style") or "rioplatense_voseo",
                        _DIALECT["rioplatense_voseo"])


# ── Identidad (encabezado del prompt) ─────────────────────────────────────────
def build_identity_block(profile: dict) -> str:
    """Encabezado 'Sos {agente}, {rol} de {negocio}…' compuesto desde el perfil.

    Con el perfil del Hampton produce el encabezado histórico byte a byte.
    """
    agente = profile.get("agent_display_name") or "Aura"
    rol = profile.get("role_descriptor") or "concierge"
    negocio = profile.get("business_name") or "Hampton by Hilton Bariloche"
    brand = (profile.get("brand_line") or "").strip()
    city = profile.get("city") or "Bariloche"

    # Caso de fábrica (Hampton): reproduce EXACTAMENTE el texto histórico, incluida la
    # frase de color local sobre Bariloche.
    if (negocio == "Hampton by Hilton Bariloche"
            and rol == "concierge"
            and brand == "el primer Hilton de la Patagonia"
            and city == "Bariloche"):
        return (
            "Sos Aura, la concierge del Hampton by Hilton Bariloche, el primer Hilton de la "
            "Patagonia. Conocés Bariloche como la palma de tu mano —el lago, el cerro, el "
            "frío que invita a quedarse adentro tomando algo caliente— y ese cariño por tu "
            "lugar se nota cuando hablás."
        ).replace("Aura", agente)

    # Caso genérico (otro cliente): identidad neutra parametrizada.
    brand_opt = f", {brand}" if brand else ""
    region = (profile.get("region_line") or "").strip()
    region_opt = f" {region}" if region else ""
    return f"Sos {agente}, {rol} de {negocio}{brand_opt}.{region_opt}"


# ── Hechos del negocio (cierra el hueco #6 diferido en Fase 0) ────────────────
def build_facts_block(profile: dict) -> str:
    """Lista de hechos duros del negocio para que el agente no los invente ni contradiga.

    Vacío si el perfil no tiene facts (el default de fábrica): así el prompt del Hampton
    queda byte-idéntico (los 'no hay spa ni sauna' siguen inline en las tools por ahora).
    """
    facts = profile.get("facts") or []
    if not facts:
        return ""
    lineas = "\n".join(f"- {f}" for f in facts)
    return "HECHOS DEL NEGOCIO (no inventar ni contradecir):\n" + lineas


# ── Bloque temporal (fecha/hora en el timezone del perfil) ────────────────────
def build_temporal_block(fecha_actual: str, hora_actual: str, profile: dict) -> str:
    """Bloque de fecha/hora local del negocio. Con el perfil AR produce el texto histórico."""
    city = profile.get("city") or "Bariloche"
    # 'país' legible para el encabezado: derivable del locale, con default Argentina.
    pais = "Argentina" if (profile.get("locale") or "es_AR").endswith("AR") else ""
    encab = f", {pais}" if pais else ""
    return (
        f"INFORMACIÓN TEMPORAL (zona horaria del hotel{encab}):\n"
        f"- Fecha actual: {fecha_actual}\n"
        f"- Hora actual: {hora_actual}\n"
        f"- Esta es la hora LOCAL DEL HOTEL. El visitante puede estar en otra zona horaria.\n"
        f"  No asumas que es su hora local ni que está físicamente en {city}."
    )
