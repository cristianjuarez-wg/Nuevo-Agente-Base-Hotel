from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ClearHistoryResponse,
    GreetingResponse,
    AgentStatsResponse,
    DestinationsResponse,
    GeographyAnalysis,
    SessionInfo
)
from app.models.database import get_db
from app.services.agent_service import agent_service
from app.services.rag_service import rag_service
from app.services.metrics_service import metrics_service
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.rate_limit import limiter, CHAT_RATE_LIMIT
import asyncio
import time
from datetime import datetime

CHAT_TIMEOUT_SECONDS = 60

# Mensajes de borde que llegan directo al usuario SIN pasar por el LLM (timeout, error).
# Son los únicos textos fijos del endpoint que conviene traducir para coherencia.
_EDGE_MESSAGES = {
    "timeout": {
        "es": "Lo siento, la respuesta tardó demasiado. Por favor, intentá de nuevo.",
        "en": "Sorry, the response took too long. Please try again.",
        "pt": "Desculpe, a resposta demorou demais. Por favor, tente novamente.",
        "fr": "Désolé, la réponse a pris trop de temps. Veuillez réessayer.",
    },
    "error": {
        "es": "Lo siento, ocurrió un error procesando tu mensaje. Por favor, intentá de nuevo.",
        "en": "Sorry, an error occurred while processing your message. Please try again.",
        "pt": "Desculpe, ocorreu um erro ao processar sua mensagem. Por favor, tente novamente.",
        "fr": "Désolé, une erreur s'est produite lors du traitement de votre message. Veuillez réessayer.",
    },
}


def _edge_message(key: str, language: str) -> str:
    """Texto de borde (timeout/error) en el idioma activo, con fallback a español."""
    return _EDGE_MESSAGES.get(key, {}).get((language or "es").lower(), _EDGE_MESSAGES[key]["es"])


# Saludo inicial por idioma. Para "es" se usa el del perfil (profile_manager); para el
# resto, estos saludos cortos (el saludo es lo único visible del greeting al cambiar idioma).
_GREETINGS = {
    "en": "Hi! I'm Aura, your virtual concierge at Hampton by Hilton Bariloche. How can I help you?",
    "pt": "Olá! Sou a Aura, sua concierge virtual no Hampton by Hilton Bariloche. Como posso ajudar?",
    "fr": "Bonjour ! Je suis Aura, votre concierge virtuelle au Hampton by Hilton Bariloche. Comment puis-je vous aider ?",
}

# Marca de arranque del proceso, para reportar uptime en /stats.
_SERVICE_START = time.monotonic()


def _format_uptime(seconds: float) -> str:
    """Formatea un lapso en segundos como 'Xd Yh Zm Ws' (omitiendo las unidades en 0)."""
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Imagen de respaldo cuando una habitación no tiene foto cargada.
_ROOM_FALLBACK_IMG = "/fotos/habitacion-vista-lago.jpg"


def _date_picker_card(suggested_month: str | None = None) -> dict:
    """Tarjeta de selección de fechas + huéspedes que el front renderiza como controles.

    `suggested_month` ('YYYY-MM') hace que el picker ABRA en ese mes si el huésped lo mencionó.
    """
    return {
        "type": "date_picker",
        "title": "Elegí las fechas de tu estadía",
        # El front usa esto para abrir el calendario en el mes mencionado (si lo hay).
        "preset": {"month": suggested_month} if suggested_month else {},
        "action": {
            "kind": "send_message",
            "label": "Ver disponibilidad",
            # El front compone el message real con las fechas elegidas.
        },
    }


# Señales en la respuesta del agente de que está pidiendo fechas/huéspedes.
_DATE_REQUEST_HINTS = (
    "fecha", "check-in", "check in", "checkin", "qué día", "que dia",
    "cuándo", "cuando", "disponibilidad para",
)

# Tools que indican que el usuario YA pasó la etapa de elegir fechas: mostró
# disponibilidad, creó o consultó una reserva. En esos turnos NO se ofrece el
# date picker aunque la respuesta mencione "fecha" (ej. al confirmar una reserva
# el agente dice "Fechas: del 12 al 15…", lo que no debe reabrir el selector).
_BOOKING_FLOW_TOOLS = ("consultar_disponibilidad", "crear_reserva", "consultar_reserva")


