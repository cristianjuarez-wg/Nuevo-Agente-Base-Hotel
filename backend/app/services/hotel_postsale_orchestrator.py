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

MAX_TURNS = 5
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
    def __init__(self, service, booking, ticket, message: str, history: List[Dict]):
        self.service = service          # HotelPostSaleService
        self.booking = booking          # Booking validado
        self.ticket = ticket            # HotelTicket de sesión
        self.message = message
        self.history = history
        self.escalation_analysis = None  # lo escribe analizar_escalacion
        self.service_requested = False   # lo marca solicitar_servicio (no re-tocar el ticket)
        self.room_photos_card = None     # lo setea ver_fotos_habitacion (card para el chat)
        self.menu_card = None            # lo setea ver_carta/armar_pedido_carta
        self.table_card = None           # lo setea reservar_mesa

    def restaurant_tool_ctx(self) -> Dict:
        """ctx dict para reusar los handlers de restaurante de hotel_tools (execute_tool).
        Lleva la sesión y el contacto de la reserva para que el huésped no pierda su contexto."""
        return {
            "db": self.service.db,
            "session_id": getattr(self.booking, "session_id", None),
            "contact_id": getattr(self.booking, "contact_id", None),
        }

    def absorb_restaurant(self, tool_ctx: Dict):
        """Recupera las cards que los handlers de restaurante dejaron en el tool_ctx."""
        if tool_ctx.get("menu_card"):
            self.menu_card = tool_ctx["menu_card"]
        if tool_ctx.get("table_card"):
            self.table_card = tool_ctx["table_card"]

    def knowledge_tool_ctx(self) -> Dict:
        """ctx dict mínimo para reusar los handlers de conocimiento de hotel_tools
        (info_pago, comercios_amigos, promos_vigentes, excursiones): solo necesitan `db`."""
        return {"db": self.service.db}


