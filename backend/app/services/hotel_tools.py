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

    # Guardar las habitaciones en el ctx para que el orquestador arme las tarjetas del chat.
    ctx["rooms_offered"] = rooms

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


def _handle_ver_carta(args: Dict, ctx: Dict) -> Dict:
    """Devuelve la carta del restaurante PLAZA y un link para armar el pedido."""
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    categoria = (args.get("categoria") or "").strip().lower()
    menu = restaurant_service.list_menu(db, include_inactive=False)
    if not menu:
        return {"tool_result": "Por ahora no tengo la carta disponible. Probá más tarde."}

    if categoria:
        menu = [m for m in menu if categoria in (m.get("category") or "").lower()] or menu

    # Si el huésped tiene preferencias, resaltarlas para sugerir.
    contact = _resolve_contact(db, ctx)
    pref_note = ""
    if contact:
        try:
            profile = contact_service.get_guest_profile(contact.id, db)
            prefs = (profile or {}).get("preferences") or {}
            diet = prefs.get("dietary") or prefs.get("dietary_restrictions") or []
            if diet:
                pref_note = f" (Tené en cuenta sus preferencias: {', '.join(diet)} — sugerí acorde.)"
        except Exception:
            pass

    # Agrupar por categoría para el texto.
    by_cat: Dict[str, list] = {}
    for m in menu:
        by_cat.setdefault(m["category"], []).append(m)
    lines = ["Carta del restaurante PLAZA - Hampton's Kitchen House:\n"]
    for cat, items in by_cat.items():
        lines.append(f"**{cat.capitalize()}**")
        for m in items[:8]:
            tags = f" [{', '.join(m['tags'])}]" if m.get("tags") else ""
            lines.append(f"• {m['name']} — USD {m['price_usd']:.0f}{tags}")
    cart_url = f"{settings.LANDING_URL.rstrip('/')}/#pedido"
    sid = ctx.get("session_id")
    if sid:
        cart_url += f"?session={sid}"
    lines.append(f"\nPara armar tu pedido entrá acá: {cart_url}")
    if pref_note:
        lines.append(pref_note)

    # Card para el chat web con botón que abre la pantalla de carrito.
    ctx["menu_card"] = {
        "type": "menu",
        "title": "Carta del restaurante",
        "description": "Cocina patagónica de PLAZA - Hampton's Kitchen House.",
        "action": {"kind": "open_url", "label": "Ver carta y pedir", "url": cart_url},
    }

    return {"tool_result": "\n".join(lines), "found": True}


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


def _handle_guardar_preferencia(args: Dict, ctx: Dict) -> Dict:
    """Guarda una preferencia dietética del huésped en su perfil (para sugerir a futuro)."""
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
        return {"tool_result": "¿Qué preferencia querés que guarde? (ej: vegetariano, sin TACC, alergia al maní)"}

    try:
        profile = contact_service.get_guest_profile(contact.id, db)
        prefs = (profile or {}).get("preferences") or {}
    except Exception:
        prefs = {}
    diet = set(prefs.get("dietary") or [])
    diet.update(nuevas)
    prefs["dietary"] = sorted(diet)
    contact_service.set_preferences(contact.id, prefs, db)

    return {
        "tool_result": (
            f"Listo, guardé tus preferencias ({', '.join(nuevas)}) en tu perfil. "
            "Las voy a tener en cuenta para sugerirte opciones acordes. 🌿"
        ),
        "saved": True,
    }


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
    "promos_vigentes": _handle_promos_vigentes,
    "calcular_precio_promo": _handle_calcular_precio_promo,
    "ver_carta": _handle_ver_carta,
    "registrar_pedido": _handle_registrar_pedido,
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
