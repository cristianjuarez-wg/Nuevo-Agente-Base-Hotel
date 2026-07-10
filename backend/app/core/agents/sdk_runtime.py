"""
Runtime GENÉRICO de agentes sobre el OpenAI Agents SDK (Fase 2.2).

Un solo loop de ejecución para todos los agentes declarados por AgentSpec:
  1. Construye el Agent (modelo/temperatura/tools/guardrails desde la spec).
  2. Runner.run(max_turns de la spec).
  3. Extrae response / tools_used / usage (el contrato común de los orquestadores).
  4. Catch genérico anti-500: si el Runner revienta y la spec trae fallback, devuelve el
     fallback amable en vez de propagar (portado tal cual de los orquestadores).

Lo que NO hace (queda en el orquestador fino de cada dominio): post-procesamiento de
dominio (acciones sobre tickets, flags de disponibilidad, charts), manejo del tripwire de
guardrails con respuesta propia, y la composición del prompt (composer del dominio).
"""
import time
from typing import Dict, List, Optional

from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner

from app.config import settings
from app.core.llm.openai_client import get_async_openai
from app.core.llm.sdk_usage import extract_usage
from app.core.observability.logging_config import get_logger
from app.core.agents.agent_spec import AgentSpec, resolve_model_name, resolve_temperature
from app.core.agents.tool_registry import resolve_tools, resolve_guardrails

logger = get_logger(__name__)

_sdk_client = get_async_openai()


def extract_tools_used(result) -> List[str]:
    """Nombres de las tools llamadas en el run (contrato común de los orquestadores)."""
    return [
        item.raw_item.name
        for item in getattr(result, "new_items", [])
        if getattr(item, "type", None) == "tool_call_item"
        and hasattr(getattr(item, "raw_item", None), "name")
    ]


async def run_agent(
    spec: AgentSpec,
    *,
    instructions: str,
    context,
    input_list: List[Dict],
    display_name: Optional[str] = None,
    fallback_response: Optional[str] = None,
    tools_override: Optional[list] = None,
) -> Dict:
    """Ejecuta un turno del agente declarado por `spec`.

    Returns:
        {"response", "tools_used", "usage", "result", "error"} — `result` es el objeto
        crudo del Runner (None si falló), para que el orquestador de dominio extraiga
        extras (p.ej. escalation analysis del contexto). `error` True si hubo excepción
        y se devolvió el fallback.

    Raises:
        Si NO se pasa `fallback_response`, las excepciones del Runner se PROPAGAN
        (incluye InputGuardrailTripwireTriggered): el orquestador decide qué hacer.
    """
    model_name = resolve_model_name(spec, settings)
    # tools_override: para agentes cuya lista se FILTRA por sesión (config del Centro,
    # ej. pre-venta con filter_tools_for_session). La spec declara el catálogo completo;
    # el override aplica el subconjunto habilitado en esta sesión.
    agent = Agent(
        name=display_name or spec.display_name,
        instructions=instructions,
        tools=tools_override if tools_override is not None else resolve_tools(spec.tools),
        model=OpenAIChatCompletionsModel(model=model_name, openai_client=_sdk_client),
        model_settings=ModelSettings(temperature=resolve_temperature(spec, settings)),
        input_guardrails=resolve_guardrails(spec.input_guardrails),
    )

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": model_name}
    start = time.time()
    try:
        result = await Runner.run(agent, input=input_list, context=context, max_turns=spec.max_turns)
        usage = extract_usage(result, model=model_name)
        out = {
            "response": result.final_output or "",
            "tools_used": extract_tools_used(result),
            "usage": usage,
            "result": result,
            "agent_key": spec.key,  # observabilidad (3.4): qué agente respondió
            "error": False,
        }
    except Exception as e:  # noqa: BLE001 — anti-500 si hay fallback; si no, propaga
        if fallback_response is None:
            raise
        logger.error("Agent runtime: Runner failed",
                     agent=spec.key, error=str(e), error_type=type(e).__name__)
        out = {
            "response": fallback_response,
            "tools_used": [],
            "usage": usage,
            "result": None,
            "agent_key": spec.key,  # observabilidad (3.4)
            "error": True,
        }

    logger.info("Agent runtime turn completed",
                agent=spec.key, tools_used=out["tools_used"],
                duration=f"{time.time() - start:.2f}s")
    return out


def build_input_list(history: List[Dict], message: str, max_history: int) -> List[Dict]:
    """Ventana de historial + mensaje actual (contrato común de los orquestadores)."""
    recent = history[-max_history:] if len(history) > max_history else history
    items = [{"role": m["role"], "content": m["content"]} for m in recent]
    items.append({"role": "user", "content": message})
    return items
