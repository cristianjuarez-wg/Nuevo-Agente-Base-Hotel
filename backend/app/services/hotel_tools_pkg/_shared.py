"""
Tools (function calling) del agente de PRE-VENTA del hotel.

Mismos contratos que agent_tools.py de Freeway: cada handler recibe (args, ctx) y
devuelve un dict con al menos 'tool_result'. El dispatcher execute_tool() es invocado
por hotel_sdk_orchestrator.py vía @function_tool.

Tools disponibles:
  - info_hotel:            RAG sobre docsbase del hotel (habitaciones, servicios, políticas)
  - consultar_disponibilidad: motor de reserva real (reservation_service.get_availability)
  - crear_reserva:         crea Booking determinístico (LLM junta datos; código decide)
  - consultar_reserva:     consulta reserva existente por código HTL-XXXX
"""
from datetime import date
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.rag.rag_service import rag_service
from app.services.reservation_service import get_availability, create_booking, get_booking
from app.models.knowledge import KnowledgeEntry, Place, _payment_accounts
from app.models.hotel import Room, Booking
from app.models.promotions import Promotion
from app.models.contact import Contact
from app.services import promotions_service, exchange_rate_service, restaurant_service
from app.services.contact_service import contact_service
from app.config import settings
from app.domains.hotel.hotel_location import (
    HOTEL_ADDRESS, HOTEL_AIRPORT, directions_url, near_hotel_search_url, is_far_origin,
)
from app.core.observability.logging_config import get_logger


_ACCESS_KEYWORDS = (
    "accesible", "accesibilidad", "adaptada", "adaptado",
    "silla de ruedas", "movilidad reducida", "discapacidad", "discapacitad",
)


_ALL_KEYWORDS = (
    "todas las opciones", "todas las habitaciones", "ver todas",
    "mostrame todas", "muéstrame todas", "muestrame todas", "quiero ver todas",
)


_MAX_ROOM_CARDS = 3  # alinea con settings.WHATSAPP_MAX_ROOM_CARDS


def _wants_accessibility(ctx: Dict) -> bool:
    """True si el huésped pidió accesibilidad (mensaje actual o últimas turnos de usuario)."""
    text = (ctx.get("message") or "").lower()
    for h in (ctx.get("history") or [])[-6:]:
        if isinstance(h, dict) and h.get("role") == "user":
            text += " " + str(h.get("content") or "").lower()
    return any(k in text for k in _ACCESS_KEYWORDS)


def _wants_all_rooms(ctx: Dict) -> bool:
    """True si el huésped pidió ver TODAS las opciones (solo el mensaje actual)."""
    return any(k in (ctx.get("message") or "").lower() for k in _ALL_KEYWORDS)


def _is_accessible_room(room: Dict) -> bool:
    """True si el tipo es la habitación accesible (cubre 'Doble Twin Accesible')."""
    return "accesible" in (room.get("room_type") or "").lower()


def _select_room_cards(rooms: list, requested: list, *, wants_access: bool,
                       wants_all: bool) -> list:
    """Elige qué habitaciones van como TARJETAS (`rooms` ya viene best-fit-sorted).

    Prioridades: (1) la accesible se excluye salvo pedido; (2) "todas" → pool capeado;
    (3) si el LLM pasó tipos válidos, se honran dentro del pool; (4) si no (el bug), se
    auto-eligen las non-oversized primero (King/Twin para una pareja), capeado a 3.
    """
    # 1) Fuera la accesible salvo que la pidan.
    pool = rooms if wants_access else [r for r in rooms if not _is_accessible_room(r)]
    if not pool:  # seguridad: si solo quedaba la accesible, no devolver vacío
        pool = rooms
    # 2) Pidió ver todas.
    if wants_all:
        return pool[:_MAX_ROOM_CARDS]
    # 3) El LLM pasó tipos válidos → honrarlos DENTRO del pool ya filtrado.
    if requested:
        sel = [r for r in pool if (r.get("room_type") or "").strip().lower() in requested]
        if sel:
            return sel[:_MAX_ROOM_CARDS]
        # si filtra a vacío (tipo inexistente o accesible sin pedido) → cae al auto-pick
    # 4) Auto-pick determinístico: non-oversized primero; completar con oversized si hace falta.
    non_over = [r for r in pool if not r.get("oversized")]
    over = [r for r in pool if r.get("oversized")]
    sel = list(non_over)
    if len(sel) < 2:
        sel += over[: (2 - len(sel))]
    return sel[:_MAX_ROOM_CARDS]


