"""
Extracción defensiva de tokens usados de un resultado del Agents SDK.

El SDK expone el consumo en `result.context_wrapper.usage` (objeto Usage con
`input_tokens`, `output_tokens`, `total_tokens`). En ramas de guardrail o
excepción puede no existir, por lo que toda la lectura es defensiva: si algo
falla, se devuelve un dict de ceros y el chat sigue funcionando.
"""
from typing import Dict, Optional

from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


def extract_usage(result, model: Optional[str] = None) -> Dict:
    """Devuelve {input_tokens, output_tokens, total_tokens, model} desde un RunResult."""
    info = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": model}
    try:
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        if usage is not None:
            info["input_tokens"] = int(getattr(usage, "input_tokens", 0) or 0)
            info["output_tokens"] = int(getattr(usage, "output_tokens", 0) or 0)
            total = getattr(usage, "total_tokens", 0) or 0
            info["total_tokens"] = int(total) or (info["input_tokens"] + info["output_tokens"])
    except Exception as e:
        logger.debug("Could not extract SDK usage", error=str(e))
    return info


def usage_from_completion(response, model: Optional[str] = None) -> Dict:
    """Igual que extract_usage pero para una respuesta de chat.completions.create."""
    info = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": model}
    try:
        usage = getattr(response, "usage", None)
        if usage is not None:
            info["input_tokens"] = int(getattr(usage, "prompt_tokens", 0) or 0)
            info["output_tokens"] = int(getattr(usage, "completion_tokens", 0) or 0)
            total = getattr(usage, "total_tokens", 0) or 0
            info["total_tokens"] = int(total) or (info["input_tokens"] + info["output_tokens"])
    except Exception as e:
        logger.debug("Could not extract completion usage", error=str(e))
    return info
