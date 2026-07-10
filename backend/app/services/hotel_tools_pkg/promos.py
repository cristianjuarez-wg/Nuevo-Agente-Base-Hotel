"""Handlers de hotel tools — grupo promos (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared


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
        free_nights = oferta.get("free_nights", 0)
        paid_nights = oferta.get("paid_nights", nights)
        full_ars = round(full_usd * rate, 2)
        final_ars = round(final_usd * rate, 2)
        savings_ars = round(savings_usd * rate, 2)

        # Mecánica EXACTA para estas noches (la tool la dicta; el LLM no la deduce del
        # nombre de la promo). Ej. "4x3" aplicada a 5 noches = pagás 4, 1 bonificada.
        if free_nights > 0:
            mecanica = (
                f"pagás {paid_nights} noche(s) y {free_nights} noche(s) van bonificadas "
                f"(gratis), sobre un total de {nights} noche(s)"
            )
        else:
            mecanica = f"se aplica un descuento sobre las {nights} noche(s)"

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
                f"Promo aplicable a {room.room_type} para {nights} noche(s): "
                f"**{oferta['promo_name']}** — {mecanica}. "
                f"Precio sin promo: USD {full_usd:.0f}. "
                f"Con la promo: USD {final_usd:.0f} (ahorra USD {savings_usd:.0f}). "
                f"COMUNICÁ LA MECÁNICA TAL CUAL ESTÁ ARRIBA: NO la deduzcas del nombre de la "
                f"promo. Decí cuántas noches paga y cuántas van gratis para ESTA estadía; "
                f"no traslades el nombre (ej. '4x3') como si fuera el resultado de estas noches. "
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
