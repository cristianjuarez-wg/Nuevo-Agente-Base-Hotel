"""Handlers de hotel tools — grupo booking (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared

# `logger` se usa en este módulo (disponibilidad/crear_reserva) pero no venía del import *
# de _shared (no está en su __all__): sin esto, crear_reserva lanzaba NameError en runtime.
logger = get_logger(__name__)  # noqa: F405


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

    # SELECCIÓN de tarjetas: el backend elige las más adecuadas (no depende de que el LLM
    # pase room_types). Excluye la accesible salvo pedido. Texto y tarjetas usan el MISMO set
    # seleccionado, para que la prosa de Aura coincida con lo que ve el huésped.
    requested = args.get("room_types") or []
    if isinstance(requested, str):
        requested = [requested]
    requested = [str(t).strip().lower() for t in requested if str(t).strip()]

    cards = _select_room_cards(
        rooms, requested,
        wants_access=_wants_accessibility(ctx),
        wants_all=_wants_all_rooms(ctx),
    )
    ctx["rooms_offered"] = cards

    from app.utils.money import format_price_pair
    from app.services import business_profile_service
    _prof = business_profile_service.get_profile(ctx.get("db"))
    lines = [
        f"Habitaciones disponibles para {composicion}, "
        f"{cards[0].get('nights')} noche(s) ({check_in} → {check_out}):\n"
    ]
    for r in cards:
        precio = format_price_pair(r['total_price_usd'], r['total_price_ars'], _prof,
                                   amount_primary=r.get('total_price_primary'))
        lines.append(
            f"• {r['room_type']}: {precio} "
            f"en total ({r['units_available']} unidad(es) disponible(s)). "
            f"{r.get('bed_config', '')}. "
            f"Capacidad: {r['capacity']} pax."
        )

    return {"tool_result": "\n".join(lines), "rooms": cards}


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

    from app.utils.money import format_price_pair
    from app.services import business_profile_service
    _prof = business_profile_service.get_profile(ctx.get("db"))
    return {
        "tool_result": (
            f"¡Reserva confirmada! 🎉\n"
            f"Código de reserva: **{code}**\n"
            f"Habitación: {room}\n"
            f"Check-in: {check_in} | Check-out: {check_out} ({nights} noche(s))\n"
            f"Huésped: {guest_name}\n"
            f"{promo_line}"
            f"Total: {format_price_pair(total_usd, total_ars, _prof)}\n"
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

    # Recordar el código validado en esta charla: si luego pide comida, el checkout lo reusa
    # (no le re-preguntamos si es huésped ni el código). El gate de folio (in-house) lo
    # revalida el server igual.
    ctx["booking_code"] = booking["code"]

    from app.utils.money import format_price_pair
    from app.services import business_profile_service
    _prof = business_profile_service.get_profile(ctx.get("db"))
    return {
        "tool_result": (
            f"Reserva {booking['code']}:\n"
            f"• Habitación: {booking.get('room_type', 'N/A')}\n"
            f"• Huésped: {booking['guest_name']}\n"
            f"• Check-in: {booking['check_in']} | Check-out: {booking['check_out']} "
            f"({booking['nights']} noche(s))\n"
            f"• Huéspedes: {booking['guests']}\n"
            f"• Total: {format_price_pair(booking['total_price_usd'], booking['total_price_ars'], _prof)}\n"
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
        from app.services import business_profile_service
        from app.services.hotel_tools_pkg.info import _contact_sentence
        c = business_profile_service.get_contact(db)
        return {
            "tool_result": (
                "No tengo cargados los datos de pago en este momento." + _contact_sentence(c)
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
