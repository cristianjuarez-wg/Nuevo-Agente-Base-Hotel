"""
Compatibilidad de parámetros entre familias de modelos de OpenAI.

PROBLEMA
--------
La familia GPT-5 (y los modelos de razonamiento o1/o3) NO acepta los mismos
parámetros que GPT-4:

    temperature=0.3   -> 400 "Only the default (1) value is supported"
    max_tokens=150    -> 400 "Use 'max_completion_tokens' instead"

El código tiene ~27 sitios con `temperature=` y ~15 con `max_tokens=`. Editarlos
uno por uno haría que cambiar de familia vuelva a ser una cacería. En su lugar,
la regla vive ACÁ y se aplica en un único punto de paso (openai_client), de modo
que migrar de modelo sea cambiar OPENAI_MODEL en el .env y nada más.

CRITERIO
--------
No se mantiene una lista blanca de modelos (envejece mal: gpt-5.4, gpt-5.6-luna,
lo que venga). Se decide por familia a partir del prefijo del nombre, que es lo
único estable que publica OpenAI.
"""
from typing import Any, Dict

# Familias que rechazan `temperature` != 1 y exigen `max_completion_tokens`.
# Prefijos, no nombres exactos: cubre gpt-5, gpt-5-mini, gpt-5.4-nano, o1-preview…
_RESTRICTED_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def is_restricted_family(model: str | None) -> bool:
    """True si el modelo pertenece a una familia con parámetros restringidos.

    Se usa también desde sdk_runtime para decidir si mandar ModelSettings con
    temperature o sin ella.
    """
    if not model:
        return False
    m = model.strip().lower()
    return any(m.startswith(p) for p in _RESTRICTED_PREFIXES)


def adapt_params(model: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve una copia de `params` compatible con la familia de `model`.

    - temperature: se ELIMINA si el modelo no la soporta. No se fuerza a 1.0
      porque 1.0 ya es el default del servidor; mandarlo explícito no aporta y
      solo agrega superficie de error si mañana también lo rechazan.
    - max_tokens -> max_completion_tokens (sin pisar uno ya presente).
    - top_p / frequency_penalty / presence_penalty: mismo tratamiento que
      temperature (la familia restringida también los rechaza).

    Para un modelo GPT-4 devuelve los params intactos: el camino viejo no cambia
    de comportamiento.
    """
    if not is_restricted_family(model):
        return params

    out = dict(params)

    for unsupported in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
        out.pop(unsupported, None)

    if "max_tokens" in out:
        value = out.pop("max_tokens")
        # Si el llamador ya especificó el nombre nuevo, respetarlo.
        out.setdefault("max_completion_tokens", value)

    return out


def ensure_json_hint(model: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
    """Garantiza el requisito de `response_format={"type": "json_object"}`.

    La API exige que la palabra "json" aparezca en los mensajes cuando se pide
    json_object; si no, devuelve 400. Varios prompts del proyecto lo cumplen por
    casualidad (dicen "JSON" en el texto), pero no todos, y no queremos que la
    migración dependa de eso.

    Si falta, se inyecta una línea mínima en el mensaje `system` (o se crea uno).
    No altera la semántica del prompt: solo declara el formato de salida.
    """
    fmt = (params.get("response_format") or {})
    if fmt.get("type") != "json_object":
        return params

    messages = params.get("messages") or []
    if any("json" in str(m.get("content", "")).lower() for m in messages):
        return params

    out = dict(params)
    msgs = [dict(m) for m in messages]
    hint = "Respondé exclusivamente con un objeto JSON válido."
    for m in msgs:
        if m.get("role") == "system":
            m["content"] = f"{m.get('content', '')}\n\n{hint}".strip()
            break
    else:
        msgs.insert(0, {"role": "system", "content": hint})
    out["messages"] = msgs
    return out
