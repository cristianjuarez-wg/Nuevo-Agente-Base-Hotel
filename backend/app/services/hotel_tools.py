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

from app.services.rag_service import rag_service
from app.services.reservation_service import get_availability, create_booking, get_booking
from app.models.knowledge import KnowledgeEntry, Place, _payment_accounts
from app.models.hotel import Room, Booking
from app.models.promotions import Promotion
from app.models.contact import Contact
from app.services import promotions_service, exchange_rate_service, restaurant_service
from app.services.contact_service import contact_service
from app.config import settings
from app.core.hotel_location import (
    HOTEL_ADDRESS, HOTEL_AIRPORT, directions_url, near_hotel_search_url, is_far_origin,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------

async def _handle_info_hotel(args: Dict, ctx: Dict) -> Dict:
    """RAG sobre documentos del hotel (habitaciones, servicios, ubicación, promos)."""
    query = (args.get("query") or "").strip() or ctx.get("message", "")
    result = await rag_service.retrieve_context_with_sources(
        query=query,
        conversation_history=ctx.get("history"),
    )
    context = result.get("context", "NO_CONTEXT_FOUND")

    if context == "NO_CONTEXT_FOUND":
        return {
            "found": False,
            "tool_result": (
                "No encontré información específica sobre eso en nuestra base de datos. "
                "Para más detalles podés contactarnos al +54 294-474-6200 o en info@hamptonbariloche.com."
            ),
        }

    ctx["document_sources"] = result.get("sources", [])
    return {
        "found": True,
        "tool_result": context,
    }


def _handle_consultar_disponibilidad(args: Dict, ctx: Dict) -> Dict:
    """Consulta habitaciones disponibles en el motor de reserva real."""
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    check_in_str = (args.get("check_in") or "").strip()
    check_out_str = (args.get("check_out") or "").strip()
    guests = int(args.get("guests") or 1)
    children = int(args.get("children") or 0)
    infants = int(args.get("infants") or 0)

    if not check_in_str or not check_out_str:
        return {
            "tool_result": (
                "Necesito las fechas de check-in y check-out para consultar disponibilidad. "
                "Por favor indicame las fechas (ej: check-in 15/07, check-out 20/07)."
            )
        }

    try:
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)
    except ValueError:
        return {
            "tool_result": (
                "Las fechas deben estar en formato YYYY-MM-DD "
                f"(recibí: check_in='{check_in_str}', check_out='{check_out_str}'). "
                "¿Podés indicarme las fechas en ese formato?"
            )
        }

    # Blindaje contra interpretación errónea de fechas por el LLM: una estadía de hotel es
    # de pocas noches. Un rango enorme (ej. el LLM cambió el mes del check-out) produciría
    # precios absurdos. Antes que mostrar eso, pedimos confirmar las fechas.
    nights_requested = (check_out - check_in).days
    if nights_requested > 30:
        logger.warning("Rango de fechas sospechoso en disponibilidad",
                       check_in=check_in_str, check_out=check_out_str, nights=nights_requested)
        return {
            "tool_result": (
                f"Verifico las fechas: del {check_in} al {check_out} son {nights_requested} "
                "noches, que es una estadía muy larga. ¿Me confirmás las fechas de check-in y "
                "check-out, por favor? Así te muestro la disponibilidad correcta."
            )
        }

    try:
        rooms = get_availability(db, check_in, check_out, guests, children)
    except ValueError as e:
        return {"tool_result": str(e)}

    # Descripción legible de la composición de huéspedes.
    partes = [f"{guests} adulto(s)"]
    if children:
        partes.append(f"{children} niño(s)")
    if infants:
        partes.append(f"{infants} bebé(s) en cuna")
    composicion = ", ".join(partes)

    if not rooms:
        return {
            "tool_result": (
                f"No hay habitaciones disponibles para {composicion} "
                f"entre el {check_in} y el {check_out}. "
                "¿Querés probar otras fechas?"
            )
        }

    lines = [
        f"Habitaciones disponibles para {composicion}, "
        f"{rooms[0].get('nights')} noche(s) ({check_in} → {check_out}):\n"
    ]
    for r in rooms:
        lines.append(
            f"• {r['room_type']}: USD {r['total_price_usd']:.0f} / ARS {r['total_price_ars']:,.0f} "
            f"en total ({r['units_available']} unidad(es) disponible(s)). "
            f"{r.get('bed_config', '')}. "
            f"Capacidad: {r['capacity']} pax."
        )

    # TARJETAS DEL CHAT: por defecto mostramos solo las que el agente recomienda en su
    # respuesta (room_types), para que las tarjetas coincidan con el texto y no se muestren
    # TODAS las disponibles. Si el agente no especifica, se muestran todas (compatibilidad).
    requested = args.get("room_types") or []
    if isinstance(requested, str):
        requested = [requested]
    requested = [str(t).strip().lower() for t in requested if str(t).strip()]

    cards = rooms
    if requested:
        # Match EXACTO (normalizado) contra el nombre del tipo. No usamos "substring" para
        # evitar falsos positivos: "Twin" NO debe machear "Doble Twin Accesible".
        def _matches(room_type: str) -> bool:
            rt = (room_type or "").strip().lower()
            return rt in requested
        filtered = [r for r in rooms if _matches(r.get("room_type", ""))]
        # Si el filtro deja todo vacío (el agente nombró un tipo que no existe/no entra),
        # mostramos todas: mejor ofrecer algo que una lista vacía.
        cards = filtered or rooms

    # Guardar las habitaciones en el ctx para que el orquestador arme las tarjetas del chat.
    ctx["rooms_offered"] = cards

    return {"tool_result": "\n".join(lines), "rooms": rooms}