def _format_wa_link(whatsapp: str) -> Optional[str]:
    """Convierte un número de WhatsApp en link wa.me (solo dígitos)."""
    if not whatsapp:
        return None
    digits = "".join(c for c in whatsapp if c.isdigit())
    return f"https://wa.me/{digits}" if digits else None


def _resolve_contact(db, ctx: Dict):
    """Resuelve el Contact desde el ctx (contact_id directo o teléfono del session_id wa_)."""
    cid = ctx.get("contact_id")
    if cid:
        return db.query(Contact).filter(Contact.id == cid).first()
    session_id = ctx.get("session_id") or ""
    if session_id.startswith("wa_"):
        phone = "+" + session_id[3:]
        return db.query(Contact).filter(Contact.phone_number == phone).first()
    return None


def _active_booking_for(db, contact, session_id: Optional[str]):
    """Reserva activa (hospedado hoy) del contacto/sesión, o None."""
    today = date.today()
    q = db.query(Booking).filter(
        Booking.status != "cancelled",
        Booking.check_in <= today, Booking.check_out >= today,
    )
    if contact:
        b = q.filter(Booking.contact_id == contact.id).first()
        if b:
            return b
    if session_id:
        return q.filter(Booking.session_id == session_id).first()
    return None


def _relevant_booking_for(db, contact, session_id: Optional[str]):
    """Reserva relevante del huésped para resolver 'el primer día de mi estadía': la activa
    HOY si está alojado, o la próxima FUTURA (check_out >= hoy) más cercana. Busca por contacto
    y por session_id (web). None si no hay reserva vigente/futura."""
    today = date.today()
    q = db.query(Booking).filter(
        Booking.status != "cancelled", Booking.check_out >= today,
    ).order_by(Booking.check_in.asc())
    if contact:
        b = q.filter(Booking.contact_id == contact.id).first()
        if b:
            return b
    if session_id:
        return q.filter(Booking.session_id == session_id).first()
    return None


def _menu_cart_url(ctx: Dict) -> str:
    """Link a la pantalla #pedido (carta completa), con la sesión para asociar el pedido."""
    url = f"{settings.LANDING_URL.rstrip('/')}/#pedido"
    sid = ctx.get("session_id")
    if sid:
        url += f"?session={sid}"
    return url


def _build_menu_card(menu: list, ctx: Dict, preselect: Optional[list] = None,
                     purpose: str = "order") -> Dict:
    """Card interactiva del menú para el chat: lleva los platos embebidos (no solo un link).

    `preselect` = [{menu_item_id, qty}] para precargar el carrito (pedido por texto, caso 2).
    `purpose` = "order" (pedir ahora, Fase 1) | "voucher" (compra anticipada, Fase 3).
    """
    titulo = "Comprá tu voucher" if purpose == "voucher" else "Carta del restaurante"
    desc = ("Elegí los platos del voucher (los canjeás cuando vengas)."
            if purpose == "voucher" else "Cocina patagónica de PLAZA - Hampton's Kitchen House.")
    # Preset de huésped IN-HOUSE: si el huésped ya validó su reserva (o reservó en esta sesión)
    # Y está alojado hoy, precargamos el checkout para no re-preguntarle "¿sos huésped?" ni el
    # código. Solo aplica a pedidos (no a vouchers). El gate de folio lo revalida el server.
    guest_preset = {}
    if purpose == "order":
        db = ctx.get("db")
        if db is not None:
            try:
                guest_preset = restaurant_service.folio_guest_preset(
                    db, ctx.get("booking_code"), ctx.get("session_id")
                )
            except Exception:  # noqa: BLE001 — el preset nunca debe romper la card
                guest_preset = {}
    return {
        "type": "menu_interactive",
        "purpose": purpose,
        "title": titulo,
        "description": desc,
        "items": menu,
        "session_id": ctx.get("session_id"),
        "fallback_url": _menu_cart_url(ctx),
        "preselect": preselect or [],
        "guest_preset": guest_preset,
    }


