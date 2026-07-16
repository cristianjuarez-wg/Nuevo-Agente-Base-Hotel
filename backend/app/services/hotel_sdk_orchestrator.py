"""
Orquestador de PRE-VENTA del HOTEL sobre el OpenAI Agents SDK.

Clon adaptado de agent_sdk_orchestrator.py (Freeway). Mismo contrato público
`run(db, message, session_id, history) -> Dict`. Cambios respecto a Freeway:
  - Tools de HOTEL (info_hotel, consultar_disponibilidad, crear_reserva, consultar_reserva)
    vía hotel_tools.execute_tool.
  - Sin obtener_clima ni guardrail de países disponibles (eran de turismo).
  - Prompt de concierge hotelero (HOTEL_AGENT_SYSTEM).

Conserva del original: análisis de lead transversal, input guardrail anti-jailbreak,
catch genérico anti-500, extracción de tools_used, max_turns.
"""
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

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
from app.utils.timezone_utils import now_business
from app.core.profile.agent_profile import profile_manager
from app.core.observability.logging_config import get_logger
from app.core.llm.openai_client import get_async_openai
from app.core.llm.sdk_usage import extract_usage
from app.services.lead_service import lead_service
from app.services.lead_analyzer import lead_analyzer
from app.core.rag.rag_service import rag_service
from app.services.hotel_tools import execute_tool
from app.domains.hotel.prompts.tool_agent_prompts import (
    TOOL_AGENT_SYSTEM, DEFAULT_TONO_BLOCK, DEFAULT_POLITICA_BLOCK,
)
from app.domains.hotel.prompts.flow_blocks import flow_block_for
from app.domains.hotel.prompts.generation_prompts import NATURALIDAD_BLOCK
from app.domains.hotel.prompts.base_blocks import handoff_block as _handoff_block
from app.domains.hotel.prompts.base_blocks import MULTI_INTENT_BLOCK
from app.domains.hotel.prompts.context_blocks import (
    build_lead_context_block,
    build_contact_request_block,
    build_booking_nudge_block,
    build_price_objection_capture_block,
    build_whatsapp_contact_block,
    build_language_block,
)

# Flag (en Conversation.extra_metadata) que marca que en esta sesión la tool de disponibilidad
# ya devolvió habitaciones reales. Si está, el huésped ya vio opciones → toca cerrar la venta
# (ofrecer reservar), no captar lead pasivo. Se setea al final del turno donde hubo rooms_offered.
_AVAILABILITY_SHOWN_FLAG = "availability_shown"

logger = get_logger(__name__)

# NOTA: la config REAL del loop (turns, history, temperatura, tools) vive en la AgentSpec
# (agent_specs.py:hotel_presale). MAX_HISTORY_MESSAGES solo lo usa el `_build_input_list` local
# (que el runtime NO usa — ver `run`). MAX_TURNS quedaba sin ningún uso: eliminado para que no
# aparente ser la config viva.
MAX_HISTORY_MESSAGES = 20

