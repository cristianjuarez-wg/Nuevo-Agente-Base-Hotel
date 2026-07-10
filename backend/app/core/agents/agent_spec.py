"""
AgentSpec — definición DECLARATIVA de un agente (Fase 2.2).

Un agente deja de ser "un orquestador de ~800 líneas clonado" y pasa a ser una SPEC:
qué modelo usa, con qué temperatura, cuántos turnos, qué tools (por key del ToolRegistry),
qué guardrails y qué composer arma su prompt. El loop de ejecución es UNO solo
(core/agents/sdk_runtime.run_agent) para todos.

Las specs del dominio hotel viven en domains/hotel (agent_specs.py) como CÓDIGO — el
"cerebro no se muda": lo que el cliente configura son los BLOQUES que el composer inyecta
(tono, política, identidad, training), no la spec.
"""
from dataclasses import dataclass, field
from typing import Literal, Tuple


@dataclass(frozen=True)
class AgentSpec:
    key: str                          # "hotel_staff" | "hotel_owner" | "hotel_postsale" | "hotel_presale" | "casual" | "triage"
    display_name: str                 # nombre visible del Agent en el SDK ("Coordinador de Operaciones")
    display_role: str                 # "guest" | "management" | "staff" — mapea a agent_directory
    engine: Literal["sdk", "completions"] = "sdk"
    model_setting: str = "OPENAI_MODEL"       # nombre del atributo en settings
    temperature_setting: str = ""             # atributo en settings (prioridad sobre temperature)
    temperature: float = 0.3                  # usado si temperature_setting == ""
    max_turns: int = 6                        # solo engine="sdk"
    max_history: int = 20
    tools: Tuple[str, ...] = ()               # keys del ToolRegistry
    prompt_composer: str = ""                 # key del registro de composers
    input_guardrails: Tuple[str, ...] = ()    # keys del registro de guardrails
    channels: Tuple[str, ...] = ("web",)
    # True → el display_name sale del BusinessProfile/perfil (agentes "Aura"); False → fijo.
    name_from_profile: bool = False


def resolve_temperature(spec: AgentSpec, settings) -> float:
    """Temperatura efectiva: el setting nombrado (si hay) o el valor fijo de la spec."""
    if spec.temperature_setting:
        return float(getattr(settings, spec.temperature_setting))
    return spec.temperature


def resolve_model_name(spec: AgentSpec, settings) -> str:
    """Nombre del modelo desde settings (indirección por nombre, no hardcodeado)."""
    return str(getattr(settings, spec.model_setting))
