"""
Orquestador de POST-VENTA sobre el OpenAI Agents SDK.

Delega el loop de tool calling, los guardrails y el tracing al SDK oficial
(`agents`). Firma pública
`run(service, package, ticket, message, session_id, history) -> Dict`. Es el único
camino de post-venta (el loop casero fue retirado en P4); agent_service.chat()
delega siempre acá.

Reutiliza SIN reescribir:
  - Las tools de postsale_tools.py (vía execute_tool) envueltas como @function_tool.
  - El system prompt POSTSALE_TOOL_SYSTEM y el contexto del paquete (_build_package_context).
  - La ACCIÓN DETERMINÍSTICA sobre el ticket (postsale_orchestrator._apply_ticket_action),
    que el LLM NO decide: escalar/resolver se aplica según el análisis recogido en ctx.

El gate determinístico (validación de reserva, contacto, ticket de sesión, atajos
voucher/cortesía) ya corrió en agent_service.chat() y nos entrega el `package` validado
y el `ticket` de sesión.
"""
import time
from typing import Dict, List

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
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai
from app.prompts.postsale_tool_prompts import POSTSALE_TOOL_SYSTEM
from app.services.postsale_tools import execute_tool
from app.services.postsale_orchestrator import postsale_orchestrator
from app.services.shared_sdk_tools import obtener_clima

logger = get_logger(__name__)

MAX_TURNS = 6
MAX_HISTORY_MESSAGES = 8

# Cliente OpenAI compartido por el SDK (singleton del proyecto, ver core/openai_client).
_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# CONTEXTO POR TURNO — se inyecta a las tools vía RunContextWrapper
# ---------------------------------------------------------------------------
class PostventaContext:
    """Contexto mutable de un turno; equivale al `ctx` dict del orquestador casero.

    Lleva service/package/ticket/message/history para las tools y recoge la decisión
    de escalación (escalation_analysis) y flight_issues que el orquestador necesita
    para aplicar la acción determinística sobre el ticket.
    """

    def __init__(self, service, package, ticket, message: str, history: List[Dict]):
        self.service = service       # PostSaleService (con .db)
        self.package = package       # SoldPackage validado
        self.ticket = ticket         # SupportTicket de sesión
        self.message = message
        self.history = history
        self.escalation_analysis = None  # lo escribe analizar_severidad_y_escalacion
        self.flight_issues = False       # lo escribe consultar_estado_vuelo

    def as_tool_ctx(self) -> Dict:
        """Adapta a la forma de dict que esperan los handlers de postsale_tools.execute_tool."""
        return {
            "service": self.service,
            "package": self.package,
            "db": self.service.db,
            "message": self.message,
            "history": self.history,
            "escalation_analysis": self.escalation_analysis,
            "flight_issues": self.flight_issues,
        }

    def absorb(self, tool_ctx: Dict):
        """Recupera lo que las tools escribieron en el dict mutable."""
        self.escalation_analysis = tool_ctx.get("escalation_analysis", self.escalation_analysis)
        self.flight_issues = tool_ctx.get("flight_issues", self.flight_issues)