# Cliente OpenAI compartido por el SDK (singleton del proyecto).
_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# CONTEXTO POR TURNO
# ---------------------------------------------------------------------------
class HotelContext:
    """Contexto mutable de un turno de pre-venta del hotel.

    Lleva db/message/history para las tools y recoge document_sources (RAG) que el
    orquestador necesita para armar la respuesta final.
    """

    def __init__(self, db: Session, message: str, history: List[Dict], session_id: str = "",
                 contact_id: Optional[int] = None):
        self.db = db
        self.message = message
        self.history = history
        self.session_id = session_id
        # Contacto resuelto del huésped (Fase 6): antes solo post-venta lo pasaba al ctx. Con
        # esto las tools de restaurante (_resolve_contact) lo reciben directo también en pre-venta;
        # si es None, _resolve_contact cae al fallback por teléfono del wa_ (comportamiento previo).
        self.contact_id = contact_id
        self.document_sources: List = []
        # Habitaciones consultadas en este turno (para renderizar tarjetas en el chat).
        self.rooms_offered: List[Dict] = []
        # Oferta de promo calculada en este turno (card con precio tachado), si la hubo.
        self.promo_offer: Optional[Dict] = None
        # Card de la carta del restaurante (botón "Ver carta y pedir"), si se mostró.
        self.menu_card: Optional[Dict] = None
        self.table_card: Optional[Dict] = None
        # Código de reserva que el huésped ya validó en ESTA charla (consultar_reserva).
        # Se reusa para precargar el checkout del restaurante y no re-pedirlo.
        self.booking_code: Optional[str] = None

    def as_tool_ctx(self) -> Dict:
        return {
            "db": self.db,
            "message": self.message,
            "history": self.history,
            "session_id": self.session_id,
            "contact_id": self.contact_id,
            "document_sources": self.document_sources,
            "rooms_offered": self.rooms_offered,
            "promo_offer": self.promo_offer,
            "menu_card": self.menu_card,
            "table_card": self.table_card,
            "booking_code": self.booking_code,
        }

    # --- Contrato uniforme para las tools compartidas (Fase 6) -------------------
    # agent_tools.py declara cada tool UNA vez y obtiene el ctx por estos nombres, sin
    # saber de qué rol viene. En pre-venta el ctx es siempre el mismo (as_tool_ctx, que
    # ya lleva todo); knowledge/restaurant apuntan al mismo dict. absorb_knowledge y
    # absorb_restaurant son el mismo absorb() (pre recupera todos los campos de una).
    def knowledge_ctx(self) -> Dict:
        return self.as_tool_ctx()

    def restaurant_ctx(self) -> Dict:
        return self.as_tool_ctx()

    def absorb_knowledge(self, tool_ctx: Dict):
        self.absorb(tool_ctx)

    def absorb_restaurant(self, tool_ctx: Dict):
        self.absorb(tool_ctx)

    def absorb(self, tool_ctx: Dict):
        self.document_sources = tool_ctx.get("document_sources", self.document_sources)
        self.rooms_offered = tool_ctx.get("rooms_offered", self.rooms_offered)
        self.promo_offer = tool_ctx.get("promo_offer", self.promo_offer)
        self.menu_card = tool_ctx.get("menu_card", self.menu_card)
        self.table_card = tool_ctx.get("table_card", self.table_card)
        self.booking_code = tool_ctx.get("booking_code", self.booking_code)


# ---------------------------------------------------------------------------
# TOOLS — envuelven los handlers de hotel_tools.execute_tool
# ---------------------------------------------------------------------------
@function_tool
async def info_hotel(ctx: RunContextWrapper[HotelContext], query: str) -> str:
    """Consulta información del hotel: habitaciones, servicios, instalaciones, ubicación,
    políticas (check-in/out, mascotas, estacionamiento), promociones y amenities.
    Úsala SIEMPRE que el usuario pregunte sobre el hotel, sus comodidades o servicios.
    Es la única fuente de información oficial del hotel: no inventes datos."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("info_hotel", {"query": query}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def consultar_disponibilidad(
    ctx: RunContextWrapper[HotelContext],
    check_in: str,
    check_out: str,
    guests: int = 1,
    children: int = 0,
    infants: int = 0,
    room_types: List[str] = [],
) -> str:
    """Consulta qué tipos de habitación están disponibles para un rango de fechas y
    cantidad de huéspedes, con el precio total en USD y ARS. Úsala SIEMPRE que el usuario
    quiera reservar o pregunte por disponibilidad/precios para fechas concretas.
    Las fechas deben estar en formato YYYY-MM-DD.
    `guests` = adultos (18+). `children` = niños (3-17, cuentan para la capacidad).
    `infants` = bebés (0-2, van en cuna y NO cuentan para la capacidad de la habitación).
    `room_types`: los tipos de habitación que vas a RECOMENDAR en tu respuesta (ej.
    ["Twin", "Family Plan"]). El sistema muestra como TARJETAS interactivas SOLO esos tipos,
    para que coincidan con tu texto. Pasá 2-3 opciones, las que mejor encajen con el huésped.
    Si lo dejás vacío, se muestran TODAS las disponibles (evitá esto: elegí las que recomendás)."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "consultar_disponibilidad",
        {"check_in": check_in, "check_out": check_out, "guests": guests,
         "children": children, "infants": infants, "room_types": room_types},
        tool_ctx,
    )
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def crear_reserva(
    ctx: RunContextWrapper[HotelContext],
    room_type: str,
    check_in: str,
    check_out: str,
    guest_name: str,
    guest_email: str = "",
    guest_phone: str = "",
    guests: int = 1,
    children: int = 0,
    infants: int = 0,
    promo_name: str = "",
) -> str:
    """Crea una reserva confirmada y devuelve el código de reserva (HTL-XXXX).
    Llamala SOLO cuando ya tengas TODOS estos datos confirmados por el usuario:
    tipo de habitación, check_in, check_out (YYYY-MM-DD) y nombre del huésped.
    Si falta algún dato, pedíselo al usuario ANTES de llamar a esta herramienta.
    El pago de la demo se simula como pagado al confirmar.

    `promo_name`: si en ESTA conversación se aplicó una promoción a esta habitación y
    fechas (porque usaste `calcular_precio_promo`), pasá el nombre EXACTO de esa promo
    (ej. "Promoción 4x3") para que la reserva quede con el precio con descuento. Si no
    hubo promo, dejalo vacío. El backend revalida que la promo realmente aplique."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "crear_reserva",
        {
            "room_type": room_type,
            "check_in": check_in,
            "check_out": check_out,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "guest_phone": guest_phone,
            "guests": guests,
            "children": children,
            "infants": infants,
            "promo_name": promo_name,
        },
        tool_ctx,
    )
    return result.get("tool_result", "")


@function_tool
async def consultar_reserva(ctx: RunContextWrapper[HotelContext], code: str) -> str:
    """Consulta el estado y los detalles de una reserva existente a partir de su código
    (formato HTL-XXXX). Úsala cuando el usuario quiera ver o confirmar su reserva."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("consultar_reserva", {"code": code}, tool_ctx)
    return result.get("tool_result", "")


