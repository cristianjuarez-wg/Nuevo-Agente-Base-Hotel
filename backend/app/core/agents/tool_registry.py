"""
Registros del runtime declarativo (Fase 2.2): tools, composers y guardrails.

- TOOLS: cada @function_tool del dominio se registra con una key estable
  (register_tool). La spec referencia tools por key; el runtime las resuelve.
- COMPOSERS: funciones que arman las instrucciones (system prompt) de un agente.
  Firma: (db, spec, **ctx) -> str. Encapsulan lo que hoy hace _build_instructions
  de cada orquestador. Viven en el dominio (domains/hotel/.../composers).
- GUARDRAILS: input guardrails del SDK, por key.

El registro es global de proceso e idempotente (re-registrar la misma key pisa el valor,
útil en tests con reimports).
"""
from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolDef:
    key: str
    fn: Callable           # la función YA decorada con @function_tool
    description: str = ""


_TOOLS: Dict[str, ToolDef] = {}
_COMPOSERS: Dict[str, Callable] = {}
_GUARDRAILS: Dict[str, object] = {}


# ── Tools ─────────────────────────────────────────────────────────────────────
def register_tool(key: str, fn: Callable, description: str = "") -> Callable:
    """Registra una tool (ya decorada con @function_tool) bajo una key estable."""
    _TOOLS[key] = ToolDef(key=key, fn=fn, description=description)
    return fn


def resolve_tools(keys: Tuple[str, ...]) -> list:
    """Resuelve keys → funciones tool. KeyError explícito si falta una (fail-fast)."""
    missing = [k for k in keys if k not in _TOOLS]
    if missing:
        raise KeyError(f"Tools no registradas: {missing}. ¿Falta importar el módulo que las registra?")
    return [_TOOLS[k].fn for k in keys]


def registered_tools() -> Dict[str, ToolDef]:
    return dict(_TOOLS)


# ── Composers ────────────────────────────────────────────────────────────────
def register_composer(key: str, fn: Callable) -> Callable:
    _COMPOSERS[key] = fn
    return fn


def resolve_composer(key: str) -> Callable:
    if key not in _COMPOSERS:
        raise KeyError(f"Composer no registrado: {key!r}")
    return _COMPOSERS[key]


# ── Guardrails ───────────────────────────────────────────────────────────────
def register_guardrail(key: str, guardrail: object) -> object:
    _GUARDRAILS[key] = guardrail
    return guardrail


def resolve_guardrails(keys: Tuple[str, ...]) -> list:
    missing = [k for k in keys if k not in _GUARDRAILS]
    if missing:
        raise KeyError(f"Guardrails no registrados: {missing}")
    return [_GUARDRAILS[k] for k in keys]
