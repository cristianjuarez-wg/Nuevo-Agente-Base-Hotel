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
from app.models.promotions import Promotion
from app.services import promotions_service
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
    )

    if "error" in result:
        return {"tool_result": result["error"]}

    code = result.get("code", "")
    nights = result.get("nights", 0)
    total_usd = result.get("total_price_usd", 0)
    total_ars = result.get("total_price_ars", 0)
    room = result.get("room_type", room_type)

    logger.info("Reservation created via agent tool", code=code, guest=guest_name)

    return {
        "tool_result": (
            f"¡Reserva confirmada! 🎉\n"
            f"Código de reserva: **{code}**\n"
            f"Habitación: {room}\n"
            f"Check-in: {check_in} | Check-out: {check_out} ({nights} noche(s))\n"
            f"Huésped: {guest_name}\n"
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
