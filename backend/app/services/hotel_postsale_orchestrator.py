"""
Orquestador de POST-VENTA del HOTEL sobre el OpenAI Agents SDK.

Clon reducido de postsale_sdk_orchestrator.py (Freeway). Mismo patrón:
  - Una tool `analizar_escalacion` (LLM analiza la severidad).
  - Acción determinística sobre el ticket tras el loop (escalar/resolver lo decide código).

Diferencias con Freeway: sin tools de vuelos ni proveedores (no aplican al hotel).
Firma pública `run(service, booking, ticket, message, session_id, history) -> Dict`.
"""
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents import (
    Agent,
    Runner,
    RunContextWrapper,
    function_tool,
    input_guardrail,
    GuardrailFunctionOutput,
    ModelSettings,
    OpenAIChatCompletionsModel,
    set_default_openai_client,
    set_tracing_disabled,
    set_tracing_export_api_key,
)

from app.config import settings
from app.core.profile.agent_profile import profile_manager
from app.core.observability.logging_config import get_logger
from app.core.llm.openai_client import get_async_openai
from app.core.llm.sdk_usage import extract_usage
from app.domains.hotel.prompts.postsale_tool_prompts import POSTSALE_TOOL_SYSTEM

logger = get_logger(__name__)

# La config real del loop vive en la AgentSpec (agent_specs.py:hotel_postsale). MAX_TURNS quedaba
# sin uso (eliminado); MAX_HISTORY_MESSAGES solo lo usan los _build_input_list locales.
MAX_HISTORY_MESSAGES = 8
# Minutos desde el último mensaje a partir de los cuales un saludo de apertura vuelve a tener
# sentido. Por debajo, el mensaje es "continuación inmediata" y NO hay que re-saludar.
GREETING_GAP_MINUTES = 30

_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# CONTEXTO POR TURNO
# ---------------------------------------------------------------------------
class HotelPostventaContext:
    def __init__(self, service, booking, ticket, message: str, history: List[Dict],
                 session_id: str = ""):
        self.service = service          # HotelPostSaleService
        self.booking = booking          # Booking validado
        self.ticket = ticket            # HotelTicket de sesión
        self.message = message
        self.history = history
        # Sesión EN CURSO (la de la conversación viva). Distinta de booking.session_id (la sesión
        # donde se CREÓ la reserva): si el huésped escribe desde otro canal, difieren. Las tools que
        # marcan la conversación (derivar_a_humano → needs_human) deben usar ESTA, no la del booking.
        self.session_id = session_id
        self.escalation_analysis = None  # lo escribe analizar_escalacion
        self.service_requested = False   # lo marca solicitar_servicio (no re-tocar el ticket)
        self.room_photos_card = None     # lo setea ver_fotos_habitacion (card para el chat)
        self.menu_card = None            # lo setea ver_carta/armar_pedido_carta
        self.table_card = None           # lo setea reservar_mesa
        # Fuentes RAG del turno (Fase 6): las escribe _handle_info_hotel cuando post-venta
        # adopta el handler seguro de conocimiento (antes el RAG inline no registraba sources).
        self.document_sources: List = []

    def restaurant_tool_ctx(self) -> Dict:
        """ctx dict para reusar los handlers de restaurante de hotel_tools (execute_tool).
        Lleva la sesión y el contacto de la reserva para que el huésped no pierda su contexto."""
        return {
            "db": self.service.db,
            # Sesión viva de la conversación (fallback a la del booking solo si no la tenemos):
            # así derivar_a_humano marca la charla EN CURSO, no la sesión donde se creó la reserva.
            "session_id": self.session_id or getattr(self.booking, "session_id", None),
            "contact_id": getattr(self.booking, "contact_id", None),
            # Código de la reserva (Fase 6): el folio-preset de la carta lo usa para precargar
            # el checkout del huésped in-house. Antes solo pre-venta lo pasaba; post resolvía el
            # folio solo por session_id (degradado). Paridad con pre-venta.
            "booking_code": getattr(self.booking, "code", None),
        }

    def absorb_restaurant(self, tool_ctx: Dict):
        """Recupera las cards que los handlers de restaurante dejaron en el tool_ctx."""
        if tool_ctx.get("menu_card"):
            self.menu_card = tool_ctx["menu_card"]
        if tool_ctx.get("table_card"):
            self.table_card = tool_ctx["table_card"]

    def knowledge_tool_ctx(self) -> Dict:
        """ctx dict para reusar los handlers de conocimiento de hotel_tools (info_pago,
        comercios_amigos, promos_vigentes, excursiones, info_hotel).

        Fase 6: se amplía con session_id/message/history/document_sources para que post-venta
        pueda adoptar el handler seguro `_handle_info_hotel` (RAG con sources + anti-injection),
        que lee `message`/`history` y escribe `document_sources`. Los handlers que solo usan `db`
        ignoran las keys extra."""
        return {
            "db": self.service.db,
            "session_id": self.session_id or getattr(self.booking, "session_id", None),
            "message": self.message,
            "history": self.history,
            "document_sources": self.document_sources,
        }

    def absorb_knowledge(self, tool_ctx: Dict):
        """Recupera las fuentes RAG que _handle_info_hotel dejó en el tool_ctx (Fase 6)."""
        if tool_ctx.get("document_sources"):
            self.document_sources = tool_ctx["document_sources"]

    # --- Contrato uniforme para las tools compartidas (Fase 6) -------------------
    # agent_tools.py declara cada tool UNA vez y obtiene el ctx por estos nombres. En
    # post-venta knowledge y restaurant tienen builders distintos (el de restaurante lleva
    # contact_id/booking_code; el de conocimiento no), así que los mapeamos explícitamente.
    def knowledge_ctx(self) -> Dict:
        return self.knowledge_tool_ctx()

    def restaurant_ctx(self) -> Dict:
        return self.restaurant_tool_ctx()