def _handle_crear_reserva(args: Dict, ctx: Dict) -> Dict:
    """
    Gate determinístico de creación de reserva.

    El LLM reúne los datos del huésped; ESTE CÓDIGO (no el LLM) llama a
    create_booking(). Si falta algún dato obligatorio, pide al LLM que los solicite.
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    room_type = (args.get("room_type") or "").strip()
    check_in_str = (args.get("check_in") or "").strip()
    check_out_str = (args.get("check_out") or "").strip()
    guest_name = (args.get("guest_name") or "").strip()
    guest_email = (args.get("guest_email") or "").strip() or None
    guest_phone = (args.get("guest_phone") or "").strip() or None
    guests = int(args.get("guests") or 1)
    children = int(args.get("children") or 0)
    infants = int(args.get("infants") or 0)

    # Validación de campos obligatorios antes de tocar la BD
    missing = []
    if not room_type:
        missing.append("tipo de habitación")
    if not check_in_str:
        missing.append("fecha de check-in (YYYY-MM-DD)")
    if not check_out_str:
        missing.append("fecha de check-out (YYYY-MM-DD)")
    if not guest_name:
        missing.append("nombre del huésped")
    # En WhatsApp el teléfono ya lo conocemos (viene en el session_id wa_): si el LLM no lo
    # pasó, lo auto-completamos desde la sesión. Así nunca se lo pedimos de nuevo al huésped.
    if not guest_phone:
        sid = ctx.get("session_id") or ""
        if sid.startswith("wa_"):
            guest_phone = "+" + sid[3:]
    # Teléfono OBLIGATORIO para reservar: se necesita para confirmar la reserva y el
    # seguimiento. El email queda opcional. (El "9" móvil argentino lo normaliza el modelo.)
    if not guest_phone:
        missing.append("teléfono de contacto")
    if missing:
        return {
            "tool_result": (
                f"Para crear la reserva necesito: {', '.join(missing)}. "
                "¿Podés proporcionarme esos datos?"
            )
        }

    try:
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)
    except ValueError:
        return {
            "tool_result": (
                "Las fechas deben estar en formato YYYY-MM-DD. "
                f"Recibí: check_in='{check_in_str}', check_out='{check_out_str}'."
            )
        }

    # Promo a aplicar a la reserva. Prioridad: el nombre que el agente pasó explícitamente
    # (ve toda la conversación), luego la promo calculada en este mismo turno (ctx). En
    # ambos casos create_booking REVALIDA server-side que la promo realmente aplique.
    promo_name = (args.get("promo_name") or "").strip() or None
    if not promo_name:
        offer = ctx.get("promo_offer")
        if offer and offer.get("check_in") == check_in_str and offer.get("check_out") == check_out_str:
            if room_type.lower() in (offer.get("room_type") or "").lower() or \
               (offer.get("room_type") or "").lower() in room_type.lower():
                promo_name = offer.get("promo_name")

    result = create_booking(
        db,
        room_type=room_type,
        check_in=check_in,
        check_out=check_out,
        guest_name=guest_name,
        guest_email=guest_email,
        guest_phone=guest_phone,
        guests=guests,
        children=children,
        infants=infants,
        source="agente",
        session_id=ctx.get("session_id"),
        promo_name=promo_name,
    )

    if "error" in result:
        return {"tool_result": result["error"]}

    code = result.get("code", "")
    nights = result.get("nights", 0)
    total_usd = result.get("total_price_usd", 0)
    total_ars = result.get("total_price_ars", 0)
    room = result.get("room_type", room_type)
    applied_promo = result.get("promo_name")
    full_usd = result.get("full_price_usd")

    logger.info("Reservation created via agent tool", code=code, guest=guest_name, promo=applied_promo)

    promo_line = ""
    if applied_promo and full_usd:
        ahorro = full_usd - total_usd
        promo_line = (
            f"Promo aplicada: **{applied_promo}** "
            f"(antes USD {full_usd:.0f}, ahorrás USD {ahorro:.0f})\n"
        )

    return {
        "tool_result": (
            f"¡Reserva confirmada! 🎉\n"
            f"Código de reserva: **{code}**\n"
            f"Habitación: {room}\n"
            f"Check-in: {check_in} | Check-out: {check_out} ({nights} noche(s))\n"
            f"Huésped: {guest_name}\n"
            f"{promo_line}"
            f"Total: USD {total_usd:.0f} / ARS {total_ars:,.0f}\n"
            f"Estado: Confirmada ✅\n\n"
            f"Guardá el código **{code}**: lo vas a necesitar para cualquier consulta post-estadía."
        ),
        "booking": result,
    }


def _handle_consultar_reserva(args: Dict, ctx: Dict) -> Dict:
    """Consulta el estado de una reserva existente por su código HTL-XXXX."""
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    code = (args.get("code") or "").strip().upper()
    if not code:
        return {
            "tool_result": (
                "Necesito el código de reserva (formato HTL-XXXX) para consultar el estado. "
                "¿Lo tenés a mano?"
            )
        }

    booking = get_booking(db, code)
    if not booking:
        return {
            "tool_result": (
                f"No encontré ninguna reserva con el código '{code}'. "
                "Verificá que esté bien escrito (ej: HTL-A1B2)."
            )
        }

    return {
        "tool_result": (
            f"Reserva {booking['code']}:\n"
            f"• Habitación: {booking.get('room_type', 'N/A')}\n"
            f"• Huésped: {booking['guest_name']}\n"
            f"• Check-in: {booking['check_in']} | Check-out: {booking['check_out']} "
            f"({booking['nights']} noche(s))\n"
            f"• Huéspedes: {booking['guests']}\n"
            f"• Total: USD {booking['total_price_usd']:.0f} / ARS {booking['total_price_ars']:,.0f}\n"
            f"• Estado: {booking['status']} | Pago: {booking['payment_status']}"
        ),
        "booking": booking,
    }


def _handle_info_pago(args: Dict, ctx: Dict) -> Dict:
    """Devuelve los DATOS EXACTOS de pago/transferencia cargados en el repositorio.

    Determinístico a propósito: el CBU/alias/titular son datos sensibles que NO deben
    salir de una búsqueda semántica difusa. Lee la KnowledgeEntry activa de categoría
    'pagos' y devuelve sus datos textuales para que el agente los comunique sin inventar.
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    entry = (
        db.query(KnowledgeEntry)
        .filter(KnowledgeEntry.category == "pagos", KnowledgeEntry.status == "active")
        .order_by(KnowledgeEntry.updated_at.desc())
        .first()
    )

    if not entry:
        return {
            "tool_result": (
                "No tengo cargados los datos de pago en este momento. "
                "Para coordinar el pago podés contactarnos al +54 294-474-6200 "
                "o en info@hamptonbariloche.com."
            )
        }

    data = entry.data or {}
    lines = []
    if entry.content:
        lines.append(entry.content.strip())

    medios = data.get("medios") or []
    if medios:
        lines.append("Medios de pago: " + ", ".join(medios) + ".")

    cuentas = _payment_accounts(data)  # default primero

    # ¿El usuario pide explícitamente OTRA cuenta / otra moneda? Entonces mostramos todas.
    consulta = (args.get("consulta") or "").lower()
    pide_todas = any(
        kw in consulta for kw in ("otra", "otras", "dólar", "dolar", "usd", "todas", "cuáles", "cuales")
    )

    def fmt_cuenta(c, etiqueta):
        bits = []
        if c.get("titular"):
            bits.append(f"Titular: {c['titular']}")
        if c.get("banco"):
            bits.append(f"Banco: {c['banco']}")
        if c.get("moneda"):
            bits.append(f"Moneda: {c['moneda']}")
        if c.get("cbu"):
            bits.append(f"CBU: {c['cbu']}")
        if c.get("alias"):
            bits.append(f"Alias: {c['alias']}")
        if not bits:
            return None
        return f"{etiqueta}:\n" + "\n".join(f"• {b}" for b in bits)

    if cuentas:
        if pide_todas and len(cuentas) > 1:
            for i, c in enumerate(cuentas):
                etiqueta = "Cuenta principal" if c.get("default") else f"Cuenta {i + 1}"
                block = fmt_cuenta(c, etiqueta)
                if block:
                    lines.append(block)
        else:
            # Solo la cuenta principal (la primera, default).
            block = fmt_cuenta(cuentas[0], "Datos para transferencia")
            if block:
                lines.append(block)
            if len(cuentas) > 1:
                lines.append("Si necesitás otra cuenta (por ejemplo en otra moneda), decímelo y te la paso.")

    if not lines:
        return {
            "tool_result": (
                "Tengo registrada información de pagos pero está incompleta. "
                "Por favor contactanos para coordinar el pago."
            )
        }

    return {"tool_result": "\n".join(lines), "found": True}


