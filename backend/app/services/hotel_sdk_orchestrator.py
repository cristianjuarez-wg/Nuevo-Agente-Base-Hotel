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
from app.utils.timezone_utils import now_argentina
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai
from app.core.sdk_usage import extract_usage
from app.services.lead_service import lead_service
from app.services.rag_service import rag_service
from app.services.hotel_tools import execute_tool
from app.prompts.tool_agent_prompts import TOOL_AGENT_SYSTEM
from app.prompts.context_blocks import (
    build_lead_context_block,
    build_contact_request_block,
    build_whatsapp_contact_block,
    build_guest_profile_block,
    build_language_block,
)

logger = get_logger(__name__)

MAX_TURNS = 6
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

    def __init__(self, db: Session, message: str, history: List[Dict], session_id: str = ""):
        self.db = db
        self.message = message
        self.history = history
        self.session_id = session_id
        self.document_sources: List = []
        # Habitaciones consultadas en este turno (para renderizar tarjetas en el chat).
        self.rooms_offered: List[Dict] = []
        # Oferta de promo calculada en este turno (card con precio tachado), si la hubo.
        self.promo_offer: Optional[Dict] = None
        # Card de la carta del restaurante (botón "Ver carta y pedir"), si se mostró.
        self.menu_card: Optional[Dict] = None
        self.table_card: Optional[Dict] = None

    def as_tool_ctx(self) -> Dict:
        return {
            "db": self.db,
            "message": self.message,
            "history": self.history,
            "session_id": self.session_id,
            "document_sources": self.document_sources,
            "rooms_offered": self.rooms_offered,
            "promo_offer": self.promo_offer,
            "menu_card": self.menu_card,
            "table_card": self.table_card,
        }

    def absorb(self, tool_ctx: Dict):
        self.document_sources = tool_ctx.get("document_sources", self.document_sources)
        self.rooms_offered = tool_ctx.get("rooms_offered", self.rooms_offered)
        self.promo_offer = tool_ctx.get("promo_offer", self.promo_offer)
        self.menu_card = tool_ctx.get("menu_card", self.menu_card)
        self.table_card = tool_ctx.get("table_card", self.table_card)


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
) -> str:
    """Consulta qué tipos de habitación están disponibles para un rango de fechas y
    cantidad de huéspedes, con el precio total en USD y ARS. Úsala SIEMPRE que el usuario
    quiera reservar o pregunte por disponibilidad/precios para fechas concretas.
    Las fechas deben estar en formato YYYY-MM-DD.
    `guests` = adultos (18+). `children` = niños (3-17, cuentan para la capacidad).
    `infants` = bebés (0-2, van en cuna y NO cuentan para la capacidad de la habitación)."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "consultar_disponibilidad",
        {"check_in": check_in, "check_out": check_out, "guests": guests,
         "children": children, "infants": infants},
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


@function_tool
async def info_pago(ctx: RunContextWrapper[HotelContext], consulta: str = "") -> str:
    """Devuelve los datos EXACTOS de pago y transferencia bancaria del hotel: medios de
    pago aceptados, y para transferencias el titular, banco, CBU y alias.
    Úsala SOLO cuando el usuario pregunte específicamente cómo pagar, dónde/cómo transferir,
    pida el CBU, el alias o los datos bancarios. Para cualquier OTRA consulta del hotel
    (servicios, habitaciones, políticas, ubicación) usá `info_hotel`, no esta.
    El parámetro `consulta` es la pregunta del usuario (opcional, informativo).
    Devolvé los datos tal cual, sin inventar ni alterar."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("info_pago", {"consulta": consulta}, tool_ctx)
    return result.get("tool_result", "")


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


