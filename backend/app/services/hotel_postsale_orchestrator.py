"""
Orquestador de POST-VENTA del HOTEL sobre el OpenAI Agents SDK.

Clon reducido de postsale_sdk_orchestrator.py (Freeway). Mismo patrón:
  - Una tool `analizar_escalacion` (LLM analiza la severidad).
  - Acción determinística sobre el ticket tras el loop (escalar/resolver lo decide código).

Diferencias con Freeway: sin tools de vuelos ni proveedores (no aplican al hotel).
Firma pública `run(service, booking, ticket, message, session_id, history) -> Dict`.
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
from app.core.sdk_usage import extract_usage
from app.prompts.postsale_tool_prompts import POSTSALE_TOOL_SYSTEM

logger = get_logger(__name__)

MAX_TURNS = 5
MAX_HISTORY_MESSAGES = 8

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


_TOOLS = [analizar_escalacion]


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

    def _build_instructions(self, service, booking, history: List[Dict]) -> str:
        booking_context = service.build_booking_context(booking)
        return POSTSALE_TOOL_SYSTEM.format(
            agent_name=profile_manager.get_agent_name(),
            passenger_name=booking.guest_name or "el huésped",
            package_context=booking_context,
            chat_history=self._format_history(history),
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

        instructions = self._build_instructions(service, booking, history)
        agent = Agent[HotelPostventaContext](
            name=profile_manager.get_agent_name(),
            instructions=instructions,
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=0.7),
            input_guardrails=[relevancia_guardrail],
        )

        run_ctx = HotelPostventaContext(service, booking, ticket, message, history)
        input_list = self._build_input_list(history, message)

        from agents import InputGuardrailTripwireTriggered

        run_failed = False
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": self._model_name}
        try:
            result = await Runner.run(
                agent, input=input_list, context=run_ctx, max_turns=MAX_TURNS,
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
            logger.warning("Hotel post-venta: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte con tu reserva en el Hampton Bariloche. "
                "¿En qué puedo asistirte con tu estadía? 😊"
            )
            tools_used = []
        except Exception as e:
            logger.error("Hotel post-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un inconveniente procesando tu consulta. "
                "Un asesor del hotel va a revisar tu caso a la brevedad."
            )
            tools_used = []
            run_failed = True

        if not response_text:
            response_text = "Disculpá, no pude procesar tu consulta. ¿Podés reformularla?"

        # ACCIÓN DETERMINÍSTICA SOBRE EL TICKET — la decide el código, no el LLM.
        # Si el run falló o el análisis pidió escalar, escalamos por seguridad.
        analysis = run_ctx.escalation_analysis
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
            "has_context": True,
            "context_type": "postsale",
            "ticket_created": True,
            "ticket_number": ticket.ticket_number,
            "priority": ticket.priority,
            "status": status,
            "can_auto_resolve": not requires_escalation,
            "tools_used": tools_used,
            "processing_time": f"{duration:.2f}s",
            "usage": usage,
        }


# Instancia global
hotel_postsale_sdk_orchestrator = HotelPostSaleSDKOrchestrator()