def _match_menu_items(texto: str, menu: list) -> Dict[str, list]:
    """Matchea un pedido en lenguaje natural contra la carta. Simple y conservador.

    Devuelve {"matched": [{menu_item_id, qty, name}], "unmatched": [textos no reconocidos]}.
    Estrategia: por cada plato de la carta, buscar su nombre (o palabras clave del nombre) en
    el texto; si aparece, lo cuenta. NO inventa: si un pedido del usuario no matchea, lo deja
    en `unmatched` para que el agente lo aclare.
    """
    import re as _re
    t = (texto or "").lower()
    # Palabras genéricas que NO distinguen un plato (aparecen en muchos): evitan falsos
    # positivos como "2 pintas Patagonia" matcheando todas las cervezas "… Patagonia".
    _GENERIC = {"patagonia", "lata", "casa", "plato", "clasico", "clásico", "patagonico",
                "patagónico", "artesanal", "especial", "guarnición", "guarnicion",
                # Marcas/lugares que aparecen en nombres de productos y no distinguen un
                # plato (ej. "Gin Athos Bariloche"): evitan matchear un saludo que los nombra.
                "bariloche", "athos", "hampton", "plaza",
                # Términos del dominio HOTEL que aparecen en nombres de productos (ej. el vino
                # "Pinot Noir Malma Reserva") y colisionan por substring con el verbo del flujo
                # de reservas ("reserva" ⊂ "reservar"): jamás deben anclar un plato.
                "reserva", "reservar", "reservas"}
    matched = []
    for m in menu:
        name = (m.get("name") or "").lower()
        if not name:
            continue
        words = [w for w in _re.split(r"[\s()]+", name) if len(w) >= 4 and w not in _GENERIC]
        # Match por la palabra ANCLA: la más larga y distintiva del nombre (ej. "provenzal",
        # "napolitana", "capuccino", "bolognesa"). Si NO hay una palabra distintiva (todas
        # cortas o genéricas, ej. "Gin Athos Bariloche"), NO usamos ancla: solo matchea por
        # nombre completo. Así evitamos que "gin" pegue dentro de "página"/"imagina".
        anchor = max(words, key=len) if words else ""
        # El ancla matchea por PALABRA COMPLETA (\b), no substring: "napolitana" sí matchea
        # "napolitanas" (plural) pero "gin" no matchea "página".
        anchor_hit = bool(anchor) and _re.search(rf"\b{_re.escape(anchor)}", t) is not None
        hit = name in t or anchor_hit
        if hit:
            # Cantidad: "2 napolitanas" / "2x …" → 2; por defecto 1.
            qty = 1
            mqty = _re.search(r"(\d+)\s*(?:x\s*)?[\wáéíóú]*\s*" + _re.escape(anchor), t)
            if mqty:
                qty = max(1, int(mqty.group(1)))
            matched.append({"menu_item_id": m["id"], "qty": qty, "name": m["name"]})
    return {"matched": matched, "unmatched": []}


def _build_table_card(ctx: Dict, preset: Optional[Dict] = None) -> Dict:
    """Card selector de reserva de mesa para el chat (fecha + turno + personas)."""
    db = ctx.get("db")
    session_id = ctx.get("session_id")
    # Si ya reservó en esta sesión, no le pedimos el código (se asocia por session_id).
    # El preset del agente (franja/fecha/personas) tiene prioridad sobre el de la reserva.
    merged = {}
    if db is not None:
        merged.update(restaurant_service.session_guest_preset(db, session_id))
    merged.update(preset or {})
    return {
        "type": "table_reservation",
        "title": "Reservar una mesa",
        "description": "Elegí el día, el turno y cuántas personas.",
        "slots": restaurant_service.RESTAURANT_SLOTS,
        "session_id": session_id,
        "preset": merged,
    }


_FRANJA_CENA_HINTS = ("noche", "cena", "cenar", "nocturn")


_FRANJA_ALMUERZO_HINTS = ("almuerzo", "almorzar", "mediodia", "mediodía", "medio dia", "medio día")


def _franja_desde_texto(turno: str) -> Optional[str]:
    """Devuelve 'almuerzo'|'cena' si el texto del turno corresponde a una franja, o None."""
    t = (turno or "").lower()
    if not t:
        return None
    if t in restaurant_service.RESTAURANT_SLOTS:   # ya viene "almuerzo"/"cena"
        return t
    if any(h in t for h in _FRANJA_CENA_HINTS):
        return "cena"
    if any(h in t for h in _FRANJA_ALMUERZO_HINTS):
        return "almuerzo"
    return None