# Señales en el MENSAJE DEL USUARIO de que pide ver la carta / el menú. Fallback
# determinístico: si el huésped pide la carta y el LLM no llamó `ver_carta`, igual
# adjuntamos la card interactiva (que nunca quede "te envío la carta" sin carta).
_MENU_REQUEST_HINTS = (
    "carta", "menu", "menú", "para comer", "para cenar", "para almorzar",
    "para tomar", "qué hay de comer", "que hay de comer", "qué comer", "que comer",
    "room service", "pedir comida", "restaurante",
)
_MENU_TOOLS = ("ver_carta", "armar_pedido_carta")
# Señales de que el usuario quiere RESERVAR UNA MESA (no ver la carta): en ese caso el
# fallback de la carta NO debe dispararse aunque el mensaje diga "cenar/comer".
_TABLE_INTENT_HINTS = ("reservar mesa", "reservar una mesa", "una mesa", "reserva de mesa",
                       "mesa para", "reservar lugar")

# Señales de que el usuario quiere RESERVAR UNA HABITACIÓN (no comida): la carta del
# restaurante NO debe ofrecerse en estos turnos. Defensa en profundidad para que el flujo
# de reservas del hotel nunca dispare el fallback de menú por una colisión de palabras.
_ROOM_BOOKING_HINTS = ("reservar la habitación", "reservar la habitacion", "reservar habitación",
                       "reservar habitacion", "reservar una habitación", "reservar una habitacion",
                       "quiero reservar", "hacer una reserva", "confirmar la reserva",
                       "reservar la suite", "reservar el", "quiero la habitación",
                       "quiero la habitacion")


def _should_offer_menu(user_message: str, tools_used: list, has_other_cards: bool,
                       context_type: str = "", db=None) -> bool:
    """Decide si adjuntar la carta interactiva como fallback determinístico.

    Dispara si: el agente NO usó una tool de carta este turno (si la usó, la card ya viene),
    no hay otra card con prioridad, no es post-venta, no es intención de reservar mesa, y o
    bien (a) el MENSAJE pide la carta/menú, o (b) el mensaje parece un PEDIDO (menciona platos).
    """
    if has_other_cards:
        return False
    # En charla casual o post-venta NUNCA se ofrece la carta como fallback: solo aplica en
    # pre-venta cuando el huésped realmente pide comida. (Evita falsos positivos como "página"
    # matcheando "gin" del trago "Gin Athos" en medio de una charla informal.)
    if context_type in ("casual", "postsale"):
        return False
    if any(t in (tools_used or []) for t in _MENU_TOOLS):
        return False
    text = (user_message or "").lower()
    # Si quiere reservar mesa, la carta no aplica (es otra intención).
    if any(h in text for h in _TABLE_INTENT_HINTS):
        return False
    # Si quiere reservar una HABITACIÓN, la carta tampoco aplica: estamos en el flujo de
    # reserva del hotel, no pidiendo comida.
    if any(h in text for h in _ROOM_BOOKING_HINTS):
        return False
    if any(h in text for h in _MENU_REQUEST_HINTS):
        return True
    # (b) Pedido por texto: el mensaje menciona platos concretos de la carta.
    if db is not None:
        try:
            from app.services import restaurant_service
            from app.services.hotel_tools import _match_menu_items
            menu = restaurant_service.list_menu(db, include_inactive=False)
            if _match_menu_items(text, menu).get("matched"):
                return True
        except Exception:
            pass
    return False


def _should_offer_table(user_message: str, tools_used: list, has_other_cards: bool,
                        context_type: str = "") -> bool:
    """Fallback determinístico del selector de mesa: si el usuario quiere reservar mesa y el
    agente no llamó `reservar_mesa` ni hay otra card, igual mostramos el selector."""
    if has_other_cards:
        return False
    if context_type in ("postsale", "casual"):
        return False
    if "reservar_mesa" in (tools_used or []):
        return False
    text = (user_message or "").lower()
    return any(h in text for h in _TABLE_INTENT_HINTS)


