"""Handlers de hotel tools — grupo info (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared


def _contact_sentence(contact: dict) -> str:
    """Frase de contacto para fallbacks, u '' si el cliente no cargó tel/email (3.5).

    Evita mostrar el contacto de otro hotel: si el perfil no tiene datos, se omite la línea.
    """
    phone = (contact or {}).get("phone", "")
    email = (contact or {}).get("email", "")
    partes = []
    if phone:
        partes.append(f"al {phone}")
    if email:
        partes.append(f"en {email}")
    if not partes:
        return ""
    return " Para más detalles podés contactarnos " + " o ".join(partes) + "."


async def _handle_info_hotel(args: Dict, ctx: Dict) -> Dict:
    """RAG sobre documentos del hotel (habitaciones, servicios, ubicación, promos)."""
    query = (args.get("query") or "").strip() or ctx.get("message", "")
    result = await rag_service.retrieve_context_with_sources(
        query=query,
        conversation_history=ctx.get("history"),
    )
    context = result.get("context", "NO_CONTEXT_FOUND")

    if context == "NO_CONTEXT_FOUND":
        from app.services import business_profile_service
        c = business_profile_service.get_contact(ctx.get("db"))
        contacto = _contact_sentence(c)
        return {
            "found": False,
            "tool_result": (
                "No encontré información específica sobre eso en nuestra base de datos." + contacto
            ),
        }

    ctx["document_sources"] = result.get("sources", [])
    # Anti prompt-injection (Fase 3.3): el contenido del RAG lo sube el cliente y NO es
    # confiable. Se envuelve en delimitadores; el prompt del agente (ANTI_INJECTION_BLOCK)
    # sabe que lo delimitado es referencia, no instrucciones.
    from app.domains.hotel.prompts.base_blocks import wrap_untrusted_docs
    return {
        "found": True,
        "tool_result": wrap_untrusted_docs(context),
    }


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
