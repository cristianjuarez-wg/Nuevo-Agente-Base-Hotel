"""
Orquestador de PRE-VENTA sobre el OpenAI Agents SDK.

Delega el loop de tool calling, los guardrails y el tracing al SDK oficial
(`agents`). Firma pública `run(db, message, session_id, history) -> Dict`. Es el
único camino de pre-venta (el orquestador casero fue retirado en P4);
agent_service.chat() delega siempre acá.

Reutiliza SIN reescribir:
  - Las tools de agent_tools.py (vía execute_tool) envueltas como @function_tool.
  - El system prompt TOOL_AGENT_SYSTEM y los bloques de context_blocks.py.
  - El análisis de lead transversal (lead_service.process_message_for_lead).
  - El catálogo de países disponibles (rag_service.vector_store).
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
    output_guardrail,
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
from app.services.rag_service import rag_service
from app.services.lead_service import lead_service
from app.services.agent_tools import execute_tool
from app.services.shared_sdk_tools import obtener_clima
from app.prompts.tool_agent_prompts import TOOL_AGENT_SYSTEM
from app.prompts.context_blocks import (
    build_lead_context_block,
    build_contact_request_block,
)

logger = get_logger(__name__)

MAX_TURNS = 6
MAX_HISTORY_MESSAGES = 20

# Cliente OpenAI compartido por el SDK (singleton del proyecto, ver core/openai_client).
_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
# Habilitar el export de trazas usando la misma API key del proyecto (las trazas
# quedan visibles en el dashboard de OpenAI). Evita el aviso "OPENAI_API_KEY is not set".
set_tracing_export_api_key(settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# CONTEXTO POR TURNO — se inyecta a las tools vía RunContextWrapper
# ---------------------------------------------------------------------------
class PreventaContext:
    """Contexto mutable de un turno; equivale al `ctx` dict del orquestador casero.

    Lleva db/message/history para las tools y recoge document_sources / relevance
    / event_info que el orquestador necesita para armar la respuesta final.
    """

    def __init__(self, db: Session, message: str, history: List[Dict]):
        self.db = db
        self.message = message
        self.history = history
        self.document_sources: List = []
        self.relevance_mode: Optional[str] = None
        self.event_info: Optional[Dict] = None
        self.available_countries: List[str] = []

    def as_tool_ctx(self) -> Dict:
        """Adapta a la forma de dict que esperan los handlers de agent_tools.execute_tool."""
        return {
            "db": self.db,
            "message": self.message,
            "history": self.history,
            "document_sources": self.document_sources,
            "relevance_mode": self.relevance_mode,
            "event_info": self.event_info,
        }

    def absorb(self, tool_ctx: Dict):
        """Recupera lo que las tools escribieron en el dict mutable."""
        self.document_sources = tool_ctx.get("document_sources", self.document_sources)
        self.relevance_mode = tool_ctx.get("relevance_mode", self.relevance_mode)
        self.event_info = tool_ctx.get("event_info", self.event_info)


# ---------------------------------------------------------------------------
# TOOLS — envuelven los handlers existentes de agent_tools.execute_tool
# ---------------------------------------------------------------------------
@function_tool
async def buscar_paquetes(ctx: RunContextWrapper[PreventaContext], query: str) -> str:
    """Busca paquetes turísticos en el catálogo según destino, continente, presupuesto
    o tipo de viaje. Úsala SIEMPRE que el usuario mencione un destino o tipo de viaje,
    incluso si creés que no hay paquete. Es la única fuente de paquetes y precios."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("buscar_paquetes", {"query": query}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


# obtener_clima vive en shared_sdk_tools.py (compartida con post-venta) — ver import arriba.


@function_tool
async def buscar_evento(ctx: RunContextWrapper[PreventaContext], query: str) -> str:
    """Detecta si la consulta es sobre un evento temporal (Mundial, F1, Olimpiadas,
    festivales). Úsala cuando el usuario menciona un evento así y no hay paquete específico.
    Devuelve los países relacionados para ofrecer alternativas."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("buscar_evento", {"query": query}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def identificar_contacto(
    ctx: RunContextWrapper[PreventaContext], telefono: str = "", email: str = ""
) -> str:
    """Busca si el usuario ya es un contacto conocido (lead o cliente previo) por su
    teléfono o email, para personalizar el trato. Usar solo si lo menciona explícitamente."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "identificar_contacto", {"telefono": telefono, "email": email}, tool_ctx
    )
    return result.get("tool_result", "")