# info_pago y promos_vigentes se declaran UNA sola vez en hotel_tools_pkg.agent_tools
# (Fase 6) y se importan más abajo, junto al _TOOLS.


@function_tool
async def como_llegar(
    ctx: RunContextWrapper[HotelContext],
    destino: str = "",
    origen: str = "",
    medio: str = "auto",
) -> str:
    """Arma la ruta en Google Maps y devuelve el link para llegar de un punto a otro.
    Úsala cuando el usuario pregunte cómo llegar a algún lugar, pida una ruta, pregunte
    a cuánto está de un punto (ej. Centro Cívico, Cerro Otto, terminal de ómnibus), o
    cómo llegar al hotel desde su ciudad.
    - `destino`: a dónde quiere ir (ej. "Cerro Otto"). Vacío o "el hotel" = ir al hotel.
    - `origen`: desde dónde sale (ej. "Rosario"). Vacío = desde el hotel.
    - `medio`: "auto" (por defecto) o "caminando".
    SIEMPRE compartí el link de Maps que devuelve la herramienta. NUNCA inventes la
    distancia ni el tiempo: eso lo muestra Google Maps al abrir el link."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "como_llegar",
        {"destino": destino, "origen": origen, "medio": medio},
        tool_ctx,
    )
    return result.get("tool_result", "")


# comercios_amigos y excursiones_y_atracciones se declaran UNA sola vez en
# hotel_tools_pkg.agent_tools (Fase 6) y se importan más abajo, junto al _TOOLS.


@function_tool
async def calcular_precio_promo(
    ctx: RunContextWrapper[HotelContext],
    room_type: str,
    check_in: str,
    check_out: str,
) -> str:
    """Calcula el precio REAL de una estadía concreta aplicando la MEJOR promoción que
    corresponda (ej. 4x3 = pagás 3 noches de 4). El backend hace el cálculo: vos solo
    comunicás el resultado. Devuelve el precio sin promo, el precio con promo y el ahorro.

    USALA SOLO en estas dos situaciones (NO por defecto en cada consulta de disponibilidad):
      (a) el cliente PIDE una promoción/descuento/oferta explícitamente, o
      (b) el cliente muestra RESISTENCIA AL PRECIO (dice que es caro/elevado, menciona
          presupuesto, duda por el valor).
    Si ninguna promo calculable aplica a esas noches, la herramienta sugiere beneficios
    cualitativos y cómo calificar (ej. sumar noches): comunicá eso como upsell amable.

    `room_type`: tipo de habitación (ej. "King"). `check_in`/`check_out`: YYYY-MM-DD."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "calcular_precio_promo",
        {"room_type": room_type, "check_in": check_in, "check_out": check_out},
        tool_ctx,
    )
    # Reincorpora promo_offer (la card con precio tachado) al contexto del turno.
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


# ver_carta se declara UNA sola vez en hotel_tools_pkg.agent_tools (Fase 6) y se
# importa más abajo, junto al _TOOLS.


