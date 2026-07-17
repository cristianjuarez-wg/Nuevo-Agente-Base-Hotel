"""Constantes compartidas para guardrails del agente.

Centraliza patrones/keywords que se usan en más de un orquestador para evitar
duplicaciones (causa raíz de bugs reincidentes) y facilitar su evolución.
"""

# Marcadores de intentos de jailbreak usados por el input guardrail del SDK.
# Son heurísticas por substring; a futuro pueden reemplazarse por un clasificador
# basado en modelo (más robusto contra variaciones y falsos positivos).
JAILBREAK_MARKERS = (
    "ignore previous", "ignora las instrucciones", "system prompt",
    "olvida tus instrucciones", "reveal your prompt", "actúa como",
)