def _handle_como_llegar(args: Dict, ctx: Dict) -> Dict:
    """Arma un link de Google Maps con la ruta pedida (sin API key).

    - destino vacío (o el hotel) + origen presente → ruta DESDE el origen HACIA el hotel
      (ej. "Soy de Rosario, ¿cómo llego?"). Si el origen es lejano, agrega nota aérea.
    - destino presente → ruta DESDE el hotel HACIA el destino (ej. "ruta al Cerro Otto",
      "a cuánto estoy del Centro Cívico").
    El tiempo/distancia los muestra Google Maps al abrir el link; no se inventan acá.
    """
    destino = (args.get("destino") or "").strip()
    origen = (args.get("origen") or "").strip()
    medio = (args.get("medio") or "auto").strip().lower()
    mode = "walking" if medio in ("caminando", "a pie", "walking", "pie") else "driving"

    destino_es_hotel = destino == "" or any(
        kw in destino.lower() for kw in ("hotel", "hampton", "libertad 290")
    )

    # Caso 1: llegar AL hotel desde una ciudad/origen.
    if destino_es_hotel and origen:
        url = directions_url(origen, HOTEL_ADDRESS, mode)
        lines = [
            f"Te dejo la ruta desde {origen} hasta el hotel (Libertad 290, Bariloche):",
            url,
        ]
        if is_far_origin(origen):
            lines.append(
                f"\nSi venís de lejos, la opción más rápida suele ser volar al "
                f"{HOTEL_AIRPORT}: el hotel queda a unos 20 minutos del aeropuerto. "
                f"Si preferís manejar, el link de arriba te arma la ruta en auto."
            )
        return {"tool_result": "\n".join(lines), "found": True}

    # Caso 2: ir DESDE el hotel hacia un destino (o entre dos puntos si hay ambos).
    if destino:
        if origen:
            url = directions_url(origen, f"{destino} Bariloche", mode)
            intro = f"Ruta desde {origen} hasta {destino}:"
        else:
            url = directions_url(HOTEL_ADDRESS, f"{destino} Bariloche", mode)
            intro = f"Te paso la ruta desde el hotel hasta {destino}:"
        return {
            "tool_result": (
                f"{intro}\n{url}\n\n"
                "Al abrir el link, Google Maps te muestra la distancia y el tiempo estimado "
                "desde tu ubicación."
            ),
            "found": True,
        }

    # Sin datos suficientes: pedir aclaración.
    return {
        "tool_result": (
            "¿A dónde querés ir o desde dónde venís? Decime el lugar (por ejemplo "
            "'Cerro Otto', 'Centro Cívico') o tu ciudad de origen y te armo la ruta."
        ),
        "found": False,
    }


