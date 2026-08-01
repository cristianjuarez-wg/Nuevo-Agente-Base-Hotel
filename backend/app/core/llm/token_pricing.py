"""
Precios de tokens de OpenAI → cálculo de costo en USD.

⚠️ Estos precios son una ESTIMACIÓN local y deben actualizarse si OpenAI cambia
sus tarifas. Precios expresados en USD por 1.000.000 (1M) de tokens.
Fuente de referencia: https://openai.com/api/pricing/

Si un modelo no está en la tabla, se usa el fallback de `gpt-4o` (conservador,
para no subestimar el gasto).
"""
from typing import Dict

# USD por 1M tokens: (input, output).
#
# ATENCIÓN al orden de las claves más específicas: el match por prefijo (ver
# _rates_for) recorre este dict, así que "gpt-5-mini" DEBE ir antes que "gpt-5",
# o "gpt-5-mini" matchearía contra "gpt-5" y se facturaría 5x de más.
_PRICE_PER_1M: Dict[str, tuple[float, float]] = {
    # Familia GPT-5 (de más específico a más genérico).
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5": (1.25, 10.00),
    # Familia GPT-4.
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # Embeddings: solo "input"; el output se considera 0.
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}

_FALLBACK_MODEL = "gpt-4o"


def _rates_for(model: str | None) -> tuple[float, float]:
    """Devuelve (precio_input, precio_output) por 1M tokens para el modelo dado."""
    if not model:
        return _PRICE_PER_1M[_FALLBACK_MODEL]
    # Match exacto o por prefijo (ej. "gpt-4o-2024-08-06" → "gpt-4o").
    if model in _PRICE_PER_1M:
        return _PRICE_PER_1M[model]
    # Gana el prefijo MÁS LARGO, no el primero del dict: "gpt-5-mini-2025-08-07"
    # matchea contra "gpt-5-mini" y no contra "gpt-5" (que costaría 5x más).
    matches = [k for k in _PRICE_PER_1M if model.startswith(k)]
    if matches:
        return _PRICE_PER_1M[max(matches, key=len)]
    return _PRICE_PER_1M[_FALLBACK_MODEL]


def cost_usd(model: str | None, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """
    Costo en USD de un uso de tokens.

    Si no se conoce el desglose input/output (input_tokens=0), pasar todo el
    consumo como `output_tokens` sobreestima; preferir pasar el total como
    `input_tokens` para una estimación conservadora-media. El llamador decide.
    """
    in_rate, out_rate = _rates_for(model)
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def cost_usd_from_total(model: str | None, total_tokens: int) -> float:
    """
    Costo aproximado cuando solo se tiene `total_tokens` (sin desglose).
    Usa el promedio de las tarifas input/output del modelo como estimación.
    """
    in_rate, out_rate = _rates_for(model)
    avg_rate = (in_rate + out_rate) / 2
    return (total_tokens / 1_000_000) * avg_rate