# ---------------------------------------------------------------------------
# TOOL — análisis de severidad/escalación
# ---------------------------------------------------------------------------
@function_tool
async def analizar_escalacion(
    ctx: RunContextWrapper[HotelPostventaContext], consulta: str
) -> str:
    """Analiza una CONSULTA del huésped sobre su reserva y determina si podés resolverla
    vos (informativa: horarios, servicios, qué incluye) o si requiere escalar a un asesor
    humano (cambios de fecha, cancelaciones, reembolsos, reclamos, problemas de cobro).
    OBLIGATORIO llamarla UNA vez antes de tu respuesta final A UNA CONSULTA. Respetá su veredicto.
    NO la uses cuando el huésped ya PIDIÓ expresamente hablar con una persona o INSISTE en ello:
    ese caso va DIRECTO por `derivar_a_humano` (que avisa a una persona y deja el pedido registrado),
    no por acá. Tampoco para un pedido de servicio (eso es `solicitar_servicio`)."""
    context = ctx.context
    analysis = await context.service.analyze_escalation(consulta, context.booking)
    context.escalation_analysis = analysis

    # ENCADENAMIENTO: si el huésped PIDE una persona, este carril no alcanza (escala el ticket
    # pero no avisa a la bandeja en vivo). El tool-result instruye llamar `derivar_a_humano`,
    # que es la tool que marca needs_human — el LLM sigue las instrucciones del tool-result.
    if analysis.get("wants_human"):
        motivo = analysis.get("escalation_reason") or "el huésped pide hablar con una persona"
        return (
            f"EL HUÉSPED PIDE UNA PERSONA. Llamá AHORA la tool `derivar_a_humano` con "
            f"motivo=\"{motivo}\" — es la tool que avisa a una persona del equipo y deja el "
            "pedido registrado en la bandeja. Después confirmale con calidez lo que devuelva."
        )

    if analysis.get("requires_escalation"):
        return (
            f"REQUIERE ESCALACIÓN a un asesor humano. "
            f"Urgencia: {analysis.get('urgency_level')}. "
            f"Motivo: {analysis.get('escalation_reason', 'requiere intervención humana')}. "
            "Informá al huésped con empatía que un asesor del hotel lo contactará a la "
            "brevedad, sin prometer plazos exactos."
        )
    return (
        f"PODÉS RESOLVERLA vos con la info de la reserva. "
        f"Categoría: {analysis.get('category', 'info')}. "
        "Respondé directo y cálido usando solo los datos reales de la reserva del contexto."
    )