def _format_wa_link(whatsapp: str) -> Optional[str]:
    """Convierte un número de WhatsApp en link wa.me (solo dígitos)."""
    if not whatsapp:
        return None
    digits = "".join(c for c in whatsapp if c.isdigit())
    return f"https://wa.me/{digits}" if digits else None


def _handle_comercios_amigos(args: Dict, ctx: Dict) -> Dict:
    """Lista los comercios amigos (gastronomía con acuerdo) cargados en el backoffice.

    Determinístico: consulta la tabla `places` (is_partner=True, activos). Si no hay
    para el rubro pedido, devuelve un link de búsqueda genérica en Google Maps.
    """
    db = ctx.get("db")
    rubro = (args.get("rubro") or args.get("query") or "").strip()

    if db is None:
        return {"tool_result": "No pude acceder a la base de comercios en este momento.", "found": False}

    q = db.query(Place).filter(
        Place.is_partner == True,  # noqa: E712
        Place.status == "active",
    )
    partners = q.order_by(Place.name).all()

    # Filtro suave por rubro sobre nombre/categoría/descripción (si el usuario lo pidió).
    if rubro and partners:
        rl = rubro.lower()
        filtered = [
            p for p in partners
            if rl in (p.name or "").lower()
            or rl in (p.category or "").lower()
            or rl in (p.description or "").lower()
        ]
        # Si el filtro deja todo vacío, mostramos igual todos los amigos (mejor que nada).
        partners_to_show = filtered or partners
    else:
        partners_to_show = partners

    if partners_to_show:
        lines = ["Estos son nuestros comercios amigos con beneficios para huéspedes:\n"]
        for p in partners_to_show:
            bits = [f"**{p.name}**"]
            if p.discount:
                bits.append(f"🎁 {p.discount}")
            if p.address:
                bits.append(f"📍 {p.address}")
            if p.phone:
                bits.append(f"📞 {p.phone}")
            wa = _format_wa_link(p.whatsapp)
            if wa:
                bits.append(f"💬 WhatsApp: {wa}")
            if p.maps_url:
                bits.append(f"🗺️ {p.maps_url}")
            lines.append(" · ".join(bits))
        return {"tool_result": "\n".join(lines), "found": True}

    # Fallback: sin comercios amigos para ese rubro → búsqueda genérica en Maps.
    termino = rubro or "restaurantes"
    return {
        "tool_result": (
            f"Por ahora no tengo comercios amigos cargados para eso, pero podés ver "
            f"opciones de {termino} cerca del hotel acá:\n{near_hotel_search_url(termino)}"
        ),
        "found": True,
    }


def _handle_excursiones_y_atracciones(args: Dict, ctx: Dict) -> Dict:
    """Lista las excursiones y atracciones (lugares NO-amigo) cargadas en el backoffice.

    Determinístico: consulta la tabla `places` (is_partner=False, activos). Garantiza un
    listado estable (vs. el RAG, que depende del umbral de similitud). Para comercios con
    descuento ver `comercios_amigos`; para la ruta a un destino puntual, `como_llegar`.
    """
    db = ctx.get("db")
    categoria = (args.get("categoria") or args.get("query") or "").strip()

    if db is None:
        return {"tool_result": "No pude acceder a la base de lugares en este momento.", "found": False}

    lugares = (
        db.query(Place)
        .filter(Place.is_partner == False, Place.status == "active")  # noqa: E712
        .order_by(Place.name)
        .all()
    )

    # Filtro suave por categoría/rubro sobre nombre/categoría/descripción (si lo pidió).
    if categoria and lugares:
        cl = categoria.lower()
        filtered = [
            p for p in lugares
            if cl in (p.name or "").lower()
            or cl in (p.category or "").lower()
            or cl in (p.description or "").lower()
        ]
        # Si el filtro deja todo vacío, mostramos igual todo (mejor que nada).
        lugares_a_mostrar = filtered or lugares
    else:
        lugares_a_mostrar = lugares

    if lugares_a_mostrar:
        lines = ["Estas son las excursiones y atracciones cerca del hotel:\n"]
        for p in lugares_a_mostrar:
            bits = [f"**{p.name}**"]
            if p.description:
                bits.append(p.description)
            if p.price_info:
                bits.append(f"💲 {p.price_info}")
            if p.address:
                bits.append(f"📍 {p.address}")
            if p.maps_url:
                bits.append(f"🗺️ {p.maps_url}")
            lines.append(" · ".join(bits))
        return {"tool_result": "\n".join(lines), "found": True}

    # Fallback: nada cargado → búsqueda genérica en Maps.
    termino = categoria or "excursiones y atracciones"
    return {
        "tool_result": (
            f"Por ahora no tengo excursiones cargadas, pero podés ver opciones de "
            f"{termino} cerca del hotel acá:\n{near_hotel_search_url(termino)}"
        ),
        "found": True,
    }