def _normalizar_turno(turno: str) -> Optional[str]:
    """Convierte una hora en lenguaje natural a un slot VÁLIDO del restaurante, o None.

    Necesario sobre todo en WhatsApp (sin selector): el huésped escribe "a las 20", "20hs",
    "8 de la noche" y hay que mapearlo a "20:00" (un turno real) para poder crear la reserva.
    Solo devuelve horarios que EXISTEN en _all_slots() (no inventa turnos).

    Ejemplos: "a las 20"→"20:00", "20.30"→"20:30", "8 de la noche"→"20:00",
              "1 de la tarde"→"13:00", "cena"→None (es franja, no hora puntual).
    """
    if not turno:
        return None
    import re as _re
    t = turno.strip().lower()
    slots = restaurant_service._all_slots()
    # 1) Ya viene como HH:MM válido.
    if t in slots:
        return t
    # 2) Extraer hora[:min] del texto (acepta : o . como separador).
    m = _re.search(r"(\d{1,2})(?:[:.]?(\d{2}))?", t)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2)) if m.group(2) else 0
    # 3) "de la noche/tarde" → pasar 1–11 a la franja vespertina (formato 24h).
    if hh < 12 and any(k in t for k in ("noche", "tarde", "pm", "p.m")):
        hh += 12
    candidato = f"{hh:02d}:{mm:02d}"
    return candidato if candidato in slots else None


_ALERGIA_KEYWORDS = ("alergi", "alérgic", "alergic", "intoleran", "anafilax")


def _clasificar_preferencia(texto: str, tipo_hint: Optional[str] = None) -> str:
    """Devuelve 'allergies' o 'dietary' según el texto (o un hint explícito del agente).

    Una alergia es un tema de SEGURIDAD alimentaria y va separada de las dietas
    (vegano, vegetariano, sin TACC). El hint del agente ('alergia'|'dieta') gana.
    """
    if tipo_hint:
        h = tipo_hint.strip().lower()
        if h.startswith("aler") or "intoler" in h:
            return "allergies"
        if h in ("dieta", "dietary", "preferencia", "preferencia_dietetica"):
            return "dietary"
    t = (texto or "").lower()
    if any(k in t for k in _ALERGIA_KEYWORDS):
        return "allergies"
    return "dietary"


def persist_preferences(db, contact, nuevas: list, tipo_hint: Optional[str] = None):
    """Persiste preferencias/alergias en el perfil del Contact. Reusable por pre y post-venta.

    Clasifica cada item en `allergies` (seguridad alimentaria) o `dietary`, los suma a los ya
    guardados y los persiste. Devuelve (nuevas_alergias, nuevas_dietas) que efectivamente se
    agregaron, para el mensaje de confirmación.
    """
    try:
        profile = contact_service.get_guest_profile(contact.id, db)
        prefs = (profile or {}).get("preferences") or {}
    except Exception:
        prefs = {}
    diet = set(prefs.get("dietary") or [])
    allergies = set(prefs.get("allergies") or [])
    nuevas_alergias, nuevas_dietas = [], []
    for p in nuevas:
        if _clasificar_preferencia(p, tipo_hint) == "allergies":
            allergies.add(p)
            nuevas_alergias.append(p)
        else:
            diet.add(p)
            nuevas_dietas.append(p)
    prefs["dietary"] = sorted(diet)
    prefs["allergies"] = sorted(allergies)
    contact_service.set_preferences(contact.id, prefs, db)
    return nuevas_alergias, nuevas_dietas


# Exporta TODO (incl. helpers privados) para el import * de los submódulos (Fase 2.3).
__all__ = ['date', 'Dict', 'Optional', 'Session', 'rag_service', 'get_availability', 'create_booking', 'get_booking', 'KnowledgeEntry', 'Place', '_payment_accounts', 'Room', 'Booking', 'Promotion', 'Contact', 'promotions_service', 'exchange_rate_service', 'restaurant_service', 'contact_service', 'settings', 'HOTEL_ADDRESS', 'HOTEL_AIRPORT', 'directions_url', 'near_hotel_search_url', 'is_far_origin', 'get_logger', '_ACCESS_KEYWORDS', '_ALL_KEYWORDS', '_MAX_ROOM_CARDS', '_wants_accessibility', '_wants_all_rooms', '_is_accessible_room', '_select_room_cards', '_format_wa_link', '_resolve_contact', '_active_booking_for', '_relevant_booking_for', '_menu_cart_url', '_build_menu_card', '_match_menu_items', '_build_table_card', '_FRANJA_CENA_HINTS', '_FRANJA_ALMUERZO_HINTS', '_franja_desde_texto', '_normalizar_turno', '_ALERGIA_KEYWORDS', '_clasificar_preferencia', 'persist_preferences']
