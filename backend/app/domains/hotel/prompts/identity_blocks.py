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


# ── Identidad para el CASUAL (frase compacta, con dialecto embebido) ──────────
# Voz breve del casual: incluye el rasgo de dialecto en la misma frase (distinta a la
# del pre-venta). Con el perfil Hampton reproduce byte a byte el texto histórico.
_CASUAL_DIALECT_HINT = {
    "rioplatense_voseo": "voseo rioplatense (\"vos tenés\", \"dale\", \"bárbaro\")",
    "es_neutro": "un español neutro y claro",
    "es_tuteo": "tuteo cordial (\"tú tienes\", \"genial\")",
    "en": "warm, natural English",
}


def build_casual_identity_block(profile: dict) -> str:
    """Encabezado del prompt CASUAL, compuesto desde el perfil.

    Con el perfil del Hampton produce el encabezado casual histórico byte a byte.
    """
    agente = profile.get("agent_display_name") or "Aura"
    rol = profile.get("role_descriptor") or "concierge"
    negocio = profile.get("business_name") or "Hampton by Hilton Bariloche"
    city = profile.get("city") or "Bariloche"
    dialect_hint = _CASUAL_DIALECT_HINT.get(
        profile.get("dialect_style") or "rioplatense_voseo",
        _CASUAL_DIALECT_HINT["rioplatense_voseo"],
    )

    if (negocio == "Hampton by Hilton Bariloche" and rol == "concierge"
            and city == "Bariloche" and (profile.get("dialect_style") or "rioplatense_voseo") == "rioplatense_voseo"):
        return (
            f"Sos {agente}, la concierge del Hampton by Hilton Bariloche. Conocés Bariloche "
            "de memoria —el lago, el frío, los lugares lindos— y hablás con calidez genuina, "
            "humor sutil y voseo rioplatense (\"vos tenés\", \"dale\", \"bárbaro\"). Sos una "
            "persona, no un bot."
        )

    return (
        f"Sos {agente}, {rol} de {negocio}. Conocés {city} de memoria y hablás con calidez "
        f"genuina, humor sutil y {dialect_hint}. Sos una persona, no un bot."
    )


# ── Identidad para el POST-VENTA ──────────────────────────────────────────────
def build_postsale_identity_block(profile: dict, passenger_name: str) -> str:
    """Encabezado del post-venta. Con el perfil Hampton reproduce el texto histórico."""
    agente = profile.get("agent_display_name") or "Aura"
    rol = profile.get("role_descriptor") or "concierge"
    negocio = profile.get("business_name") or "Hampton by Hilton Bariloche"
    if negocio == "Hampton by Hilton Bariloche" and rol == "concierge":
        return (
            f"Eres {agente}, el concierge de soporte POST-VENTA del Hampton by Hilton "
            f"Bariloche. Atendés a {passenger_name}, un huésped que YA tiene una reserva "
            "confirmada. Tu trato encarna la HAMPTONALITY: cálido, empático, auténtico y "
            "orientado a resolver."
        )
    return (
        f"Eres {agente}, {rol} de soporte POST-VENTA de {negocio}. Atendés a {passenger_name}, "
        "un huésped que YA tiene una reserva confirmada. Tu trato es cálido, empático, "
        "auténtico y orientado a resolver."
    )


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
    return "\nHECHOS DEL NEGOCIO (no inventar ni contradecir):\n" + lineas


def build_location_block(profile: dict) -> str:
    """Bloque de ubicación del hotel.

    Para el Hampton (city=Bariloche) devuelve el bloque histórico con la dirección/distancias
    EXACTAS (paridad byte a byte). Para otro cliente, la dirección/distancias son un DATO que
    debe vivir en su base de conocimiento (RAG), no acá: se devuelve una guía que remite a
    info_hotel y prohíbe inventar la ubicación. Cierra el bug de "Bariloche hardcodeada" que
    salía para cualquier instancia (detectado en la prueba de fuego 3.5)."""
    city = (profile.get("city") or "").strip()
    if city == "Bariloche" or not city:
        # Perfil Hampton (o sin city): texto histórico exacto.
        from app.domains.hotel.hotel_location import HOTEL_LOCATION_BLOCK
        return HOTEL_LOCATION_BLOCK
    negocio = profile.get("business_name") or "el hotel"
    return (
        f"UBICACIÓN — NUNCA la inventes: la dirección exacta y las distancias de {negocio} "
        f"(en {city}) salen SIEMPRE de la tool info_hotel / la base de conocimiento. Si te "
        f"preguntan cómo llegar o dónde está, consultá info_hotel; no afirmes una dirección, "
        f"barrio o distancia que no venga de ahí."
    )


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