# ---------------------------------------------------------------------------
# Promos vigentes
# ---------------------------------------------------------------------------

def _handle_promos_vigentes(args: Dict, ctx: Dict) -> Dict:
    """Devuelve las promociones activas y vigentes cargadas en el backoffice.
    Determinístico: lee la tabla promotions directamente. No inventa ni improvisa."""
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    vigentes = promotions_service.get_vigentes(db)

    if not vigentes:
        return {
            "tool_result": (
                "En este momento no tenemos promociones especiales activas. "
                "De todas formas podés consultar la disponibilidad y las tarifas vigentes."
            ),
            "found": False,
        }

    lines = ["Nuestras promociones vigentes son:\n"]
    for p in vigentes:
        line = f"• **{p.name}**: {p.description}"
        if p.discount_type == "percentage" and p.discount_value is not None:
            line += f" ({p.discount_value:.0f}% de descuento)"
        elif p.discount_type == "free_night" and p.discount_value is not None:
            bonif = int(p.discount_value)
            line += f" ({bonif} noche(s) bonificada(s))"
        if p.conditions:
            line += f" — Condiciones: {p.conditions}"
        lines.append(line)

    return {"tool_result": "\n".join(lines), "found": True}


def _handle_calcular_precio_promo(args: Dict, ctx: Dict) -> Dict:
    """Calcula el precio de una estadía concreta con la MEJOR promo aplicable.

    Determinístico: el descuento lo calcula el backend (nunca el LLM). Se usa SOLO
    cuando el cliente pide promo o muestra resistencia al precio (lo decide el prompt).
    Si ninguna promo calculable aplica, ofrece las cualitativas + cómo calificar (upsell).
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    room_type = (args.get("room_type") or "").strip()
    check_in_str = (args.get("check_in") or "").strip()
    check_out_str = (args.get("check_out") or "").strip()

    if not room_type or not check_in_str or not check_out_str:
        return {
            "tool_result": (
                "Para calcular una promo necesito el tipo de habitación y las fechas "
                "(check-in y check-out en formato YYYY-MM-DD)."
            )
        }

    try:
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)
    except ValueError:
        return {"tool_result": "Las fechas deben estar en formato YYYY-MM-DD."}

    nights = (check_out - check_in).days
    if nights <= 0:
        return {"tool_result": "El check-out debe ser posterior al check-in."}

    # Precio base de la habitación (fuente de verdad = USD).
    room = (
        db.query(Room)
        .filter(Room.room_type.ilike(f"%{room_type}%"))
        .first()
    )
    if room is None:
        return {"tool_result": f"No encontré la habitación '{room_type}'."}

    rate = exchange_rate_service.get_current_rate(db)["rate"]
    base_usd = room.base_price_usd

    oferta = promotions_service.mejor_promo(db, base_usd, nights)

    if oferta:
        full_usd = oferta["full_price_usd"]
        final_usd = oferta["final_price_usd"]
        savings_usd = oferta["savings_usd"]
        full_ars = round(full_usd * rate, 2)
        final_ars = round(final_usd * rate, 2)
        savings_ars = round(savings_usd * rate, 2)

        # Datos para que el orquestador arme la card con precio tachado.
        ctx["promo_offer"] = {
            "room_type": room.room_type,
            "check_in": check_in_str,
            "check_out": check_out_str,
            "nights": nights,
            "promo_name": oferta["promo_name"],
            "full_price_usd": full_usd,
            "full_price_ars": full_ars,
            "price_usd": final_usd,
            "price_ars": final_ars,
            "savings_usd": savings_usd,
            "savings_ars": savings_ars,
            "image": (room.images or [None])[0],
            "description": room.description,
            "capacity": room.capacity,
            "bed_config": room.bed_config,
            "view": room.view,
        }

        return {
            "tool_result": (
                f"Promo aplicable a {room.room_type} por {nights} noche(s): "
                f"**{oferta['promo_name']}**. "
                f"Precio sin promo: USD {full_usd:.0f}. "
                f"Con la promo: USD {final_usd:.0f} (ahorra USD {savings_usd:.0f}). "
                f"La tarjeta muestra el precio tachado y el final; comunicá el ahorro con calidez."
            ),
            "found": True,
            "promo_applied": True,
        }

    # No hay promo calculable para estas noches → cualitativas + cómo calificar (upsell).
    cualitativas = promotions_service.promos_cualitativas(db)
    cercanas = promotions_service.promos_calculables_cercanas(db, nights)

    partes = [
        f"Para {room.room_type} por {nights} noche(s) no hay un descuento directo aplicable."
    ]
    if cercanas:
        c = cercanas[0]
        faltan = c.min_nights - nights
        partes.append(
            f"Pero si sumás {faltan} noche(s) más (mínimo {c.min_nights}), accedés a "
            f"**{c.name}**: {c.description}"
        )
    if cualitativas:
        nombres = "; ".join(f"**{p.name}** ({p.description})" for p in cualitativas)
        partes.append(f"También tenemos beneficios vigentes: {nombres}.")
    if not cercanas and not cualitativas:
        partes.append(
            "No tenemos descuentos adicionales en este momento, pero la tarifa incluye "
            "todos nuestros servicios y la mejor ubicación de Bariloche."
        )

    return {
        "tool_result": " ".join(partes),
        "found": True,
        "promo_applied": False,
    }


# ---------------------------------------------------------------------------
# RESTAURANTE
# ---------------------------------------------------------------------------

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
    return {
        "type": "menu_interactive",
        "purpose": purpose,
        "title": titulo,
        "description": desc,
        "items": menu,
        "session_id": ctx.get("session_id"),
        "fallback_url": _menu_cart_url(ctx),
        "preselect": preselect or [],
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


def _handle_ver_carta(args: Dict, ctx: Dict) -> Dict:
    """Adjunta la carta del restaurante PLAZA como tarjeta interactiva en el chat.

    El texto es CORTO (la card muestra los platos); el agente agrega la intro cálida y la
    pregunta de intención. Devuelve el link a la carta completa por si el huésped la prefiere.
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    categoria = (args.get("categoria") or "").strip().lower()
    menu = restaurant_service.list_menu(db, include_inactive=False)
    if not menu:
        return {"tool_result": "Por ahora no tengo la carta disponible. Probá más tarde."}

    if categoria:
        menu = [m for m in menu if categoria in (m.get("category") or "").lower()] or menu

    # Si el huésped tiene preferencias dietéticas guardadas, recordarlas al agente.
    contact = _resolve_contact(db, ctx)
    pref_note = ""
    if contact:
        try:
            profile = contact_service.get_guest_profile(contact.id, db)
            prefs = (profile or {}).get("preferences") or {}
            diet = prefs.get("dietary") or prefs.get("dietary_restrictions") or []
            if diet:
                pref_note = f" (Preferencias del huésped: {', '.join(diet)} — sugerí acorde.)"
        except Exception:
            pass

    # Card interactiva con los platos embebidos (se arma el pedido sin salir del chat).
    ctx["menu_card"] = _build_menu_card(menu, ctx)

    return {
        "tool_result": (
            "Listo, le mostré la carta interactiva de PLAZA - Hampton's Kitchen House en el chat "
            "(puede tocar los platos para armar el pedido o abrir la carta completa)."
            + pref_note
        ),
        "found": True,
    }