def _build_table_card_fallback(db, session_id: str) -> dict:
    """Selector de reserva de mesa construido determinísticamente."""
    from app.services import restaurant_service
    return {
        "type": "table_reservation",
        "title": "Reservar una mesa",
        "description": "Elegí el día, el turno y cuántas personas.",
        "slots": restaurant_service.RESTAURANT_SLOTS,
        "session_id": session_id,
        # Si ya reservó en esta sesión, la card no le pide el código (se asocia por session_id).
        "preset": restaurant_service.session_guest_preset(db, session_id),
    }


def _build_menu_card_fallback(db, session_id: str, user_message: str = "") -> dict:
    """Carta interactiva construida determinísticamente (sin pasar por el LLM).

    Si el `user_message` parece un pedido (menciona platos de la carta), precarga el carrito
    con esos platos (caso 2: pedido por texto que el LLM no ruteó por la tool).
    """
    from app.services import restaurant_service
    from app.services.hotel_tools import _match_menu_items
    from app.config import settings
    menu = restaurant_service.list_menu(db, include_inactive=False)
    if not menu:
        return None
    url = f"{settings.LANDING_URL.rstrip('/')}/#pedido"
    if session_id:
        url += f"?session={session_id}"
    preselect = []
    try:
        matched = _match_menu_items(user_message or "", menu).get("matched", [])
        preselect = [{"menu_item_id": m["menu_item_id"], "qty": m["qty"]} for m in matched]
    except Exception:
        preselect = []
    return {
        "type": "menu_interactive",
        "title": "Carta del restaurante",
        "description": "Cocina patagónica de PLAZA - Hampton's Kitchen House.",
        "items": menu,
        "session_id": session_id,
        "fallback_url": url,
        "preselect": preselect,
    }


import re as _re_dates

# Detecta fechas explícitas ya dadas: "2026-07-24", "del 24 al 31", "24/07", "24 de julio".
_DATE_GIVEN_PATTERNS = (
    _re_dates.compile(r"\d{4}-\d{2}-\d{2}"),                       # 2026-07-24
    _re_dates.compile(r"\d{1,2}\s*/\s*\d{1,2}"),                   # 24/07
    _re_dates.compile(r"del\s+\d{1,2}\b.*\bal\s+\d{1,2}\b"),       # del 24 al 31
    _re_dates.compile(r"\d{1,2}\s+de\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)", _re_dates.I),
)


def _dates_already_given(user_message: str, history: list) -> bool:
    """True si el usuario YA dio fechas concretas (en este mensaje o en el historial).

    Evita reabrir el date picker cuando ya hay fechas: el selector solo sirve para CAPTURAR
    fechas que faltan, no para repetirlas. Mira el mensaje actual y los mensajes 'user' del
    historial reciente.
    """
    blobs = [user_message or ""]
    for m in (history or [])[-12:]:
        if m.get("role") == "user":
            blobs.append(m.get("content") or "")
    text = " ".join(blobs).lower()
    return any(p.search(text) for p in _DATE_GIVEN_PATTERNS)


# Meses en español (nombre completo) → número. Para posicionar el date picker en el mes que
# el huésped mencionó ("alojarme en septiembre").
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MES_PATTERN = _re_dates.compile(
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    _re_dates.I,
)


def _suggested_month(user_message: str) -> str | None:
    """Si el mensaje menciona un mes, devuelve 'YYYY-MM' de la PRÓXIMA ocurrencia de ese mes.

    Si el mes ya pasó este año (o es el mes actual), usa el año siguiente, para que el picker
    abra en una fecha futura coherente con una estadía. None si no se menciona ningún mes.
    """
    if not user_message:
        return None
    m = _MES_PATTERN.search(user_message)
    if not m:
        return None
    mes = _MESES[m.group(1).lower()]
    hoy = datetime.now()
    anio = hoy.year if mes > hoy.month else hoy.year + 1
    return f"{anio:04d}-{mes:02d}"


def _should_offer_datepicker(response_text: str, tools_used: list, has_room_cards: bool,
                             context_type: str = "", dates_given: bool = False) -> bool:
    """Decide si adjuntar el selector de fechas.

    El picker SOLO tiene sentido en PRE-VENTA cuando el agente está pidiendo fechas que el
    usuario AÚN NO dio. En post-venta/casual nunca se ofrece; tampoco si ya se mostraron
    habitaciones, se tocó una tool de reserva en el turno, o el usuario YA dio fechas en la
    conversación (aunque la respuesta vuelva a mencionar "fecha"/"del 24 al 31").
    """
    if context_type in ("postsale", "casual"):
        return False
    if has_room_cards:
        return False
    if dates_given:
        return False
    used = tools_used or []
    if any(t in used for t in _BOOKING_FLOW_TOOLS):
        return False
    text = (response_text or "").lower()
    return any(h in text for h in _DATE_REQUEST_HINTS)


