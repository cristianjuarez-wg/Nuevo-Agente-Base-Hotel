"""Handlers de hotel tools — grupo restaurant (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared


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
            "Listo, le mostré la carta interactiva del restaurante en el chat "
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

    # Canal: en WhatsApp NO hay selector interactivo (la table_card no se renderiza), así que la
    # mesa solo puede reservarse pidiendo la hora por texto y creando directo. En web sí hay selector.
    session_id = ctx.get("session_id") or ""
    is_whatsapp = session_id.startswith("wa_")

    # Normalizamos el turno a un slot real ("a las 20" → "20:00"). Clave en WhatsApp, donde la
    # hora llega en texto libre. Solo da un slot si existe; si no, queda None.
    hora_norm = _normalizar_turno(turno)
    hora_valida = hora_norm is not None
    if hora_valida:
        turno = hora_norm
    # Si no es una hora puntual, ¿es una franja en lenguaje natural (ej. "la noche" → cena)?
    franja = _franja_desde_texto(turno) if not hora_valida else None

    # Faltan datos o no hay hora puntual válida.
    if not (fecha and personas) or not hora_valida:
        if is_whatsapp:
            # WhatsApp: no hay selector → pedimos lo que falte POR TEXTO. found=False para que el
            # agente NO confirme una reserva inexistente (anti-fantasma).
            faltan = []
            if not fecha:
                faltan.append("para qué día")
            if not personas:
                faltan.append("cuántas personas")
            if not hora_valida:
                faltan.append("a qué hora exacta (almuerzo 12:30–14:30 o cena 20:00–22:00)")
            pedido = "; ".join(faltan)
            return {
                "tool_result": (
                    f"AÚN NO está reservada la mesa: falta {pedido}. Pediselo al huésped por "
                    "texto, con calidez, y cuando lo tengas VOLVÉ a llamar `reservar_mesa` con esos "
                    "datos. NO confirmes la reserva hasta que esta tool devuelva un código MESA-XXXX."
                ),
                "found": False,
            }
        # Web: mostramos el selector (camino actual).
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
        channel="whatsapp" if is_whatsapp else "web",
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