def _handle_armar_pedido_carta(args: Dict, ctx: Dict) -> Dict:
    """Caso 2: el huésped dijo qué quiere por texto → devolver la carta con esos platos precargados.

    El agente pasa `items_texto` (lo que pidió en lenguaje natural). Se matchea contra la carta
    y se emite la card interactiva con el carrito ya armado para que confirme/ajuste.
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    texto = (args.get("items_texto") or "").strip()
    menu = restaurant_service.list_menu(db, include_inactive=False)
    if not menu:
        return {"tool_result": "Por ahora no tengo la carta disponible. Probá más tarde."}
    if not texto:
        # Sin texto: mostrar la carta vacía como en ver_carta.
        ctx["menu_card"] = _build_menu_card(menu, ctx)
        return {"tool_result": "Le mostré la carta para que arme su pedido.", "found": True}

    res = _match_menu_items(texto, menu)
    matched = res["matched"]
    if not matched:
        # No reconocimos nada: mostrar la carta y pedir que lo elija ahí.
        ctx["menu_card"] = _build_menu_card(menu, ctx)
        return {
            "tool_result": (
                "No logré identificar esos platos en la carta. Le mostré la carta completa "
                "para que elija directamente. (Pedí que confirme cuál plato quiere si hay dudas.)"
            ),
            "found": True,
        }

    preselect = [{"menu_item_id": m["menu_item_id"], "qty": m["qty"]} for m in matched]
    ctx["menu_card"] = _build_menu_card(menu, ctx, preselect=preselect)
    resumen = ", ".join(f"{m['qty']}x {m['name']}" for m in matched)
    return {
        "tool_result": (
            f"Armé el pedido con: {resumen}. Le dejé la carta con eso precargado para que "
            "confirme o ajuste y elija dónde lo quiere."
        ),
        "found": True,
        "preselect": preselect,
    }


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


# Mapea lenguaje natural del turno a la FRANJA del restaurante (almuerzo | cena).
# "noche/cena/a la noche/a cenar" → cena; "mediodía/almuerzo/al mediodía" → almuerzo.
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


def _handle_reservar_mesa(args: Dict, ctx: Dict) -> Dict:
    """Reserva de mesa del restaurante. Normalmente adjunta el selector (card) para que el
    huésped elija día/turno/personas. Si el agente ya trae un horario HH:MM válido, confirma
    directo. Si trae una FRANJA en lenguaje natural ("la noche", "cena"), muestra el selector
    con esa franja preseleccionada (nunca lo trata como "no disponible").
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    fecha = (args.get("fecha") or "").strip()
    turno = (args.get("turno") or args.get("hora") or "").strip()
    personas = args.get("personas") or 0
    nombre = (args.get("nombre") or "").strip()
    # Pedido especial / ocasión (champán, cumpleaños, aniversario, alergias para la cena…).
    # Se guarda en la reserva y llega al equipo del salón; no se pierde en el chat.
    notas = (args.get("notas") or args.get("ocasion") or "").strip() or None

    # "El primer día de mi estadía" / "cuando llegue": si el huésped tiene una reserva (de esta
    # sesión o su contacto) y NO dio una fecha, usamos el CHECK-IN de su reserva como fecha de
    # la mesa. Evita el selector con fecha vacía/incoherente cuando ya sabemos cuándo llega.
    derived_from_booking = False
    if not fecha:
        contact = _resolve_contact(db, ctx)
        booking = _relevant_booking_for(db, contact, ctx.get("session_id"))
        if booking and booking.check_in:
            fecha = booking.check_in.isoformat()
            derived_from_booking = True
            # Si no dio nombre, usamos el de la reserva.
            nombre = nombre or (booking.guest_name or "")

    # ¿El turno es un horario HH:MM puntual y válido? Solo entonces se puede crear directo.
    hora_valida = turno in restaurant_service._all_slots()
    # Si no es un horario puntual, ¿es una franja en lenguaje natural (ej. "la noche" → cena)?
    franja = _franja_desde_texto(turno) if not hora_valida else None

    # Faltan datos, o el turno es una franja / texto no puntual → mostrar el selector.
    # El usuario elige el horario exacto ahí (nunca decimos "no disponible" por esto).
    if not (fecha and personas) or not hora_valida:
        preset = {
            "fecha": fecha or None,
            "personas": int(personas) if personas else None,
            "nombre": nombre or None,
            "notas": notas,                    # pre-carga el pedido especial en el selector
        }
        if franja:
            preset["franja"] = franja          # preselecciona almuerzo/cena en el selector
        ctx["table_card"] = _build_table_card(ctx, preset=preset)
        if franja == "cena":
            msg = ("Le mostré el selector con el turno CENA preseleccionado para que elija el "
                   "horario (20:00 a 22:00). Confirmale con calidez que la cena está disponible "
                   "y pedile que elija el horario ahí; NO le digas que no hay turno de noche.")
        elif franja == "almuerzo":
            msg = ("Le mostré el selector con el turno ALMUERZO preseleccionado (12:30 a 14:30). "
                   "Pedile que elija el horario ahí; NO le pidas la hora por texto.")
        else:
            msg = ("Le mostré un selector para reservar la mesa (día, turno y personas). "
                   "Pedile que lo complete ahí; no le pidas la hora por texto.")
        return {"tool_result": msg, "found": True}

    # Datos completos con HORARIO VÁLIDO → confirmar directo (camino híbrido).
    contact = _resolve_contact(db, ctx)
    result = restaurant_service.create_table_reservation(
        db,
        fecha=fecha, hora=turno, party_size=int(personas),
        guest_name=nombre or None,
        contact_id=contact.id if contact else None,
        booking_code=(args.get("codigo_reserva") or "").strip() or None,
        session_id=ctx.get("session_id"),
        notes=notas,
        channel="web",
    )
    if "error" in result:
        # Si el dato vino mal, caemos al selector.
        ctx["table_card"] = _build_table_card(ctx)
        return {"tool_result": f"No pude reservar: {result['error']} Le muestro el selector para reintentar."}

    return {
        "tool_result": (
            f"¡Mesa reservada! Código {result['code']} para {result['party_size']} persona(s). "
            "Confirmá con calidez."
        ),
        "reservation": result,
        "found": True,
    }