def _build_room_cards(rooms_offered: list) -> list:
    """Arma tarjetas de habitación a partir de las habitaciones que ofreció la tool.

    Determinístico: sale de los datos reales de disponibilidad, no del LLM. Cada tarjeta
    lleva lo necesario para renderizar en el chat (imagen, tipo, precios, capacidad) y la
    acción 'reservar' (que el front convierte en un mensaje al chat).
    """
    cards = []
    for r in rooms_offered or []:
        images = r.get("images") or []
        image = images[0] if images else _ROOM_FALLBACK_IMG
        cards.append({
            "type": "room",
            "title": r.get("room_type"),
            "description": r.get("description"),
            "image": image,
            "price_usd": r.get("total_price_usd"),
            "price_ars": r.get("total_price_ars"),
            "price_usd_night": r.get("base_price_usd"),
            "nights": r.get("nights"),
            "capacity": r.get("capacity"),
            "bed_config": r.get("bed_config"),
            "view": r.get("view"),
            "units_available": r.get("units_available"),
            "action": {
                "kind": "send_message",
                "label": "Reservar esta habitación",
                "message": f"Quiero reservar la habitación {r.get('room_type')}",
            },
        })
    return cards


def _build_promo_card(offer: dict) -> dict:
    """Arma la tarjeta de oferta con promo (precio lleno tachado + final + ahorro).

    `offer` viene del handler calcular_precio_promo (ctx['promo_offer']): ya trae el
    precio sin promo, el precio con promo, el ahorro y los datos de la habitación.
    """
    image = offer.get("image") or _ROOM_FALLBACK_IMG
    return {
        "type": "room",
        "title": offer.get("room_type"),
        "description": offer.get("description"),
        "image": image,
        "price_usd": offer.get("price_usd"),          # final (con promo)
        "price_ars": offer.get("price_ars"),
        "full_price_usd": offer.get("full_price_usd"),  # tachado
        "full_price_ars": offer.get("full_price_ars"),
        "savings_usd": offer.get("savings_usd"),
        "savings_ars": offer.get("savings_ars"),
        "promo_name": offer.get("promo_name"),
        "nights": offer.get("nights"),
        "capacity": offer.get("capacity"),
        "bed_config": offer.get("bed_config"),
        "view": offer.get("view"),
        "action": {
            "kind": "send_message",
            "label": "Reservar esta habitación",
            "message": f"Quiero reservar la habitación {offer.get('room_type')}",
        },
    }