@function_tool
async def comercios_amigos(ctx: RunContextWrapper[HotelContext], rubro: str = "") -> str:
    """Devuelve los comercios amigos del hotel (gastronomía, heladerías, chocolaterías,
    restaurantes con acuerdo) y sus beneficios/descuentos para huéspedes.
    Úsala cuando el usuario pida recomendaciones de dónde comer, lugares con descuento,
    heladerías, chocolaterías o restaurantes cerca del hotel.
    `rubro` (opcional): tipo de comercio que busca (ej. "heladería", "restaurante").
    Si no hay comercios amigos para ese rubro, la herramienta devuelve un link de
    búsqueda en Google Maps; compartilo igual."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("comercios_amigos", {"rubro": rubro}, tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def promos_vigentes(ctx: RunContextWrapper[HotelContext], consulta: str = "") -> str:
    """Devuelve las promociones y ofertas especiales VIGENTES del hotel en este momento,
    con descripción de cada una, el tipo de descuento y las condiciones.
    Úsala SIEMPRE que el usuario pregunte EN GENERAL sobre promociones, ofertas, descuentos,
    tarifas especiales o 'qué promociones tienen' (listado informativo).
    Para CALCULAR el precio con descuento de una estadía concreta, usá `calcular_precio_promo`.
    Devolvé los datos tal cual, sin inventar ni modificar ningún beneficio."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("promos_vigentes", {"consulta": consulta}, tool_ctx)
    return result.get("tool_result", "")


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


@function_tool
async def ver_carta(ctx: RunContextWrapper[HotelContext], categoria: str = "") -> str:
    """Devuelve la carta del restaurante PLAZA - Hampton's Kitchen House (platos, precios,
    tags dietéticos) y un link para que el cliente arme su pedido en la pantalla de carrito.
    Úsala cuando pregunten por el menú, qué hay para comer/tomar, room service o pedir comida.
    `categoria` opcional filtra (ej. "tapas", "postre", "trago"). Si el cliente tiene
    preferencias dietéticas guardadas, sugerí acorde."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("ver_carta", {"categoria": categoria}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


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
    codigo_reserva: str = "",
) -> str:
    """Reserva una MESA del restaurante (no es pedir comida ahora). Úsala cuando quieran
    reservar mesa para un día. La interfaz muestra un selector de día, turno y personas — NO
    le pidas la hora por texto; de eso se encarga la tarjeta. Si el huésped está alojado podés
    pasar su `codigo_reserva` (HTL-XXXX) para asociarla. Si ya tenés todos los datos
    (fecha, turno, personas, nombre) se confirma directo con el código MESA-XXXX; si faltan,
    se muestra el selector. NO la confundas con `consultar_disponibilidad` (reservar habitación)
    ni con `ver_carta` (pedir comida)."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("reservar_mesa", {
        "fecha": fecha, "turno": turno, "personas": personas,
        "nombre": nombre, "codigo_reserva": codigo_reserva,
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
    """Guarda una preferencia dietética o ALERGIA del huésped en su perfil, para tenerla
    siempre en cuenta. Úsala apenas el cliente mencione una restricción, gusto o alergia
    EN CUALQUIER momento de la charla (no solo al pedir comida): ej. "soy vegetariano",
    "soy celíaco", "soy alérgico al maní", "no como carne".
    `preferencias` = lista separada por comas (ej. "vegetariano, sin tacc").
    `tipo` = "alergia" si es una alergia/intolerancia (seguridad alimentaria), o "dieta"
    si es una preferencia dietética. Si no estás seguro, dejalo vacío y se clasifica solo."""
    tool_ctx = ctx.context.as_tool_ctx()
    prefs = [p.strip() for p in (preferencias or "").split(",") if p.strip()]
    args = {"preferencias": prefs}
    if (tipo or "").strip():
        args["tipo"] = tipo.strip()
    result = await execute_tool("guardar_preferencia", args, tool_ctx)
    return result.get("tool_result", "")