# ---------------------------------------------------------------------------
# TOOL — análisis de severidad/escalación
# ---------------------------------------------------------------------------
@function_tool
async def analizar_escalacion(
    ctx: RunContextWrapper[HotelPostventaContext], consulta: str
) -> str:
    """Analiza la consulta del huésped sobre su reserva y determina si podés resolverla
    vos (informativa: horarios, servicios, qué incluye) o si requiere escalar a un asesor
    humano (cambios de fecha, cancelaciones, reembolsos, reclamos, problemas de cobro).
    OBLIGATORIO llamarla UNA vez antes de tu respuesta final. Respetá su veredicto."""
    context = ctx.context
    analysis = await context.service.analyze_escalation(consulta, context.booking)
    context.escalation_analysis = analysis

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
async def consultar_info_hotel(
    ctx: RunContextWrapper[HotelPostventaContext], query: str
) -> str:
    """Consulta la base de conocimiento del hotel para responder dudas INFORMATIVAS del
    huésped durante su estadía: política de cancelación y cambios, horarios de
    check-in/check-out, servicios incluidos, amenities, desayuno, estacionamiento,
    mascotas, accesibilidad, cómo llegar. Úsala cuando el huésped PIDE información sobre
    una política o servicio (aunque sea sobre cancelación o cambios), para informarle la
    condición antes de ofrecer pasar a un asesor. NO inventes: respondé solo con lo que
    devuelva esta herramienta."""
    try:
        from app.core.rag.rag_service import rag_service
        context_text = await rag_service.retrieve_context(query)
        if not context_text or context_text.strip() == "NO_CONTEXT_FOUND":
            return ("No encontré ese detalle en la información del hotel. Para ese caso "
                    "puntual, lo mejor es coordinar con un asesor del hotel.")
        return context_text
    except Exception as e:  # noqa: BLE001
        logger.error("consultar_info_hotel (post-venta) falló", error=str(e))
        return ("No pude acceder a la información en este momento. Un asesor del hotel "
                "puede ayudarte con ese detalle.")


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
    etc. NO la uses para dudas informativas (eso es consultar_info_hotel) ni para
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
            "horario exacto."
        )
    except Exception as e:  # noqa: BLE001
        logger.error("solicitar_servicio (post-venta) falló", error=str(e))
        return ("No pude registrar el pedido automáticamente. Pedile disculpas al huésped y "
                "ofrecele contactar a recepción al +54 294-474-6200.")


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
    """Guarda en el perfil del huésped una ALERGIA/intolerancia o preferencia dietética que
    menciona DESPUÉS de reservar (ej. "soy alérgico al maní", "soy celíaco", "soy vegetariano").
    Úsala apenas la mencione: NO te limites a decir "lo tendré en cuenta". Las ALERGIAS son
    seguridad alimentaria: quedan en su perfil y se avisa al equipo del hotel.

    Args:
        preferencias: lista de lo que dijo (ej. ["maní"] o ["vegetariano"]).
        tipo: "alergia" si es alergia/intolerancia, "dieta" si es preferencia dietética.
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
        nuevas_alergias, nuevas_dietas = persist_preferences(db, contact, nuevas, tipo or None)
    except Exception as e:  # noqa: BLE001
        logger.error("registrar_preferencia (post-venta) falló", error=str(e))
        return ("No pude guardarlo automáticamente. Avisá al equipo del hotel para que lo "
                "registre, por las dudas.")

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
    if nuevas_dietas:
        partes.append(f"Guardé tus preferencias ({', '.join(nuevas_dietas)}) en tu perfil.")
    return (" ".join(partes) or "Listo, lo guardé en tu perfil.") + \
        " Confirmáselo al huésped con calidez y tranquilidad."


# ── Restaurante en POST-VENTA (capa compartida con pre-venta) ───────────────────
# El huésped que YA reservó puede gestionar el restaurante sin perder el contexto de su
# reserva (fechas, contacto). Reusan los mismos handlers de hotel_tools vía execute_tool.
@function_tool
async def ver_carta(ctx: RunContextWrapper[HotelPostventaContext], categoria: str = "") -> str:
    """Muestra la carta del restaurante PLAZA como tarjeta interactiva. Úsala cuando el huésped
    pida ver el menú/carta o qué hay para comer/tomar."""
    from app.services.hotel_tools import execute_tool
    tc = ctx.context.restaurant_tool_ctx()
    result = await execute_tool("ver_carta", {"categoria": categoria}, tc)
    ctx.context.absorb_restaurant(tc)
    return result.get("tool_result", "")


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
    from app.services.hotel_tools import execute_tool
    tc = ctx.context.restaurant_tool_ctx()
    # Asociar a su reserva por defecto.
    codigo = getattr(ctx.context.booking, "code", "") or ""
    result = await execute_tool("reservar_mesa", {
        "fecha": fecha, "turno": turno, "personas": personas,
        "nombre": nombre, "codigo_reserva": codigo, "notas": notas,
    }, tc)
    ctx.context.absorb_restaurant(tc)
    return result.get("tool_result", "")


@function_tool
async def armar_pedido_carta(ctx: RunContextWrapper[HotelPostventaContext], items_texto: str = "") -> str:
    """El huésped dijo qué quiere comer/pedir por texto. Devuelve la carta con esos platos
    precargados para que confirme el pedido."""
    from app.services.hotel_tools import execute_tool
    tc = ctx.context.restaurant_tool_ctx()
    result = await execute_tool("armar_pedido_carta", {"items_texto": items_texto}, tc)
    ctx.context.absorb_restaurant(tc)
    return result.get("tool_result", "")


# ── Conocimiento determinístico en POST-VENTA (capa compartida con pre-venta) ───
# El huésped alojado también pregunta cómo pagar el saldo, dónde comer con beneficio,
# qué promos hay o qué excursiones hacer. Reusan los handlers de hotel_tools (datos
# EXACTOS de la DB) en vez del RAG difuso.
@function_tool
async def consultar_pago(ctx: RunContextWrapper[HotelPostventaContext], consulta: str = "") -> str:
    """Devuelve los datos EXACTOS de pago/transferencia (CBU, alias, titular, medios de pago)
    cargados por el hotel. Úsala cuando el huésped pregunte cómo pagar el saldo, pida el CBU,
    el alias, los datos bancarios o una cuenta en otra moneda. Pasale `consulta` con lo que
    pidió. NUNCA inventes ni modifiques un dato bancario."""
    from app.services.hotel_tools import execute_tool
    result = await execute_tool("info_pago", {"consulta": consulta}, ctx.context.knowledge_tool_ctx())
    return result.get("tool_result", "")


@function_tool
async def comercios_amigos(ctx: RunContextWrapper[HotelPostventaContext], rubro: str = "") -> str:
    """Devuelve los comercios amigos del hotel (gastronomía con acuerdo) y sus beneficios para
    huéspedes. Úsala cuando el huésped pida dónde comer con descuento, heladerías, chocolaterías
    o restaurantes cerca. `rubro` (opcional): tipo de comercio."""
    from app.services.hotel_tools import execute_tool
    result = await execute_tool("comercios_amigos", {"rubro": rubro}, ctx.context.knowledge_tool_ctx())
    return result.get("tool_result", "")


@function_tool
async def promociones_vigentes(ctx: RunContextWrapper[HotelPostventaContext]) -> str:
    """Devuelve las promociones activas del hotel con sus condiciones EXACTAS. Úsala cuando el
    huésped pregunte qué promociones o descuentos hay. Si no hay ninguna activa, decilo; no
    inventes promos."""
    from app.services.hotel_tools import execute_tool
    result = await execute_tool("promos_vigentes", {}, ctx.context.knowledge_tool_ctx())
    return result.get("tool_result", "")


@function_tool
async def excursiones_y_atracciones(ctx: RunContextWrapper[HotelPostventaContext], categoria: str = "") -> str:
    """Devuelve las excursiones y atracciones de la zona cargadas por el hotel, con descripción
    y ubicación. Úsala cuando el huésped pregunte qué hacer, qué visitar o qué paseos/excursiones
    hay cerca. `categoria` (opcional): tipo de lugar. No la confundas con `comercios_amigos`
    (dónde comer) ni con dudas de la reserva."""
    from app.services.hotel_tools import execute_tool
    result = await execute_tool("excursiones_y_atracciones", {"categoria": categoria}, ctx.context.knowledge_tool_ctx())
    return result.get("tool_result", "")


_TOOLS = [analizar_escalacion, consultar_info_hotel, solicitar_servicio,
          ver_fotos_habitacion, registrar_preferencia,
          ver_carta, reservar_mesa, armar_pedido_carta,
          consultar_pago, comercios_amigos, promociones_vigentes, excursiones_y_atracciones]

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
        self._model_name = settings.OPENAI_MODEL
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )
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
        from app.domains.hotel.prompts.identity_blocks import build_postsale_identity_block
        profile = business_profile_service.get_profile(service.db)
        passenger_name = booking.guest_name or "el huésped"
        return POSTSALE_TOOL_SYSTEM.format(
            identity_block=build_postsale_identity_block(profile, passenger_name),
            passenger_name=passenger_name,  # el prompt lo usa además en la regla de no re-saludar
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
        # turns=5, hist=8, temp=0.7, 12 tools, guardrail). Este orquestador conserva su
        # try/except propio: el tripwire tiene respuesta específica y el fallo genérico
        # alimenta run_failed (que fuerza la ESCALACIÓN determinística del ticket).
        from app.core.agents.sdk_runtime import run_agent, build_input_list
        from app.domains.hotel.agent_specs import SPECS
        spec = SPECS["hotel_postsale"]

        instructions = self._build_instructions(service, booking, history, session_id)
        run_ctx = HotelPostventaContext(service, booking, ticket, message, history)
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