@function_tool
async def armar_pedido_carta(ctx: RunContextWrapper[HotelContext], items_texto: str) -> str:
    """Cuando el cliente diga POR TEXTO qué quiere comer/tomar (ej. "quiero el ojo de bife y una
    pinta"), usá esta tool para devolverle la carta interactiva YA con esos platos precargados,
    para que confirme o ajuste y elija dónde lo quiere. Pasale en `items_texto` lo que pidió,
    tal cual. Si algún plato no se reconoce, el sistema te avisa para que lo aclares (NUNCA
    inventes platos ni precios)."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("armar_pedido_carta", {"items_texto": items_texto}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def registrar_pedido(ctx: RunContextWrapper[HotelContext], order_code: str = "") -> str:
    """Confirma y registra un pedido del restaurante que el cliente armó en la pantalla de
    carrito (te dará un código RST-XXXX, o lo trae el contexto al volver del carrito).
    Úsala cuando el cliente confirme que terminó su pedido. El backend ya calculó el total
    y, si está hospedado, lo cargó al folio de su habitación; vos solo confirmás con calidez."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("registrar_pedido", {"order_code": order_code}, tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def reservar_mesa(
    ctx: RunContextWrapper[HotelContext],
    fecha: str = "", turno: str = "", personas: int = 0, nombre: str = "",
    codigo_reserva: str = "", notas: str = "",
) -> str:
    """Reserva una MESA del restaurante (no es pedir comida ahora). Úsala SIEMPRE que quieran
    reservar una mesa, APENAS lo digan. LLAMALA DE ENTRADA AUNQUE FALTEN LA FECHA Y LAS PERSONAS:
    la interfaz muestra un selector de día, turno y personas y el huésped completa ahí lo que
    falte — NO le pidas la fecha, la hora ni las personas por texto antes de llamarla; de eso se
    encarga la tarjeta. Pasá `fecha`/`turno`/`personas` solo si ya los mencionó; si no, llamala
    igual con lo que tengas o sin argumentos. El restaurante tiene dos turnos:
    ALMUERZO (mediodía) y CENA (noche). Si el huésped dice "la noche"/"a cenar" pasá
    turno="cena"; si dice "al mediodía"/"a almorzar" pasá turno="almuerzo" (NUNCA pases "noche"
    ni un texto libre como turno). El horario puntual lo elige el huésped en el selector. Si el
    huésped alude a SU estadía ("el primer día", "cuando llegue", "mi primera noche", "el día
    que llego"), NO le pidas la fecha ni asumas hoy: dejá `fecha` VACÍA y el sistema usará el
    check-in de su reserva. Si el huésped está alojado/tiene reserva podés pasar su
    `codigo_reserva` (HTL-XXXX) para asociarla. Si menciona una OCASIÓN o pedido especial
    (cumpleaños, aniversario, "que los reciban con champán", una alergia para esa cena), pasalo
    en `notas` tal cual lo dijo: queda guardado en la reserva y el equipo del salón lo tiene en
    cuenta. NO la confundas con `consultar_disponibilidad` (reservar habitación) ni con
    `ver_carta` (pedir comida)."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("reservar_mesa", {
        "fecha": fecha, "turno": turno, "personas": personas,
        "nombre": nombre, "codigo_reserva": codigo_reserva, "notas": notas,
    }, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def comprar_voucher(ctx: RunContextWrapper[HotelContext]) -> str:
    """Úsala cuando un VISITANTE de afuera quiera COMPRAR o REGALAR comida por anticipado
    (un voucher). Abre la carta en modo voucher: el visitante arma su pedido y recibe un código
    VCH-XXXX para canjear cuando venga al hotel. Tras emitirlo, ofrecé reservar una mesa para
    usarlo (`reservar_mesa`). NO la uses con un huésped ALOJADO: ese carga su pedido al folio
    (es `ver_carta`/`registrar_pedido`, no voucher)."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("comprar_voucher", {}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def guardar_preferencia(
    ctx: RunContextWrapper[HotelContext], preferencias: str, tipo: str = ""
) -> str:
    """Guarda un dato del huésped en su perfil, para tenerlo siempre en cuenta. Úsala apenas el
    cliente mencione algo que valga recordar EN CUALQUIER momento de la charla: una restricción o
    alergia ("soy celíaco", "alérgico al maní"), con quién viaja ("vengo con mi hijo Tomás"), un
    servicio que suele usar ("siempre uso el spa") o una observación para el hotel.
    `preferencias` = lista separada por comas (ej. "vegetariano, sin tacc" o "Tomás").
    `tipo` = "alergia" (seguridad alimentaria) · "dieta" (vegano/vegetariano/sin TACC) ·
    "acompañante" (con quién viaja) · "servicio" (servicio que suele usar) · "nota" (observación
    libre). Si es comida y no estás seguro, dejalo vacío y se clasifica entre alergia y dieta."""
    tool_ctx = ctx.context.as_tool_ctx()
    prefs = [p.strip() for p in (preferencias or "").split(",") if p.strip()]
    args = {"preferencias": prefs}
    if (tipo or "").strip():
        args["tipo"] = tipo.strip()
    result = await execute_tool("guardar_preferencia", args, tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def derivar_a_humano(ctx: RunContextWrapper[HotelContext], motivo: str = "") -> str:
    """Deriva la conversación a una PERSONA del equipo del hotel. Úsala SOLO cuando el huésped
    pide expresamente hablar con alguien, o cuando hay algo que genuinamente NO podés resolver vos
    (no como escape fácil ante cualquier duda). El sistema decide, según haya atención humana
    disponible, si lo pasa en vivo o lo deja registrado para seguimiento — vos solo llamás la tool
    con un `motivo` breve y confirmás con calidez lo que devuelva."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("derivar_a_humano", {"motivo": motivo}, tool_ctx)
    return result.get("tool_result", "")


# Tools declaradas UNA vez y compartidas con post-venta (Fase 6).
from app.services.hotel_tools_pkg.agent_tools import (  # noqa: E402
    comercios_amigos, excursiones_y_atracciones, info_pago, promos_vigentes, ver_carta,
)

_TOOLS = [
    info_hotel, consultar_disponibilidad, crear_reserva, consultar_reserva, info_pago,
    como_llegar, comercios_amigos, excursiones_y_atracciones, promos_vigentes, calcular_precio_promo,
    ver_carta, armar_pedido_carta, registrar_pedido, reservar_mesa, comprar_voucher,
    guardar_preferencia, derivar_a_humano,
]

# Fase 2.2: registro en el ToolRegistry con key "presale.<nombre>".
from app.core.agents.tool_registry import register_tool  # noqa: E402
for _t in _TOOLS:
    register_tool(f"presale.{_t.name}", _t)


# ---------------------------------------------------------------------------
# GUARDRAIL — input anti-jailbreak (mismo patrón que Freeway)
# ---------------------------------------------------------------------------
_JAILBREAK_MARKERS = (
    "ignore previous", "ignora las instrucciones", "system prompt",
    "olvida tus instrucciones", "reveal your prompt", "actúa como",
)


@input_guardrail
async def relevancia_guardrail(
    ctx: RunContextWrapper[HotelContext], agent: Agent, user_input
) -> GuardrailFunctionOutput:
    text = user_input if isinstance(user_input, str) else str(user_input)
    text_lower = text.lower()
    is_jailbreak = any(m in text_lower for m in _JAILBREAK_MARKERS)

    if is_jailbreak:
        logger.warning("Hotel pre-venta input guardrail: possible jailbreak attempt",
                       preview=text_lower[:80])

    return GuardrailFunctionOutput(
        output_info={"jailbreak_suspected": is_jailbreak},
        tripwire_triggered=is_jailbreak,
    )


# Fase 2.2: registro del guardrail — la spec lo referencia por key.
from app.core.agents.tool_registry import register_guardrail  # noqa: E402
register_guardrail("presale.relevancia", relevancia_guardrail)


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class HotelSDKOrchestrator:
    """Loop de tool calling de pre-venta del hotel sobre el OpenAI Agents SDK."""

    def __init__(self):
        # El modelo real del loop lo construye el runtime desde la spec (sdk_runtime.run_agent).
        # Acá solo guardamos el NOMBRE para el dict de usage del fallback; el objeto model que se
        # construía era dead code (nunca se usaba para correr).
        self._model_name = settings.OPENAI_MODEL
        if not settings.DEBUG:
            set_tracing_disabled(False)

    def _build_instructions(self, lead_block: str, language: str = "es",
                            flow_block: str = "",
                            tono_block: str = DEFAULT_TONO_BLOCK,
                            politica_block: str = DEFAULT_POLITICA_BLOCK,
                            training_block: str = "",
                            team_block: str = "",
                            profile: Optional[dict] = None,
                            customer_facing: bool = True,
                            handoff_disponible: bool = False) -> str:
        now = now_business()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        hora = now.strftime("%H:%M")

        from app.domains.hotel.prompts.identity_blocks import (
            build_identity_block, build_dialect_block, build_facts_block, build_location_block,
        )

        prof = profile or {}
        # El {dialect_block} vive DENTRO del tono default; se resuelve acá (format no es
        # recursivo). Si el cliente SUSTITUYÓ el tono (training), su texto no trae el
        # placeholder → format lo ignora sin romper.
        dialect = build_dialect_block(prof)
        tono_resuelto = tono_block.replace("{dialect_block}", dialect)

        return TOOL_AGENT_SYSTEM.format(
            agent_name=prof.get("agent_display_name") or profile_manager.get_agent_name(),
            identity_block=build_identity_block(prof),
            facts_block=build_facts_block(prof),
            fecha_actual=fecha,
            hora_actual=hora,
            flow_block=flow_block,
            tono_block=tono_resuelto,
            politica_block=politica_block,
            training_block=training_block,
            lead_block=lead_block,
            language_block=build_language_block(language),
            naturalidad_block=NATURALIDAD_BLOCK if customer_facing else "",
            handoff_block=_handoff_block(handoff_disponible) if customer_facing else "",
            multi_intent_block=MULTI_INTENT_BLOCK if customer_facing else "",
            ubicacion_block=build_location_block(prof),
            team_block=team_block,
            negocio=prof.get("business_name") or "el hotel",  # límite de dominio (Fase A)
            ciudad=prof.get("city") or "la ciudad",
        )

    def _availability_already_shown(self, db: Session, session_id: str) -> bool:
        """¿En esta sesión la tool de disponibilidad ya devolvió habitaciones? (turnos previos).

        Lee el flag en Conversation.extra_metadata. Best-effort: ante cualquier problema, asume
        que NO (cae al comportamiento de captura pasiva, que es el conservador).
        """
        try:
            from app.models.conversation import Conversation
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            return bool(conv and (conv.extra_metadata or {}).get(_AVAILABILITY_SHOWN_FLAG))
        except Exception as e:  # noqa: BLE001
            logger.debug("No se pudo leer el flag availability_shown", error=str(e))
            return False

    def _mark_availability_shown(self, db: Session, session_id: str) -> None:
        """Marca en la Conversation que ya se mostró disponibilidad real en esta sesión.

        Se llama al final de un turno donde la tool ofreció habitaciones, para que el gating del
        próximo turno sepa que el huésped ya vio opciones y corresponda ofrecer reservar.
        """
        try:
            from app.models.conversation import Conversation
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if not conv:
                return
            meta = dict(conv.extra_metadata or {})
            if not meta.get(_AVAILABILITY_SHOWN_FLAG):
                meta[_AVAILABILITY_SHOWN_FLAG] = True
                conv.extra_metadata = meta
                db.commit()
                # Bitácora del lead: Aura ofreció disponibilidad (idempotente, best-effort).
                try:
                    from app.services import lead_events_service as les
                    les.log_lead_event_by_session(db, session_id, "availability_shown")
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo marcar availability_shown", session_id=session_id, error=str(e))

    @staticmethod
    def _variant_allows_capture(variant: Optional[str], analysis: Dict) -> bool:
        """¿La variante del flujo permite la captura proactiva de contacto?

        "sin_presion" la suprime, salvo pedido EXPRESO del huésped (contact_readiness).
        Cualquier otra variante (o ninguna config) → permitida (paridad).
        """
        if (variant or "").strip().lower() != "sin_presion":
            return True
        return bool(analysis.get("contact_readiness", False))

    async def _build_lead_block(
        self, db: Session, message: str, session_id: str, history: List[Dict],
        flow_criteria: Optional[Dict] = None,
    ) -> tuple[str, Dict, bool, Optional[int]]:
        """Análisis de lead transversal (igual que Freeway, sin geo).

        Devuelve además el contact_id resuelto (Fase 6) para que run() lo pase al HotelContext.
        """
        lead = lead_service._get_or_create_lead(db, session_id)
        has_contact_info = lead.is_complete_lead()
        is_whatsapp = session_id.startswith("wa_")

        # GATING: el análisis de lead (1+ llamadas LLM) corre antes del agente y lo bloquea.
        # En los primeros turnos nunca se pide contacto (should_request_contact exige el
        # mínimo de mensajes del flujo), así que lo salteamos para no pagar esa latencia de
        # entrada. Tampoco hace falta si ya tenemos el lead completo (no hay nada nuevo que
        # captar). En esos casos devolvemos un análisis neutro y seguimos con el perfil.
        min_msgs = (flow_criteria or {}).get(
            "min_msgs", lead_analyzer.CONTACT_CRITERIA_DEFAULTS["min_msgs"]
        )
        skip_lead_analysis = len(history) < min_msgs or has_contact_info
        if skip_lead_analysis:
            lead_analysis, should_request_contact = {}, False
        else:
            # Sin análisis geográfico: pasamos dict vacío (el lead_service lo tolera).
            lead_analysis, should_request_contact = await lead_service.process_message_for_lead(
                db, message, session_id, history, "", {}, flow_criteria=flow_criteria,
            )

        # Variante "sin_presion" (Fase B): la captura PROACTIVA se suprime para que el
        # comportamiento cumpla lo que la variante promete. Excepción: si el huésped pidió
        # expresamente ser contactado, capturar no es presión — es servicio.
        if should_request_contact and not self._variant_allows_capture(
            (flow_criteria or {}).get("variante"), lead_analysis
        ):
            should_request_contact = False

        # Perfil del huésped conocido (recurrente/alojado): personaliza la conversación.
        # Se antepone a cualquier bloque de lead cuando hay historial real.
        guest_block, contact_id = self._build_guest_block(db, session_id, lead)

        lead_block = ""
        if has_contact_info:
            contact_name = lead.name or "este usuario"
            details = []
            if lead.name:
                full = f"{lead.name} {lead.last_name}" if lead.last_name else lead.name
                details.append(f"Nombre: {full}")
            if lead.phone:
                details.append(f"Teléfono: {lead.phone}")
            if lead.email:
                details.append(f"Email: {lead.email}")
            lead_block = build_lead_context_block(contact_name, details)
        elif is_whatsapp and lead.phone:
            # WhatsApp: ya conocemos el teléfono. No lo pedimos; pedimos solo el nombre
            # y ofrecemos usar/cambiar este número. (No depende de should_request_contact:
            # apenas tengamos el teléfono pre-cargado conviene guiar así la reserva.)
            lead_block = build_whatsapp_contact_block(lead.phone)
        elif should_request_contact:
            main_interest = lead_analysis.get("main_interest", "tu estadía")
            if self._availability_already_shown(db, session_id):
                # Ya vio disponibilidad. Distinguir DOS cierres:
                #  - OBJETÓ el precio o se está despidiendo ("muy caro", "lo voy a pensar") →
                #    NO insistir con reservar: captar el contacto para avisarle de PROMOS.
                #  - Sigue evaluando sin objetar → ofrecé reservar (nudge), como hasta ahora.
                obstacle = (lead_analysis.get("obstacle") or "").lower()
                is_price_or_exit = obstacle == "precio" or lead_analyzer._is_exit_intent(message)
                lead_block = (
                    build_price_objection_capture_block(main_interest)
                    if is_price_or_exit
                    else build_booking_nudge_block(main_interest)
                )
            else:
                # Sin disponibilidad mostrada: captura pasiva clásica.
                lead_block = build_contact_request_block(main_interest)

        # El perfil del huésped va PRIMERO (contexto de quién es), luego el bloque de lead.
        return (guest_block + lead_block), lead_analysis, should_request_contact, contact_id

    def _build_guest_block(self, db: Session, session_id: str, lead) -> tuple[str, Optional[int]]:
        """Bloque de perfil del huésped para pre-venta (nivel guest = 360 completo).

        Delega en guest_context_service (helper único con niveles por rol, Fase 1). El bloque
        es idéntico al anterior para un huésped sin ai_summary; con ai_summary suma una línea.

        Devuelve también el contact_id resuelto (Fase 6): pre-venta lo propaga al HotelContext
        para que las tools de restaurante lo reciban en el ctx (antes solo lo tenía post-venta),
        cerrando la asimetría por la que un huésped web identificado no resolvía su contacto.
        """
        from app.services import guest_context_service
        contact_id = guest_context_service.resolve_contact_id(session_id, lead, db)
        return guest_context_service.build_guest_context("guest", contact_id, db), contact_id

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(
        self, db: Session, message: str, session_id: str, history: List[Dict],
        language: str = "es",
    ) -> Dict:
        """Procesa un turno de pre-venta del hotel con el SDK."""
        start = time.time()

        # 0. Config del flujo del Centro (Fase A). None → defaults hardcodeados (paridad).
        from app.services import skill_service
        flow_criteria = skill_service.get_flow_values_for_session(db, session_id, "flujo_preventa")

        # 1. Lead analysis transversal → bloque para el prompt
        lead_block, lead_analysis, should_request_contact, contact_id = await self._build_lead_block(
            db, message, session_id, history, flow_criteria=flow_criteria
        )

        # 2. Construir el Agent. Las tools se filtran por las function-skills habilitadas
        #    del agente (mapa vacío en Fase A → lista intacta). El flow_block lo elige la
        #    VARIANTE del flujo (Fase B): "estandar" → vacío (paridad exacta). El
        #    entrenamiento del cliente (Fase E2) SUSTITUYE tono/política y suma directivas
        #    aditivas; sin docs efectivos → defaults del código (paridad).
        variant = (flow_criteria or {}).get("variante", "estandar")
        from app.services import training_service
        from app.services.agent_directory import agent_for_session
        try:
            _agent_row = agent_for_session(db, session_id)
            blocks = training_service.get_training_blocks(db, _agent_row.id if _agent_row else None)
        except Exception as e:  # noqa: BLE001 — fail-open a los defaults
            # El cliente pierde su tono/política entrenados y cae a defaults: dejamos rastro
            # (antes era un silencio total, difícil de diagnosticar "por qué cambió el tono").
            logger.warning("No se pudieron cargar los training blocks; usando defaults",
                           session_id=session_id, error=str(e))
            blocks = {"tono_block": DEFAULT_TONO_BLOCK, "politica_block": DEFAULT_POLITICA_BLOCK,
                      "training_block": ""}
        # Roster del equipo real (Fase 0.1): acompaña la regla anti-invención de
        # personas — el agente solo reconoce por nombre a quien figura acá.
        from app.domains.hotel.prompts.base_blocks import build_team_roster_block
        # Identidad del negocio (Fase 1): compone el encabezado y el dialecto desde el perfil.
        from app.services import business_profile_service
        profile = business_profile_service.get_profile(db)
        # Fase 2.2: el loop del SDK corre por el runtime declarativo (spec hotel_presale:
        # turns=6, hist=20, temp=settings, 16 tools + guardrail). Las tools se FILTRAN por
        # sesión (config del Centro) vía tools_override — la spec declara el catálogo.
        from app.core.agents.sdk_runtime import run_agent, build_input_list
        from app.domains.hotel.agent_specs import SPECS
        spec = SPECS["hotel_presale"]
        from app.services import human_attention_service
        handoff_disponible = human_attention_service.is_human_available(db)
        instructions = self._build_instructions(
            lead_block, language, flow_block=flow_block_for(variant),
            tono_block=blocks["tono_block"], politica_block=blocks["politica_block"],
            training_block=blocks["training_block"],
            team_block=build_team_roster_block(db),
            profile=profile,
            customer_facing=spec.customer_facing,
            handoff_disponible=handoff_disponible,
        )

        # 3. Contexto del turno
        run_ctx = HotelContext(db, message, history, session_id=session_id, contact_id=contact_id)
        input_list = build_input_list(history, message, spec.max_history)

        # 4. Ejecutar el loop del SDK
        from agents import InputGuardrailTripwireTriggered

        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": self._model_name}
        try:
            out = await run_agent(
                spec, instructions=instructions, context=run_ctx, input_list=input_list,
                display_name=profile_manager.get_agent_name(),
                tools_override=skill_service.filter_tools_for_session(db, session_id, _TOOLS),
            )
            usage = out["usage"]
            response_text = out["response"]
            tools_used = out["tools_used"]
            # Traza detallada (nombre + args + output) para la auditoría del chat.
            from app.core.observability.audit_log import build_tool_trace
            tool_trace = build_tool_trace(out["result"])
        except InputGuardrailTripwireTriggered:
            logger.warning("Hotel pre-venta: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte con tu estadía en el Hampton by Hilton Bariloche. "
                "¿Querés que te muestre las habitaciones o consultemos disponibilidad? 😊"
            )
            tools_used = []
            tool_trace = []
        except Exception as e:
            logger.error("Hotel pre-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un problema procesando tu consulta. "
                "¿Podés intentarlo de nuevo en un momento?"
            )
            tools_used = []
            tool_trace = []

        if not response_text:
            response_text = "Disculpá, no pude generar una respuesta. ¿Podés reformular tu consulta?"

        duration = time.time() - start
        logger.info("Hotel pre-venta SDK turn completed",
                    session_id=session_id,
                    tools_used=tools_used,
                    duration=f"{duration:.2f}s")

        # Si en este turno se ofrecieron habitaciones, dejá la marca para que el próximo turno
        # cierre la venta (ofrecer reservar) en vez de captar lead pasivo.
        if run_ctx.rooms_offered:
            self._mark_availability_shown(db, session_id)

        return {
            "response": response_text,
            "agent_key": spec.key,  # observabilidad (3.4): qué agente generó la respuesta
            "has_context": bool(run_ctx.document_sources),
            "document_sources": run_ctx.document_sources,
            "rooms_offered": run_ctx.rooms_offered,
            "promo_offer": run_ctx.promo_offer,
            "menu_card": run_ctx.menu_card,
            "table_card": run_ctx.table_card,
            "tools_used": tools_used,
            "tool_trace": tool_trace,
            "processing_time": f"{duration:.2f}s",
            "usage": usage,
            "lead_analysis": {
                "lead_type": lead_analysis.get("lead_type"),
                "interest_score": lead_analysis.get("interest_score"),
                "contact_readiness": lead_analysis.get("contact_readiness"),
                "main_interest": lead_analysis.get("main_interest"),
                "has_contact_info": lead_analysis.get("has_contact_info", False),
                "priority_score": lead_analysis.get("priority_score", 0),
                "contact_requested": should_request_contact,
            },
        }


# Instancia global
hotel_sdk_orchestrator = HotelSDKOrchestrator()