def _handle_comprar_voucher(args: Dict, ctx: Dict) -> Dict:
    """Abre la carta en modo VOUCHER para que un visitante compre platos por anticipado.

    El visitante arma su pedido en la card y recibe un código VCH-XXXX para canjear cuando
    venga. Solo para visitantes (el huésped alojado usa el folio, Fase 1).
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    menu = restaurant_service.list_menu(db, include_inactive=False)
    if not menu:
        return {"tool_result": "Por ahora no tengo la carta disponible. Probá más tarde."}

    ctx["menu_card"] = _build_menu_card(menu, ctx, purpose="voucher")
    return {
        "tool_result": (
            "Le mostré la carta en modo voucher: que elija los platos y confirme; recibirá un "
            "código VCH-XXXX para canjear cuando venga. Tras emitirlo, ofrecé reservar una mesa "
            "para usarlo."
        ),
        "found": True,
    }


def _handle_registrar_pedido(args: Dict, ctx: Dict) -> Dict:
    """Registra un pedido que el huésped armó en la pantalla de carrito (por order_code)."""
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    order_code = (args.get("order_code") or "").strip().upper()
    if order_code:
        o = restaurant_service.get_order(db, order_code)
        if not o:
            return {"tool_result": f"No encontré el pedido {order_code}. ¿Lo armaste en el link de la carta?"}
        # El pedido ya fue creado por la pantalla de carrito; acá solo confirmamos.
        items_txt = ", ".join(f"{it['qty']}x {it['name']}" for it in o.get("items", []))
        dest = {"room_service": "a tu habitación", "salon": "en el salón", "retiro": "para retirar"}.get(
            o.get("fulfillment"), "")
        pago = "cargado a tu habitación" if o.get("payment_mode") == "folio" else "con link de pago"
        extra = ""
        if o.get("payment_mode") == "folio" and o.get("booking_code"):
            extra = f" Lo sumé al folio de tu reserva {o['booking_code']}."
        return {
            "tool_result": (
                f"¡Pedido confirmado! 🍽️ {items_txt} ({dest}). "
                f"Total: USD {o['total_usd']:.0f} / ARS {o['total_ars']:,.0f}, {pago}.{extra} "
                f"El equipo ya fue avisado."
            ),
            "order": o,
        }

    return {
        "tool_result": (
            "Para registrar tu pedido necesito que lo armes primero en la carta "
            "(te paso el link con `ver_carta`) y me confirmes cuando termines."
        )
    }


# Palabras que marcan una ALERGIA / intolerancia (seguridad alimentaria → categoría aparte).
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


def _handle_guardar_preferencia(args: Dict, ctx: Dict) -> Dict:
    """Guarda una preferencia/alergia del huésped en su perfil (para tener siempre en cuenta).

    Distingue ALERGIAS (seguridad alimentaria, categoría `allergies`) de las preferencias
    dietéticas (vegano, vegetariano, sin TACC → `dietary`). El agente puede mandar un
    `tipo` ('alergia'|'dieta'); si no, se clasifica por el texto.
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    contact = _resolve_contact(db, ctx)
    if not contact:
        return {"tool_result": "Anotado. (No pude vincularlo a un perfil, pero lo tendré en cuenta en esta charla.)"}

    nuevas = args.get("preferencias") or []
    if isinstance(nuevas, str):
        nuevas = [nuevas]
    nuevas = [str(p).strip().lower() for p in nuevas if str(p).strip()]
    if not nuevas:
        return {"tool_result": "¿Qué preferencia o alergia querés que guarde? (ej: vegetariano, sin TACC, alergia al maní)"}

    tipo_hint = args.get("tipo")

    try:
        profile = contact_service.get_guest_profile(contact.id, db)
        prefs = (profile or {}).get("preferences") or {}
    except Exception:
        prefs = {}

    nuevas_alergias, nuevas_dietas = persist_preferences(db, contact, nuevas, tipo_hint)

    # Mensaje de confirmación diferenciado: la alergia se confirma con énfasis.
    partes = []
    if nuevas_alergias:
        partes.append(
            f"⚠️ Anoté tu alergia/intolerancia ({', '.join(nuevas_alergias)}). "
            "La voy a tener SIEMPRE en cuenta: no te voy a sugerir nada que la contenga."
        )
    if nuevas_dietas:
        partes.append(
            f"Guardé tus preferencias ({', '.join(nuevas_dietas)}) en tu perfil. "
            "Las voy a usar para sugerirte opciones acordes. 🌿"
        )
    return {
        "tool_result": " ".join(partes) or "Listo, lo guardé en tu perfil.",
        "saved": True,
    }


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