_TOOLS = [buscar_paquetes, obtener_clima, buscar_evento, identificar_contacto]


# ---------------------------------------------------------------------------
# GUARDRAILS
# ---------------------------------------------------------------------------
# Output guardrail: detectar mención de países SIN oferta disponible.
# Formaliza _validate_response_countries (agent_service.py) como mecanismo del SDK.
# MONITOR (no guardrail de bloqueo): registra si la respuesta menciona países sin
# oferta. NO dispara tripwire a propósito — el agente menciona países no disponibles
# de forma LEGÍTIMA ("no tenemos Tíbet, pero te ofrezco India/Nepal"). Bloquear eso
# rompería respuestas correctas. Su valor es de OBSERVABILIDAD: el dato queda en el
# log y en el tracing del SDK para auditar si el agente alguna vez OFRECE un país
# inexistente (eso se detectaría revisando estos logs, no bloqueando en caliente).
@output_guardrail
async def paises_disponibles_monitor(
    ctx: RunContextWrapper[PreventaContext], agent: Agent, output: str
) -> GuardrailFunctionOutput:
    from app.core.geography import geography_service
    import re

    available = ctx.context.available_countries or []
    all_countries = geography_service.get_all_countries()
    unavailable = [c for c in all_countries if c not in available]

    out_lower = (output or "").lower()
    mentioned_unavailable = [
        c for c in unavailable
        if re.search(rf"\b{re.escape(c.lower())}\b", out_lower)
    ]

    if mentioned_unavailable:
        logger.info("Países monitor: respuesta menciona países sin oferta (esperado al "
                    "ofrecer alternativas)",
                    mentioned=mentioned_unavailable)

    # tripwire SIEMPRE False: es un monitor de observabilidad, no un control de bloqueo.
    return GuardrailFunctionOutput(
        output_info={"unavailable_countries_mentioned": mentioned_unavailable},
        tripwire_triggered=False,
    )


# Input guardrail: relevancia de dominio / anti-jailbreak básico.
# Patrón del openai-cs-agents-demo. Detecta intentos de exfiltrar el prompt.
#
# LIMITACIÓN CONOCIDA: es detección por substrings hardcodeados. Cubre los ataques
# más comunes y literales, pero NO detecta variaciones, paráfrasis ni jailbreaks en
# otros idiomas/ortografías ("ignor previo", "sys prompt", "olvidá todo lo anterior").
# Es suficiente para el alcance demo. Mejora futura (P-largo plazo): reemplazar por un
# clasificador ligero (gpt-4o-mini) que evalúe intención, no coincidencia textual.
# Defensa en profundidad: el system prompt ya instruye al agente a no revelar sus
# instrucciones, así que un bypass de esta lista no implica fuga automática del prompt.
_JAILBREAK_MARKERS = (
    "ignore previous", "ignora las instrucciones", "system prompt",
    "olvida tus instrucciones", "reveal your prompt", "actúa como",
)