# ---------------------------------------------------------------------------
# TOOLS — envuelven los handlers existentes de postsale_tools.execute_tool
# ---------------------------------------------------------------------------
@function_tool
async def analizar_severidad_y_escalacion(
    ctx: RunContextWrapper[PostventaContext], consulta: str
) -> str:
    """Analiza la consulta del cliente sobre su viaje ya comprado y determina si podés
    resolverla vos (informativa, dudas, detalles del paquete) o si requiere escalación a
    un asesor humano (problemas, cambios, reclamos, urgencias). OBLIGATORIO llamarla una
    vez antes de dar tu respuesta final a una consulta de soporte. Devuelve la decisión
    de escalación, urgencia y categoría que debés respetar."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("analizar_severidad_y_escalacion", {"consulta": consulta}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def consultar_estado_vuelo(ctx: RunContextWrapper[PostventaContext]) -> str:
    """Consulta el estado actual de los vuelos del paquete del cliente (demoras,
    cancelaciones, cambios). Úsala cuando el cliente pregunta por su vuelo o cuando una
    consulta puede depender del estado del vuelo."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("consultar_estado_vuelo", {}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def obtener_contacto_proveedor(
    ctx: RunContextWrapper[PostventaContext], categoria: str
) -> str:
    """Obtiene los datos de contacto del proveedor relacionado con la consulta (hotel,
    transfer, aerolínea, actividad) para ofrecérselos al cliente cuando es útil que
    contacte directamente al proveedor. Devuelve nombre y teléfono reales del proveedor
    del paquete. Categoría: hotel, transfer, flight o activity."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("obtener_contacto_proveedor", {"categoria": categoria}, tool_ctx)
    return result.get("tool_result", "")


# obtener_clima es compartida con pre-venta (shared_sdk_tools): el agente post-venta,
# como compañero de viaje, puede consultar el clima del destino del cliente.
_TOOLS = [
    analizar_severidad_y_escalacion,
    consultar_estado_vuelo,
    obtener_contacto_proveedor,
    obtener_clima,
]


# ---------------------------------------------------------------------------
# GUARDRAILS — solo input anti-jailbreak (espejo del de pre-venta)
# ---------------------------------------------------------------------------
_JAILBREAK_MARKERS = (
    "ignore previous", "ignora las instrucciones", "system prompt",
    "olvida tus instrucciones", "reveal your prompt", "actúa como",
)


@input_guardrail
async def relevancia_guardrail(
    ctx: RunContextWrapper[PostventaContext], agent: Agent, user_input
) -> GuardrailFunctionOutput:
    text = user_input if isinstance(user_input, str) else str(user_input)
    text_lower = text.lower()
    is_jailbreak = any(m in text_lower for m in _JAILBREAK_MARKERS)

    if is_jailbreak:
        logger.warning("Post-venta SDK input guardrail: possible jailbreak attempt",
                       preview=text_lower[:80])

    return GuardrailFunctionOutput(
        output_info={"jailbreak_suspected": is_jailbreak},
        tripwire_triggered=is_jailbreak,
    )


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class PostSaleSDKOrchestrator:
    """Loop de tool calling de post-venta sobre el OpenAI Agents SDK, con acción
    determinística sobre el ticket (reusada del orquestador casero)."""

    def __init__(self):
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )
        if not settings.DEBUG:
            set_tracing_disabled(False)  # mantener trazas en consola/dashboard

    def _format_history(self, history: List[Dict]) -> str:
        if not history:
            return "No hay historial previo."
        recent = history[-MAX_HISTORY_MESSAGES:]
        lines = []
        for m in recent:
            role = "Usuario" if m.get("role") == "user" else "Asistente"
            lines.append(f"{role}: {m.get('content', '')[:300]}")
        return "\n".join(lines)

    def _build_instructions(self, service, package, history: List[Dict]) -> str:
        package_context = service._build_package_context(package)
        passenger = f"{package.passenger_name or ''} {package.passenger_lastname or ''}".strip() or "el cliente"
        return POSTSALE_TOOL_SYSTEM.format(
            agent_name=profile_manager.get_agent_name(),
            passenger_name=passenger,
            package_context=package_context,
            chat_history=self._format_history(history),
        )

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(
        self,
        service,
        package,
        ticket,
        message: str,
        session_id: str,
        history: List[Dict],
    ) -> Dict:
        """Procesa un turno de post-venta con el SDK. Mismo contrato que PostSaleOrchestrator.run()."""
        start = time.time()

        # 1. Construir el Agent con instrucciones, tools y guardrail
        instructions = self._build_instructions(service, package, history)
        agent = Agent[PostventaContext](
            name=profile_manager.get_agent_name(),
            instructions=instructions,
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=0.7),
            input_guardrails=[relevancia_guardrail],
        )

        # 2. Contexto del turno (compartido con tools y guardrail)
        run_ctx = PostventaContext(service, package, ticket, message, history)
        input_list = self._build_input_list(history, message)

        # 3. Ejecutar el loop del SDK
        from agents import InputGuardrailTripwireTriggered

        run_failed = False
        try:
            result = await Runner.run(
                agent,
                input=input_list,
                context=run_ctx,
                max_turns=MAX_TURNS,
            )
            response_text = result.final_output or ""
            tools_used = [
                item.raw_item.name
                for item in getattr(result, "new_items", [])
                if getattr(item, "type", None) == "tool_call_item"
                and hasattr(getattr(item, "raw_item", None), "name")
            ]
        except InputGuardrailTripwireTriggered:
            logger.warning("Post-venta SDK: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte con tu viaje ya comprado. "
                "¿En qué puedo asistirte con tu reserva? 😊"
            )
            tools_used = []
        except Exception as e:
            # Fallback genérico: error de OpenAI, tool, timeout o shape inesperado del SDK.
            # No propagamos un 500. Marcamos run_failed para escalar el ticket por seguridad
            # (no auto-resolver algo que no pudimos analizar).
            logger.error("Post-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un inconveniente procesando tu consulta. "
                "Un asesor va a revisar tu caso a la brevedad."
            )
            tools_used = []
            run_failed = True

        if not response_text:
            response_text = "Disculpá, no pude procesar tu consulta. ¿Podés reformularla?"

        # 4. ACCIÓN DETERMINÍSTICA SOBRE EL TICKET (no la decide el LLM)
        #    Reusa la lógica del orquestador casero — una sola fuente de verdad.
        #    Si el run falló, escalamos por seguridad (no auto-resolver sin análisis).
        escalation = run_ctx.escalation_analysis
        requires_escalation = (
            run_failed
            or bool(escalation and escalation.get("requires_escalation"))
            or run_ctx.flight_issues
        )

        status = postsale_orchestrator._apply_ticket_action(
            service, ticket, requires_escalation, response_text, message, escalation
        )

        duration = time.time() - start
        logger.info("Post-venta SDK turn completed",
                    session_id=session_id, tools_used=tools_used,
                    status=status, duration=f"{duration:.2f}s")

        return {
            "response": response_text,
            "has_context": True,
            "context_type": "postsale",
            "ticket_created": True,
            "ticket_number": ticket.ticket_number,
            "priority": ticket.priority,
            "status": status,
            "can_auto_resolve": not requires_escalation,
            "tools_used": tools_used,
            "processing_time": f"{duration:.2f}s",
        }


# Instancia global
postsale_sdk_orchestrator = PostSaleSDKOrchestrator()