# ---------------------------------------------------------------------------
# DISPATCHER
# ---------------------------------------------------------------------------

_DISPATCH = {
    "info_hotel": _handle_info_hotel,
    "consultar_disponibilidad": _handle_consultar_disponibilidad,
    "crear_reserva": _handle_crear_reserva,
    "consultar_reserva": _handle_consultar_reserva,
    "info_pago": _handle_info_pago,
    "como_llegar": _handle_como_llegar,
    "comercios_amigos": _handle_comercios_amigos,
    "excursiones_y_atracciones": _handle_excursiones_y_atracciones,
    "promos_vigentes": _handle_promos_vigentes,
    "calcular_precio_promo": _handle_calcular_precio_promo,
    "ver_carta": _handle_ver_carta,
    "armar_pedido_carta": _handle_armar_pedido_carta,
    "registrar_pedido": _handle_registrar_pedido,
    "reservar_mesa": _handle_reservar_mesa,
    "comprar_voucher": _handle_comprar_voucher,
    "guardar_preferencia": _handle_guardar_preferencia,
}


async def execute_tool(name: str, args: Dict, ctx: Dict) -> Dict:
    """
    Ejecuta una tool por nombre. `ctx` es un dict mutable compartido por turno.
    Mismo contrato que agent_tools.execute_tool de Freeway.

    Returns:
        Dict con al menos la key 'tool_result' (string que se reinyecta al LLM).
    """
    handler = _DISPATCH.get(name)
    if handler is None:
        logger.warning("Unknown hotel tool requested", tool=name)
        return {"tool_result": f"Herramienta desconocida: {name}"}

    try:
        import inspect
        if inspect.iscoroutinefunction(handler):
            return await handler(args, ctx)
        return handler(args, ctx)
    except Exception as e:
        logger.error("Error executing hotel tool", tool=name, error=str(e))
        return {"tool_result": f"Error ejecutando {name}: {e}"}