@function_tool
async def info_hotel(
    ctx: RunContextWrapper[HotelPostventaContext], query: str
) -> str:
    """Consulta la base de conocimiento del hotel para responder dudas INFORMATIVAS del
    huésped durante su estadía: política de cancelación y cambios, horarios de
    check-in/check-out, servicios incluidos, amenities, desayuno, estacionamiento,
    mascotas, accesibilidad, cómo llegar. Úsala cuando el huésped PIDE información sobre
    una política o servicio (aunque sea sobre cancelación o cambios), para informarle la
    condición antes de ofrecer pasar a un asesor. NO inventes: respondé solo con lo que
    devuelva esta herramienta."""
    # Fase 6: se unifica al nombre y al HANDLER de pre-venta (_handle_info_hotel vía
    # execute_tool). Antes esta tool reimplementaba el RAG inline SIN wrap_untrusted_docs
    # (anti prompt-injection sobre docs que sube el cliente) ni document_sources — una
    # degradacion de seguridad. Ahora post-venta gana ambos. El docstring sigue siendo el
    # de post (contexto "durante la estadia"): el nombre se unifica, el texto es de rol.
    from app.services.hotel_tools import execute_tool
    tool_ctx = ctx.context.knowledge_ctx()
    result = await execute_tool("info_hotel", {"query": query}, tool_ctx)
    ctx.context.absorb_knowledge(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def solicitar_servicio(
    ctx: RunContextWrapper[HotelPostventaContext],
    pedido: str,
    tipo: str = "general",
    urgencia: str = "media",
) -> str:
    """Registra un PEDIDO DE SERVICIO del huésped alojado para que el equipo del hotel lo
    atienda (housekeeping, mantenimiento, recepción). Úsala cuando el huésped NECESITA una
    acción concreta durante su estadía: toallas/amenities, limpieza, algo que no funciona
    (aire, TV, WiFi, luz), una llave nueva, late checkout, room service, una almohada extra,
    etc. NO la uses para dudas informativas (eso es info_hotel) ni para
    cancelar/cambiar la reserva (eso escala).

    Args:
        pedido: descripción concreta de lo que necesita el huésped (en sus palabras).
        tipo: "housekeeping" (toallas/limpieza/amenities), "mantenimiento" (algo roto),
              "recepcion" (llave, late checkout, info), "room_service" o "general".
        urgencia: "baja" | "media" | "alta" (alta si afecta el confort ahora, ej. AC roto).
    """
    try:
        context = ctx.context
        # GATE in-house: los servicios FÍSICOS en la habitación (toallas, limpieza, algo roto,
        # room service) solo tienen sentido si el huésped está ALOJADO HOY. Si su reserva es
        # futura, no se registran como si estuviera en casa: se explican para la llegada.
        # Los pedidos ANOTABLES (recepción/general: cuna, late check-out, almohada extra) sí
        # se registran aunque la reserva sea futura.
        _IN_HOUSE_ONLY = {"housekeeping", "mantenimiento", "room_service"}
        booking = context.booking
        stay = booking.stay_status() if booking else None
        if (tipo or "").strip().lower() in _IN_HOUSE_ONLY and stay != "checked_in":
            ci = getattr(booking, "check_in", None)
            cuando = f" Tu estadía arranca el {ci.strftime('%d/%m')}." if ci and stay == "upcoming" else ""
            return (
                "NO registres este pedido como si el huésped estuviera alojado: su reserva NO "
                f"está en curso (estado: {stay}).{cuando} Explicale con calidez que ese servicio "
                "(toallas, limpieza, reparaciones, room service) es para cuando esté alojado, y "
                "ofrecele DEJAR ANOTADO el pedido para su llegada si quiere. NO prometas que se "
                "hace ahora."
            )
        status = context.service.register_service_request(
            ticket=context.ticket, pedido=pedido, tipo=tipo, urgencia=urgencia,
        )
        context.service_requested = True  # el ticket queda 'open' para el staff; no re-tocarlo
        return (
            f"PEDIDO REGISTRADO para el equipo del hotel (tipo: {tipo}, urgencia: {urgencia}). "
            "Confirmá al huésped con calidez que el equipo ya fue avisado y se ocupará a la "
            "brevedad. Si es algo urgente que afecta su confort (ej. aire/calefacción), "
            "mostrá empatía extra y ofrecé avisar a recepción de inmediato. No prometas un "
            "horario exacto. IMPORTANTE: si el huésped NO queda conforme con esta solución o "
            "pide hablar con una PERSONA, NO registres otro pedido: llamá `derivar_a_humano`."
        )
    except Exception as e:  # noqa: BLE001
        logger.error("solicitar_servicio (post-venta) falló", error=str(e))
        from app.services import business_profile_service
        c = business_profile_service.get_contact(ctx.context.service.db)
        tel = f" al {c['phone']}" if c.get("phone") else ""
        return ("No pude registrar el pedido automáticamente. Pedile disculpas al huésped y "
                f"ofrecele contactar a recepción{tel}.")


@function_tool
async def ver_fotos_habitacion(ctx: RunContextWrapper[HotelPostventaContext]) -> str:
    """Muestra al huésped las fotos de la habitación que YA reservó. Úsala cuando pida ver
    fotos/imágenes de su habitación. La interfaz las muestra como una tarjeta visual en el
    chat; vos solo confirmá con calidez. NO digas que no tenés acceso a imágenes."""
    context = ctx.context
    booking = context.booking
    room_type = getattr(booking, "room_type", None) or (
        booking.room.room_type if getattr(booking, "room", None) else None
    )
    try:
        from app.models.hotel import Room
        db = context.service.db
        room = db.query(Room).filter(Room.room_type == room_type).first() if room_type else None
        images = (room.images or []) if room else []
        if not images:
            return ("No tengo fotos cargadas de esa habitación ahora mismo. Podés verla en el "
                    "sitio del hotel; si querés te paso el dato de recepción para más imágenes.")
        context.room_photos_card = {
            "type": "room_photos",
            "title": f"Habitación {room_type}",
            "description": room.description or "",
            "images": images,
            "bed_config": room.bed_config,
            "view": room.view,
        }
        return ("Le mostré las fotos de su habitación en el chat (tarjeta con imágenes). "
                "Confirmá con calidez y ofrecé ayuda con cualquier otra cosa de su estadía.")
    except Exception as e:  # noqa: BLE001
        logger.error("ver_fotos_habitacion falló", error=str(e))
        return ("No pude cargar las fotos ahora. Ofrecele disculpas y sugerile ver la "
                "habitación en el sitio del hotel.")


@function_tool
async def registrar_preferencia(
    ctx: RunContextWrapper[HotelPostventaContext],
    preferencias: List[str],
    tipo: str = "",
) -> str:
    """Guarda en el perfil del huésped algo que menciona DESPUÉS de reservar: una ALERGIA/
    intolerancia o dieta ("soy alérgico al maní", "soy celíaco"), con quién viaja ("vengo con mi
    hijo"), un servicio que suele usar ("siempre uso el spa") o una observación para el hotel.
    Úsala apenas lo mencione: NO te limites a decir "lo tendré en cuenta". Las ALERGIAS son
    seguridad alimentaria: quedan en su perfil y se avisa al equipo del hotel.

    Args:
        preferencias: lista de lo que dijo (ej. ["maní"], ["vegetariano"], ["Tomás"], ["spa"]).
        tipo: "alergia" · "dieta" · "acompañante" (con quién viaja) · "servicio" (servicio que
              usa) · "nota" (observación libre). Vacío = se clasifica entre alergia y dieta.
    """
    context = ctx.context
    booking = context.booking
    db = context.service.db
    if isinstance(preferencias, str):
        preferencias = [preferencias]
    nuevas = [str(p).strip().lower() for p in (preferencias or []) if str(p).strip()]
    if not nuevas:
        return "¿Qué alergia o preferencia querés que registre?"

    # En post-venta el huésped se identifica por su reserva → Contact vía booking.contact_id.
    from app.models.contact import Contact
    contact = None
    if getattr(booking, "contact_id", None):
        contact = db.query(Contact).filter(Contact.id == booking.contact_id).first()
    if not contact:
        return ("Lo anoté para esta conversación, pero no pude vincularlo a tu perfil. "
                "El equipo del hotel lo tendrá en cuenta igual.")

    try:
        from app.services.hotel_tools import persist_preferences
        agregados = persist_preferences(db, contact, nuevas, tipo or None)
    except Exception as e:  # noqa: BLE001
        logger.error("registrar_preferencia (post-venta) falló", error=str(e))
        return ("No pude guardarlo automáticamente. Avisá al equipo del hotel para que lo "
                "registre, por las dudas.")

    nuevas_alergias = agregados.get("allergies") or []
    # Las alergias, además, se avisan al staff (seguridad alimentaria).
    if nuevas_alergias:
        try:
            context.service.register_service_request(
                ticket=context.ticket,
                pedido=f"Alergia/intolerancia declarada por el huésped: {', '.join(nuevas_alergias)}. "
                       "Tener en cuenta en restaurante/desayuno (seguridad alimentaria).",
                tipo="recepcion", urgencia="alta",
            )
            context.service_requested = True
        except Exception as e:  # noqa: BLE001
            logger.error("aviso de alergia al staff falló", error=str(e))

    partes = []
    if nuevas_alergias:
        partes.append(f"⚠️ Registré tu alergia/intolerancia ({', '.join(nuevas_alergias)}) en tu "
                      "perfil y avisé al equipo del hotel para que la tengan en cuenta en el "
                      "restaurante y el desayuno.")
    if agregados.get("dietary"):
        partes.append(f"Guardé tus preferencias ({', '.join(agregados['dietary'])}) en tu perfil.")
    if agregados.get("family"):
        partes.append(f"Anoté que viajás con {', '.join(agregados['family'])}.")
    if agregados.get("services_used"):
        partes.append(f"Guardé que solés usar: {', '.join(agregados['services_used'])}.")
    if agregados.get("notes"):
        partes.append("Anoté tu observación en el perfil.")
    return (" ".join(partes) or "Listo, lo guardé en tu perfil.") + \
        " Confirmáselo al huésped con calidez y tranquilidad."


# ── Restaurante en POST-VENTA (capa compartida con pre-venta) ───────────────────
# El huésped que YA reservó puede gestionar el restaurante sin perder el contexto de su
# reserva (fechas, contacto). Reusan los mismos handlers de hotel_tools vía execute_tool.
#
# ver_carta se declara UNA sola vez en hotel_tools_pkg.agent_tools (Fase 6) y se importa
# más abajo, junto al _TOOLS. armar_pedido_carta y reservar_mesa se dedup en sub-fases 4 y 7.
@function_tool
async def reservar_mesa(
    ctx: RunContextWrapper[HotelPostventaContext],
    fecha: str = "", turno: str = "", personas: int = 0, nombre: str = "",
    notas: str = "",
) -> str:
    """Reserva una MESA del restaurante para el huésped. El restaurante tiene turnos ALMUERZO
    y CENA; pasá turno="cena"/"almuerzo" (no "noche"). Si el huésped alude a SU estadía ("el
    primer día", "cuando llegue"), dejá `fecha` VACÍA: se usa el check-in de su reserva. El
    horario puntual lo elige en el selector. Si menciona una OCASIÓN o pedido especial
    (cumpleaños, aniversario, recibir con champán, una alergia para esa cena), pasalo en `notas`:
    queda guardado en la reserva y el equipo del salón lo tiene en cuenta."""
    # Cuerpo compartido con pre-venta (Fase 6). Post NO expone codigo_reserva al LLM: lo inyecta
    # desde booking.code para asociar la mesa a la reserva del huésped por defecto. La firma
    # diverge de pre (por eso wrappers por rol), el cuerpo no.
    from app.services.hotel_tools_pkg.agent_tools import reservar_mesa_body
    codigo = getattr(ctx.context.booking, "code", "") or ""
    return await reservar_mesa_body(ctx, fecha, turno, personas, nombre, codigo, notas)


# armar_pedido_carta se declara UNA sola vez en hotel_tools_pkg.agent_tools (Fase 6) y
# se importa más abajo, junto al _TOOLS.


# ── Conocimiento determinístico en POST-VENTA (capa compartida con pre-venta) ───
# El huésped alojado también pregunta cómo pagar el saldo, dónde comer con beneficio,
# qué promos hay o qué excursiones hacer. Reusan los handlers de hotel_tools (datos
# EXACTOS de la DB) en vez del RAG difuso.
#
# info_pago (antes consultar_pago), promos_vigentes (antes promociones_vigentes),
# comercios_amigos y excursiones_y_atracciones se declaran UNA sola vez en
# hotel_tools_pkg.agent_tools (Fase 6) y se importan más abajo, junto al _TOOLS.
# El rename unifica el nombre por rol: el huésped de post-venta ve las mismas tools que
# el de pre-venta (docstring canónico compartido), no una variante propia.


@function_tool
async def derivar_a_humano(ctx: RunContextWrapper[HotelPostventaContext], motivo: str = "") -> str:
    """Deriva la conversación a una PERSONA del equipo del hotel. Cuando el huésped PIDE
    expresamente hablar con alguien / que lo atienda una persona, o INSISTE en ello tras ofrecerle
    resolverlo, llamá ESTA tool DIRECTO — no `analizar_escalacion` (esa es solo para clasificar una
    consulta ambigua). Usala también cuando hay algo que genuinamente NO podés resolver ni con
    `solicitar_servicio` ni respondiendo vos. Es la ÚNICA tool que realmente avisa a una persona y
    deja el pedido registrado. El sistema decide, según haya atención humana disponible, si lo pasa
    en vivo o lo deja para seguimiento — vos solo llamás la tool con un `motivo` breve y confirmás
    con calidez lo que devuelva."""
    # Cuerpo compartido con pre-venta (Fase 6): el docstring diverge (post referencia
    # analizar_escalacion/solicitar_servicio, que pre no tiene) pero la lógica es idéntica.
    # Antes duplicada → causa raíz de los bugs reincidentes de derivación (falto la tool 2 veces).
    from app.services.hotel_tools_pkg.agent_tools import derivar_a_humano_body
    return await derivar_a_humano_body(ctx, motivo)


# Tools declaradas UNA vez y compartidas con pre-venta (Fase 6).
from app.services.hotel_tools_pkg.agent_tools import (  # noqa: E402
    comercios_amigos, excursiones_y_atracciones, info_pago, promos_vigentes, ver_carta,
    armar_pedido_carta,
)

_TOOLS = [analizar_escalacion, info_hotel, solicitar_servicio,
          ver_fotos_habitacion, registrar_preferencia,
          ver_carta, reservar_mesa, armar_pedido_carta,
          info_pago, comercios_amigos, promos_vigentes, excursiones_y_atracciones,
          derivar_a_humano]

# Fase 2.2: registro en el ToolRegistry con key "postsale.<nombre>".
from app.core.agents.tool_registry import register_tool  # noqa: E402
for _t in _TOOLS:
    register_tool(f"postsale.{_t.name}", _t)


# ---------------------------------------------------------------------------
# GUARDRAIL — input anti-jailbreak
# ---------------------------------------------------------------------------
_JAILBREAK_MARKERS = (
    "ignore previous", "ignora las instrucciones", "system prompt",
    "olvida tus instrucciones", "reveal your prompt", "actúa como",
)


@input_guardrail
async def relevancia_guardrail(
    ctx: RunContextWrapper[HotelPostventaContext], agent: Agent, user_input
) -> GuardrailFunctionOutput:
    text = user_input if isinstance(user_input, str) else str(user_input)
    is_jailbreak = any(m in text.lower() for m in _JAILBREAK_MARKERS)
    if is_jailbreak:
        logger.warning("Hotel post-venta input guardrail: possible jailbreak attempt",
                       preview=text.lower()[:80])
    return GuardrailFunctionOutput(
        output_info={"jailbreak_suspected": is_jailbreak},
        tripwire_triggered=is_jailbreak,
    )


# Fase 2.2: registro del guardrail — la spec lo referencia por key.
from app.core.agents.tool_registry import register_guardrail  # noqa: E402
register_guardrail("postsale.relevancia", relevancia_guardrail)


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class HotelPostSaleSDKOrchestrator:
    def __init__(self):
        # El modelo real lo construye el runtime desde la spec; guardamos solo el nombre para el
        # dict de usage del fallback. El objeto model construido acá era dead code.
        self._model_name = settings.OPENAI_MODEL
        if not settings.DEBUG:
            set_tracing_disabled(False)

    def _format_history(self, history: List[Dict]) -> str:
        if not history:
            return "No hay historial previo."
        recent = history[-MAX_HISTORY_MESSAGES:]
        lines = []
        for m in recent:
            role = "Usuario" if m.get("role") == "user" else "Asistente"
            lines.append(f"{role}: {m.get('content', '')[:300]}")
        return "\n".join(lines)

    def _continuity_signal(self, service, session_id: str, history: List[Dict]) -> str:
        """Señal para el prompt: ¿es continuación inmediata de la charla o retoma tras pausa?

        Decide por el tiempo desde el último mensaje (Conversation.last_message_at, UTC), que
        se actualiza DESPUÉS de responder → al entrar un mensaje nuevo refleja el intercambio
        anterior, justo el gap que necesitamos. Si no hay charla previa, es el INICIO.
        """
        # Sin historial en RAM → no hay charla previa: es el primer mensaje (saludo OK).
        if not history:
            return "INICIO de la conversación: podés abrir con un saludo breve y cálido."
        last_at = None
        try:
            from app.models.conversation import Conversation
            conv = (
                service.db.query(Conversation)
                .filter(Conversation.session_id == session_id)
                .first()
            )
            last_at = conv.last_message_at if conv else None
        except Exception as e:  # noqa: BLE001 — nunca romper la respuesta por esta señal
            logger.warning("No se pudo calcular la continuidad de la charla", error=str(e))
            return ""
        if last_at is None:
            return "INICIO de la conversación: podés abrir con un saludo breve y cálido."
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        gap_min = (datetime.now(timezone.utc) - last_at).total_seconds() / 60.0
        # Umbral configurable desde el flujo de post-venta del Centro (Fase A);
        # sin config → el default histórico (paridad).
        greeting_gap = GREETING_GAP_MINUTES
        try:
            from app.services import skill_service
            flow = skill_service.get_flow_values_for_session(service.db, session_id, "flujo_postventa")
            if flow and flow.get("gap_minutes"):
                greeting_gap = float(flow["gap_minutes"])
        except Exception:  # noqa: BLE001 — nunca romper la señal por config
            pass
        if gap_min < greeting_gap:
            return (
                f"CONTINUACIÓN INMEDIATA (el último mensaje fue hace ~{max(int(gap_min), 0)} min): "
                "ya venís conversando. NO vuelvas a saludar ni a re-confirmar la reserva; "
                "respondé directo a lo último que dijo el huésped."
            )
        if gap_min < 180:
            return (
                f"RETOMA tras una pausa (~{int(gap_min)} min): podés abrir con un saludo breve."
            )
        horas = int(gap_min // 60)
        return f"RETOMA tras una pausa (~{horas} h): podés abrir con un saludo breve."

    def _build_instructions(self, service, booking, history: List[Dict], session_id: str = "") -> str:
        booking_context = service.build_booking_context(booking)
        # Roster del equipo real (Fase 0.1): acompaña la regla anti-invención de personas.
        from app.domains.hotel.prompts.base_blocks import build_team_roster_block
        # Identidad del negocio (Fase 1): encabezado compuesto desde el perfil.
        from app.services import business_profile_service
        from app.domains.hotel.prompts.identity_blocks import (
            build_postsale_identity_block, build_facts_block,
        )
        profile = business_profile_service.get_profile(service.db)
        passenger_name = booking.guest_name or "el huésped"
        # Perfil 360 del huésped (Capa 2, Fase 1): antes el post-venta NO lo recibía. Nivel guest.
        from app.services import guest_context_service
        guest_context = guest_context_service.build_guest_context(
            "guest", getattr(booking, "contact_id", None), service.db)
        # Naturalidad opt-in por customer_facing (Fase 3): post-venta es customer_facing → lo recibe.
        from app.domains.hotel.prompts.generation_prompts import NATURALIDAD_BLOCK
        from app.domains.hotel.prompts.base_blocks import handoff_block, MULTI_INTENT_BLOCK
        from app.domains.hotel.agent_specs import SPECS
        from app.services import human_attention_service
        _cf = SPECS["hotel_postsale"].customer_facing
        _naturalidad = NATURALIDAD_BLOCK if _cf else ""
        _handoff = handoff_block(human_attention_service.is_human_available(service.db)) if _cf else ""
        _multi_intent = MULTI_INTENT_BLOCK if _cf else ""
        return POSTSALE_TOOL_SYSTEM.format(
            identity_block=build_postsale_identity_block(profile, passenger_name),
            facts_block=build_facts_block(profile),  # HECHOS del negocio (Fase 3.5 → post-venta)
            passenger_name=passenger_name,  # el prompt lo usa además en la regla de no re-saludar
            guest_context=guest_context,
            naturalidad_block=_naturalidad,
            handoff_block=_handoff,
            multi_intent_block=_multi_intent,
            package_context=booking_context,
            chat_history=self._format_history(history),
            continuidad=self._continuity_signal(service, session_id, history),
            team_block=build_team_roster_block(service.db),
        )

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(
        self, service, booking, ticket, message: str, session_id: str, history: List[Dict]
    ) -> Dict:
        start = time.time()

        # Fase 2.2: el loop del SDK corre por el runtime declarativo (spec hotel_postsale:
        # turns=5, hist=8, temp=0.7, 13 tools, guardrail). Este orquestador conserva su
        # try/except propio: el tripwire tiene respuesta específica y el fallo genérico
        # alimenta run_failed (que fuerza la ESCALACIÓN determinística del ticket).
        from app.core.agents.sdk_runtime import run_agent, build_input_list
        from app.domains.hotel.agent_specs import SPECS
        spec = SPECS["hotel_postsale"]

        instructions = self._build_instructions(service, booking, history, session_id)
        run_ctx = HotelPostventaContext(service, booking, ticket, message, history,
                                        session_id=session_id)
        input_list = build_input_list(history, message, spec.max_history)

        from agents import InputGuardrailTripwireTriggered

        run_failed = False
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": self._model_name}
        try:
            out = await run_agent(
                spec, instructions=instructions, context=run_ctx, input_list=input_list,
                display_name=profile_manager.get_agent_name(),
            )
            usage = out["usage"]
            response_text = out["response"]
            tools_used = out["tools_used"]
            from app.core.observability.audit_log import build_tool_trace
            tool_trace = build_tool_trace(out["result"])
        except InputGuardrailTripwireTriggered:
            logger.warning("Hotel post-venta: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte con tu reserva en el Hampton Bariloche. "
                "¿En qué puedo asistirte con tu estadía? 😊"
            )
            tools_used = []
            tool_trace = []
        except Exception as e:
            logger.error("Hotel post-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un inconveniente procesando tu consulta. "
                "Un asesor del hotel va a revisar tu caso a la brevedad."
            )
            tools_used = []
            tool_trace = []
            run_failed = True

        if not response_text:
            response_text = "Disculpá, no pude procesar tu consulta. ¿Podés reformularla?"

        # ACCIÓN DETERMINÍSTICA SOBRE EL TICKET — la decide el código, no el LLM.
        # Si se registró un pedido de servicio, el ticket ya quedó 'open' para el staff:
        # no lo re-tocamos. Si no, aplicamos resolver/escalar según el análisis.
        analysis = run_ctx.escalation_analysis
        requires_escalation = False  # default: un pedido de servicio no escala (queda 'open').
        if run_ctx.service_requested:
            status = ticket.status  # 'open' (pedido de servicio para el staff)
        else:
            requires_escalation = (
                run_failed or bool(analysis and analysis.get("requires_escalation"))
            )
            status = service.apply_ticket_action(
                ticket, requires_escalation, response_text, message, analysis
            )

        # BACKSTOP DETERMINÍSTICO DE DERIVACIÓN A BANDEJA: si el análisis detectó que el huésped
        # PIDE una persona (wants_human) pero el LLM NO llamó `derivar_a_humano` este turno, el
        # pedido no habría dejado rastro en la bandeja (needs_human). Lo marcamos por código —igual
        # que requires_escalation respalda el ticket— para que el carril bandeja no dependa 100%
        # de que el LLM obedezca la instrucción del tool-result.
        if analysis and analysis.get("wants_human") and "derivar_a_humano" not in (tools_used or []):
            try:
                from app.services import conversation_control_service as _ctrl
                from app.services import human_attention_service as _has
                from app.services.summary_service import summarize_session as _summarize
                _sid = run_ctx.session_id or getattr(booking, "session_id", None)
                if _sid:
                    _status = "live" if _has.is_human_available(service.db) else "deferred"
                    try:
                        _resumen = _summarize(_sid, service.db)
                    except Exception:  # noqa: BLE001
                        _resumen = ""
                    _ctrl.flag_needs_human(
                        service.db, _sid,
                        motivo=(analysis.get("escalation_reason") or "el huésped pide hablar con una persona"),
                        summary=_resumen, status=_status,
                    )
                    logger.info("Backstop needs_human aplicado (LLM no llamó derivar_a_humano)",
                                session_id=_sid, status=_status)
            except Exception as e:  # noqa: BLE001
                logger.warning("No se pudo aplicar el backstop de needs_human",
                               session_id=run_ctx.session_id, error=str(e))

        duration = time.time() - start
        logger.info("Hotel post-venta SDK turn completed",
                    session_id=session_id, tools_used=tools_used,
                    status=status, duration=f"{duration:.2f}s")

        return {
            "response": response_text,
            "agent_key": spec.key,  # observabilidad (3.4)
            "has_context": True,
            "context_type": "postsale",
            "ticket_created": True,
            "ticket_number": ticket.ticket_number,
            "priority": ticket.priority,
            "status": status,
            "can_auto_resolve": not requires_escalation,
            "tools_used": tools_used,
            "tool_trace": tool_trace,
            "room_photos_card": run_ctx.room_photos_card,
            "menu_card": run_ctx.menu_card,
            "table_card": run_ctx.table_card,
            "processing_time": f"{duration:.2f}s",
            "usage": usage,
        }


# Instancia global
hotel_postsale_sdk_orchestrator = HotelPostSaleSDKOrchestrator()