@input_guardrail
async def relevancia_guardrail(
    ctx: RunContextWrapper[PreventaContext], agent: Agent, user_input
) -> GuardrailFunctionOutput:
    text = user_input if isinstance(user_input, str) else str(user_input)
    text_lower = text.lower()
    is_jailbreak = any(m in text_lower for m in _JAILBREAK_MARKERS)

    if is_jailbreak:
        logger.warning("Input guardrail: possible jailbreak attempt",
                       preview=text_lower[:80])

    return GuardrailFunctionOutput(
        output_info={"jailbreak_suspected": is_jailbreak},
        tripwire_triggered=is_jailbreak,
    )


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class AgentSDKOrchestrator:
    """Loop de tool calling de pre-venta sobre el OpenAI Agents SDK."""

    def __init__(self):
        # El modelo usa Chat Completions (consistente con el resto del proyecto)
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )
        # Tracing del SDK: activable. Por defecto seguimos el flag de debug del proyecto.
        if not settings.DEBUG:
            set_tracing_disabled(False)  # mantener trazas en consola/dashboard

    def _build_instructions(self, lead_block: str) -> str:
        now = now_argentina()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        hora = now.strftime("%H:%M")

        available = rag_service.vector_store.get_available_countries()
        countries_list = ", ".join(available) if available else "ninguno"

        return TOOL_AGENT_SYSTEM.format(
            agent_name=profile_manager.get_agent_name(),
            fecha_actual=fecha,
            hora_actual=hora,
            available_countries=countries_list,
            lead_block=lead_block,
        )

    async def _build_lead_block(
        self, db: Session, message: str, session_id: str, history: List[Dict]
    ) -> tuple[str, Dict, bool]:
        """Replica el análisis de lead del orquestador casero (agent_orchestrator._build_lead_block)."""
        lead = lead_service._get_or_create_lead(db, session_id)
        has_contact_info = lead.is_complete_lead()

        geo_analysis = rag_service.analyze_query_geography(message)
        lead_analysis, should_request_contact = await lead_service.process_message_for_lead(
            db, message, session_id, history, "", geo_analysis
        )

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
        elif should_request_contact:
            main_interest = lead_analysis.get("main_interest", "el destino consultado")
            lead_block = build_contact_request_block(main_interest)

        return lead_block, lead_analysis, should_request_contact

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        """Arma la lista de input para el Runner: historial reciente + mensaje actual."""
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(
        self, db: Session, message: str, session_id: str, history: List[Dict]
    ) -> Dict:
        """Procesa un turno de pre-venta con el SDK. Mismo contrato que AgentOrchestrator.run()."""
        start = time.time()

        # 1. Lead analysis transversal → bloque para el prompt
        lead_block, lead_analysis, should_request_contact = await self._build_lead_block(
            db, message, session_id, history
        )

        # 2. Construir el Agent con instrucciones, tools y guardrails
        instructions = self._build_instructions(lead_block)
        agent = Agent[PreventaContext](
            name=profile_manager.get_agent_name(),
            instructions=instructions,
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=settings.OPENAI_TEMPERATURE),
            input_guardrails=[relevancia_guardrail],
            output_guardrails=[paises_disponibles_monitor],
        )

        # 3. Contexto del turno (compartido con tools y guardrails)
        run_ctx = PreventaContext(db, message, history)
        run_ctx.available_countries = rag_service.vector_store.get_available_countries()

        input_list = self._build_input_list(history, message)

        # 4. Ejecutar el loop del SDK (maneja tool calling, iteraciones, respuesta final)
        from agents import (
            InputGuardrailTripwireTriggered,
            OutputGuardrailTripwireTriggered,
        )
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
            logger.warning("Pre-venta SDK: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte a encontrar tu próximo viaje. "
                "¿A qué destino te gustaría ir? ✈️"
            )
            tools_used = []
        except OutputGuardrailTripwireTriggered:
            logger.warning("Pre-venta SDK: output guardrail tripwire", session_id=session_id)
            response_text = (
                "Disculpá, déjame reformular eso. ¿Querés que te muestre los destinos "
                "que sí tenemos disponibles?"
            )
            tools_used = []
        except Exception as e:
            # Fallback genérico: error de OpenAI, tool, timeout o shape inesperado del SDK.
            # Evita propagar un 500 al usuario; degradamos a un mensaje amable.
            logger.error("Pre-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un problema procesando tu consulta. "
                "¿Podés intentarlo de nuevo en un momento?"
            )
            tools_used = []

        if not response_text:
            response_text = "Disculpá, no pude generar una respuesta. ¿Podés reformular tu consulta?"

        duration = time.time() - start
        logger.info("Pre-venta SDK turn completed",
                    session_id=session_id,
                    tools_used=tools_used,
                    duration=f"{duration:.2f}s")

        return {
            "response": response_text,
            "has_context": bool(run_ctx.document_sources),
            "document_sources": run_ctx.document_sources,
            "tools_used": tools_used,
            "processing_time": f"{duration:.2f}s",
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
agent_sdk_orchestrator = AgentSDKOrchestrator()