_TOOLS = [
    info_hotel, consultar_disponibilidad, crear_reserva, consultar_reserva, info_pago,
    como_llegar, comercios_amigos, promos_vigentes, calcular_precio_promo,
    ver_carta, armar_pedido_carta, registrar_pedido, reservar_mesa, comprar_voucher,
    guardar_preferencia,
]


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


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class HotelSDKOrchestrator:
    """Loop de tool calling de pre-venta del hotel sobre el OpenAI Agents SDK."""

    def __init__(self):
        self._model_name = settings.OPENAI_MODEL
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )
        if not settings.DEBUG:
            set_tracing_disabled(False)

    def _build_instructions(self, lead_block: str, language: str = "es") -> str:
        now = now_argentina()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        hora = now.strftime("%H:%M")

        return TOOL_AGENT_SYSTEM.format(
            agent_name=profile_manager.get_agent_name(),
            fecha_actual=fecha,
            hora_actual=hora,
            lead_block=lead_block,
            language_block=build_language_block(language),
        )

    async def _build_lead_block(
        self, db: Session, message: str, session_id: str, history: List[Dict]
    ) -> tuple[str, Dict, bool]:
        """Análisis de lead transversal (igual que Freeway, sin geo)."""
        lead = lead_service._get_or_create_lead(db, session_id)
        has_contact_info = lead.is_complete_lead()

        # Sin análisis geográfico: pasamos dict vacío (el lead_service lo tolera).
        lead_analysis, should_request_contact = await lead_service.process_message_for_lead(
            db, message, session_id, history, "", {}
        )

        is_whatsapp = session_id.startswith("wa_")

        # Perfil del huésped conocido (recurrente/alojado): personaliza la conversación.
        # Se antepone a cualquier bloque de lead cuando hay historial real.
        guest_block = self._build_guest_block(db, session_id, lead)

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
            lead_block = build_contact_request_block(main_interest)

        # El perfil del huésped va PRIMERO (contexto de quién es), luego el bloque de lead.
        return (guest_block + lead_block), lead_analysis, should_request_contact

    def _build_guest_block(self, db: Session, session_id: str, lead) -> str:
        """Si el contacto tiene historial (reserva/preferencias), arma el bloque de perfil.

        Resuelve el Contact por lead.contact_id o, en WhatsApp, por el teléfono del
        session_id. Cae con gracia (string vacío) si no hay perfil útil.
        """
        try:
            from app.services.contact_service import contact_service
            from app.models.contact import Contact

            contact_id = getattr(lead, "contact_id", None)
            if not contact_id and session_id.startswith("wa_"):
                phone = "+" + session_id[3:]
                c = db.query(Contact).filter(Contact.phone_number == phone).first()
                contact_id = c.id if c else None
            if not contact_id:
                return ""

            profile = contact_service.get_guest_profile(contact_id, db)
            # Solo personalizamos si hay algo que contar (estadías o preferencias).
            if not profile or (not profile.get("stays_count") and not profile.get("preferences")):
                return ""
            return build_guest_profile_block(profile)
        except Exception as e:  # noqa: BLE001 — nunca romper el turno por personalización
            logger.warning("No se pudo armar el guest profile block", error=str(e))
            return ""

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

        # 1. Lead analysis transversal → bloque para el prompt
        lead_block, lead_analysis, should_request_contact = await self._build_lead_block(
            db, message, session_id, history
        )

        # 2. Construir el Agent
        instructions = self._build_instructions(lead_block, language)
        agent = Agent[HotelContext](
            name=profile_manager.get_agent_name(),
            instructions=instructions,
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=settings.OPENAI_TEMPERATURE),
            input_guardrails=[relevancia_guardrail],
        )

        # 3. Contexto del turno
        run_ctx = HotelContext(db, message, history, session_id=session_id)
        input_list = self._build_input_list(history, message)

        # 4. Ejecutar el loop del SDK
        from agents import InputGuardrailTripwireTriggered

        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": self._model_name}
        try:
            result = await Runner.run(
                agent,
                input=input_list,
                context=run_ctx,
                max_turns=MAX_TURNS,
            )
            usage = extract_usage(result, model=self._model_name)
            response_text = result.final_output or ""
            tools_used = [
                item.raw_item.name
                for item in getattr(result, "new_items", [])
                if getattr(item, "type", None) == "tool_call_item"
                and hasattr(getattr(item, "raw_item", None), "name")
            ]
        except InputGuardrailTripwireTriggered:
            logger.warning("Hotel pre-venta: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte con tu estadía en el Hampton by Hilton Bariloche. "
                "¿Querés que te muestre las habitaciones o consultemos disponibilidad? 😊"
            )
            tools_used = []
        except Exception as e:
            logger.error("Hotel pre-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un problema procesando tu consulta. "
                "¿Podés intentarlo de nuevo en un momento?"
            )
            tools_used = []

        if not response_text:
            response_text = "Disculpá, no pude generar una respuesta. ¿Podés reformular tu consulta?"

        duration = time.time() - start
        logger.info("Hotel pre-venta SDK turn completed",
                    session_id=session_id,
                    tools_used=tools_used,
                    duration=f"{duration:.2f}s")

        return {
            "response": response_text,
            "has_context": bool(run_ctx.document_sources),
            "document_sources": run_ctx.document_sources,
            "rooms_offered": run_ctx.rooms_offered,
            "promo_offer": run_ctx.promo_offer,
            "menu_card": run_ctx.menu_card,
            "table_card": run_ctx.table_card,
            "tools_used": tools_used,
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