@router.post("/message", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
async def send_message(request: Request, chat_request: ChatRequest, db: Session = Depends(get_db)):
    """Envía mensaje al agente y obtiene respuesta"""
    start_time = time.time()
    
    logger.info("Chat message received",
               session_id=chat_request.session_id,
               message_length=len(chat_request.message))
    
    try:
        # Procesar mensaje con el agente (timeout para evitar esperas indefinidas)
        try:
            result = await asyncio.wait_for(
                agent_service.chat(db, chat_request.message, chat_request.session_id, chat_request.language),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("Chat message timed out",
                        session_id=chat_request.session_id,
                        timeout_seconds=CHAT_TIMEOUT_SECONDS)
            return ChatResponse(
                response=_edge_message("timeout", chat_request.language),
                has_context=False,
                geography_analysis={},
                error=True,
                error_type="timeout",
                processing_time=f"{CHAT_TIMEOUT_SECONDS}s",
            )
        
        # 🆕 FIX: Corregir nombres de paquetes truncados o incompletos
        import re
        document_sources = result.get("document_sources", [])
        response_text = result["response"]
        
        if document_sources:
            for source in document_sources:
                # Obtener nombre completo del documento
                package_name = source.get("document", "").replace(".pdf", "").replace(".PDF", "")
                
                # Solo procesar paquetes multi-país o con guión
                if " y " in package_name or " - " in package_name:
                    # Extraer la parte de países (antes del guión)
                    countries_part = package_name.split(" - ")[0] if " - " in package_name else package_name
                    
                    # Extraer todos los países del nombre
                    countries = []
                    for part in countries_part.split(" y "):
                        for country in part.split(","):
                            country = country.strip()
                            # Filtrar palabras que no son países
                            if country and not any(word in country.lower() for word in ["todo", "incluido", "desde"]):
                                countries.append(country)
                    
                    # Buscar patrones truncados con CUALQUIERA de los países
                    for country in countries:
                        # Patrón 1: "**País y -**" o "**País y -" (truncado con guión)
                        pattern1 = rf'\*\*{re.escape(country)}\s+y\s+-\s*\*?\*?'
                        # Patrón 2: "**Países**" sin el sufijo (ej: "**Japón y Corea Del Sur**" sin "- Todo Incluido")
                        pattern2 = rf'\*\*{re.escape(countries_part)}\*\*'
                        
                        if re.search(pattern1, response_text, re.IGNORECASE):
                            # Reemplazar truncado con nombre completo
                            response_text = re.sub(pattern1, f'**{package_name}**', response_text, flags=re.IGNORECASE)
                            logger.info("Fixed truncated package name",
                                      from_pattern=f"{country} y -",
                                      to_name=package_name)
                            break
                        elif re.search(pattern2, response_text, re.IGNORECASE) and " - " in package_name:
                            # Reemplazar incompleto con nombre completo
                            response_text = re.sub(pattern2, f'**{package_name}**', response_text, flags=re.IGNORECASE)
                            logger.info("Fixed incomplete package name",
                                      from_pattern=countries_part,
                                      to_name=package_name)
                            break
            
            # Actualizar la respuesta con el nombre corregido
            result["response"] = response_text
        
        # Convertir resultado a formato de respuesta (schema flexible)
        geography_analysis = result.get("geography_analysis", {})

        # SessionInfo ya viene en formato correcto desde agent_service
        session_info_data = result.get("session_info", {})
        session_info = SessionInfo(**session_info_data) if session_info_data else None

        # Tarjetas visuales (Fase 2): derivadas determinísticamente de las habitaciones
        # que la tool consultar_disponibilidad ofreció en este turno.
        cards = _build_room_cards(result.get("rooms_offered", []))

        # Si en el turno se calculó una promo aplicable, esa tarjeta (con precio tachado)
        # tiene prioridad: es la respuesta directa a la señal del cliente.
        promo_offer = result.get("promo_offer")
        menu_card = result.get("menu_card")
        table_card = result.get("table_card")
        room_photos_card = result.get("room_photos_card")
        if room_photos_card:
            # Post-venta: el huésped pidió ver las fotos de la habitación que reservó.
            cards = [room_photos_card]
        elif promo_offer:
            cards = [_build_promo_card(promo_offer)]

        # Si se mostró la carta del restaurante, agregamos su card con el botón al carrito.
        elif menu_card:
            cards = [menu_card]

        # Selector de reserva de mesa (Fase 2): día + turno + personas.
        elif table_card:
            cards = [table_card]

        # Si el agente está pidiendo fechas y no mostró habitaciones, ofrecemos el selector.
        # Nunca en post-venta/casual (el huésped con reserva no busca disponibilidad).
        elif _should_offer_datepicker(result.get("response", ""),
                                    result.get("tools_used", []),
                                    has_room_cards=bool(cards),
                                    context_type=result.get("context_type", ""),
                                    dates_given=_dates_already_given(
                                        chat_request.message,
                                        agent_service.conversation_history.get(chat_request.session_id, []),
                                    )):
            cards = [_date_picker_card(_suggested_month(chat_request.message))]

        # Fallback determinístico: el usuario quiere reservar mesa pero el LLM no llamó la tool.
        elif _should_offer_table(chat_request.message,
                                 result.get("tools_used", []),
                                 has_other_cards=bool(cards),
                                 context_type=result.get("context_type", "")):
            cards = [_build_table_card_fallback(db, chat_request.session_id)]

        # Fallback determinístico: el huésped pidió la carta pero el LLM no llamó la tool.
        # Igual le mostramos la carta interactiva (que nunca quede sin carta).
        elif _should_offer_menu(chat_request.message,
                                result.get("tools_used", []),
                                has_other_cards=bool(cards),
                                context_type=result.get("context_type", ""),
                                db=db):
            fallback = _build_menu_card_fallback(db, chat_request.session_id, chat_request.message)
            if fallback:
                cards = [fallback]

        processing_time = time.time() - start_time

        response = ChatResponse(
            response=result["response"],
            has_context=result.get("has_context", False),
            geography_analysis=geography_analysis,  # Ahora es Dict
            sources_used=result.get("sources_used"),
            session_info=session_info,
            processing_time=f"{processing_time:.2f}s",
            error=result.get("error", False),
            error_type=result.get("error_type"),
            cards=cards,
        )
        
        logger.info("Chat message processed successfully",
                   session_id=chat_request.session_id,
                   has_context=result.get("has_context", False),
                   processing_time=f"{processing_time:.2f}s")

        # AUDITORÍA: 1 línea JSON por turno con la traza completa (mensaje → ruteo →
        # tools+args+resultados → respuesta → cards). Para detectar errores de lógica
        # revisando las charlas turno a turno. Nunca interrumpe la respuesta.
        try:
            from app.core.audit_log import log_turn
            log_turn({
                "session_id": chat_request.session_id,
                "language": chat_request.language,
                "user_message": chat_request.message,
                "route": result.get("context_type") or result.get("intent"),
                "response": result.get("response", ""),
                "tools": result.get("tool_trace", []),
                "tools_used": result.get("tools_used", []),
                "cards": [{"type": c.get("type"), "title": c.get("title")} for c in (cards or [])],
                "has_context": result.get("has_context", False),
                "document_sources": [s.get("document") for s in result.get("document_sources", []) or []],
                "lead_analysis": result.get("lead_analysis"),
                "error": result.get("error", False),
                "error_type": result.get("error_type"),
                "tokens": (result.get("usage") or {}).get("total_tokens"),
                "model": (result.get("usage") or {}).get("model"),
                "processing_time_s": round(processing_time, 2),
            })
        except Exception:
            pass  # auditar nunca debe afectar la respuesta
        
        # Trackear conversación para métricas - SIEMPRE, no solo cuando hay destinos
        try:
            # Extraer destino principal del análisis geográfico
            destination = None
            if geography_analysis:
                countries = geography_analysis.get("countries", [])
                if countries:
                    destination = countries[0]  # Primer país mencionado
            
            # Extraer documentos de las fuentes
            documents = []
            document_sources = result.get("document_sources", [])
            
            if document_sources:
                for source in document_sources:
                    doc_name = source.get("document", "")
                    if doc_name and doc_name not in documents:
                        documents.append(doc_name)
            
            # Extraer paquetes (simplificado - del nombre del documento)
            packages = []
            for doc in documents:
                # Extraer nombre del paquete del nombre del archivo
                # Ej: "Europa Clásica.pdf" -> "Europa Clásica"
                package_name = doc.replace(".pdf", "").replace(".PDF", "")
                if package_name and package_name not in packages:
                    packages.append(package_name)
            
            # ✅ TRACKEAR SIEMPRE - incluso sin destinos o documentos
            metrics_service.track_conversation(
                db,
                session_id=chat_request.session_id,
                is_user_message=True,
                response_time=processing_time,
                destination=destination,
                documents=documents if documents else None,
                packages=packages if packages else None
            )
            
            logger.info("Conversation tracked",
                       session_id=chat_request.session_id,
                       destination=destination,
                       documents_count=len(documents),
                       packages_count=len(packages))
        except Exception as tracking_error:
            logger.warning("Error tracking conversation metrics", error=str(tracking_error))
        
        return response
    
    except Exception as e:
        processing_time = time.time() - start_time
        
        # Log con traceback completo para debugging
        import traceback
        logger.error("Error processing chat message",
                    session_id=chat_request.session_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                    processing_time=f"{processing_time:.2f}s")
        
        # Respuesta de error estructurada
        return ChatResponse(
            response="Lo siento, ocurrió un error procesando tu mensaje. Por favor, intenta nuevamente.",
            has_context=False,
            geography_analysis={},  # Dict vacío en lugar de GeographyAnalysis()
            error=True,
            error_type=type(e).__name__,
            processing_time=f"{processing_time:.2f}s"
        )

@router.post("/clear/{session_id}", response_model=ClearHistoryResponse)
async def clear_conversation(session_id: str):
    """Limpia historial de conversación"""
    try:
        logger.info("Clearing conversation history", session_id=session_id)
        
        # Validar session_id
        if not session_id or len(session_id) < 8:
            raise HTTPException(
                status_code=400,
                detail="Session ID inválido"
            )
        
        result = agent_service.clear_history(session_id)
        
        if result.get("success", False):
            logger.info("Conversation cleared successfully",
                       session_id=session_id,
                       messages_cleared=result.get("messages_cleared", 0))
            
            return ClearHistoryResponse(
                success=True,
                messages_cleared=result.get("messages_cleared", 0),
                message=result.get("message", "Historial limpiado exitosamente"),
                session_id=session_id
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Error limpiando historial")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing conversation",
                    session_id=session_id,
                    error=str(e))
        
        return ClearHistoryResponse(
            success=False,
            messages_cleared=0,
            message=f"Error limpiando historial: {str(e)}",
            session_id=session_id
        )

@router.get("/greeting", response_model=GreetingResponse)
async def get_greeting(lang: str = "es"):
    """Obtiene mensaje de saludo del agente, en el idioma pedido (?lang=es|en|pt|fr)."""
    try:
        logger.debug("Getting agent greeting", lang=lang)

        lang = (lang or "es").lower()
        greeting = _GREETINGS.get(lang) if lang != "es" else None
        if not greeting:
            greeting = profile_manager.get_greeting()

        return GreetingResponse(
            greeting=greeting,
            agent_name=profile_manager.get_agent_name(),
            capabilities=profile_manager.get_capabilities(),
            conversation_starters=profile_manager.get_conversation_starters()
        )
    
    except Exception as e:
        logger.error("Error getting greeting", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo saludo: {str(e)}"
        )

@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """Obtiene información de una sesión específica"""
    try:
        logger.debug("Getting session info", session_id=session_id)
        
        if not session_id or len(session_id) < 8:
            raise HTTPException(
                status_code=400,
                detail="Session ID inválido"
            )
        
        session_info = agent_service.get_session_info(session_id)
        
        return session_info
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting session info",
                    session_id=session_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo información de sesión: {str(e)}"
        )

@router.get("/stats", response_model=AgentStatsResponse)
async def get_agent_stats():
    """Obtiene estadísticas del agente"""
    try:
        logger.debug("Getting agent stats")
        
        stats = agent_service.get_service_stats()
        
        return AgentStatsResponse(
            active_sessions=stats.get("active_sessions", 0),
            total_messages=stats.get("total_messages", 0),
            agent_profile=stats.get("agent_profile", {}),
            openai_config=stats.get("model_config", {}),
            uptime=_format_uptime(time.monotonic() - _SERVICE_START)
        )
    
    except Exception as e:
        logger.error("Error getting agent stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )

@router.get("/destinations", response_model=DestinationsResponse)
async def get_available_destinations():
    """Obtiene destinos disponibles en el sistema"""
    try:
        logger.debug("Getting available destinations")
        
        destinations = await rag_service.get_available_destinations()
        
        if "error" in destinations:
            raise HTTPException(
                status_code=500,
                detail=destinations["error"]
            )
        
        return DestinationsResponse(**destinations)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting destinations", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo destinos: {str(e)}"
        )

@router.get("/health")
async def get_chat_health():
    """Verifica el estado de salud del sistema de chat"""
    try:
        # Verificar RAG service
        rag_health = rag_service.get_service_health()
        
        # Verificar agent service stats
        agent_stats = agent_service.get_service_stats()
        
        # Verificar profile manager
        try:
            profile_info = profile_manager.get_profile_info()
            profile_healthy = True
        except Exception:
            profile_healthy = False
        
        overall_status = "healthy"
        if rag_health.get("status") != "healthy":
            overall_status = "degraded"
        if not profile_healthy:
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "rag_service": rag_health,
            "agent_service": {
                "active_sessions": agent_stats.get("active_sessions", 0),
                "circuit_breaker": agent_stats.get("openai_circuit_breaker", {})
            },
            "profile_manager": {
                "healthy": profile_healthy,
                "current_profile": profile_info.get("profile_name") if profile_healthy else None
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("Error checking chat health", error=str(e))
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
