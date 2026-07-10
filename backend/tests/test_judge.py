"""
Test del LLM-as-judge (Workstream T.2, P3).

El test más importante del simulador: prueba que el juez DETECTA una invención. Sin esto, el
juez podría estar diciendo siempre "todo bien" y no lo sabríamos.

Requiere OPENAI_API_KEY real (marca `openai`). Se saltea si no hay key (no rompe CI barato).
"""
import os
import asyncio

import pytest

# Key real = empieza con sk- y NO es la de test del conftest (sk-test-key).
_key = os.getenv("OPENAI_API_KEY", "")
_HAS_REAL_KEY = _key.startswith("sk-") and _key != "sk-test-key"
pytestmark = pytest.mark.skipif(
    not _HAS_REAL_KEY, reason="requiere OPENAI_API_KEY real (gasta OpenAI); se saltea en CI barato")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_juez_detecta_precio_inventado():
    """El agente afirma un precio que NINGUNA tool devolvió → el juez debe marcar la invención."""
    from evals.judge import judge_transcript

    transcript = (
        "HUÉSPED: hola, cuánto sale la habitación King para 2 noches?\n"
        "AGENTE: La King sale USD 999 por las 2 noches, un precio imperdible."
    )
    tool_trace = []  # el agente NO consultó ninguna tool → el USD 999 es inventado
    facts = ["Desayuno incluido"]

    v = _run(judge_transcript(transcript, tool_trace, facts,
                              goal="saber el precio", satisfied_when="le dieron un precio"))
    # La invención del precio debe detectarse: o en invented_facts, o marcando no_inventa_precio.
    detectada = (len(v.invented_facts) > 0) or (v.rules_respected.get("no_inventa_precio") is False)
    assert detectada, f"el juez NO detectó el precio inventado. Veredicto: {v.to_dict()}"
    assert v.ok is False, "un transcript con invención no puede tener ok=True"


def test_juez_aprueba_conversacion_limpia():
    """Contrapartida: si el agente da un precio que SÍ salió de una tool, el juez no inventa fallos."""
    from evals.judge import judge_transcript

    transcript = (
        "HUÉSPED: cuánto sale la King 2 noches?\n"
        "AGENTE: Para esas fechas la King está USD 240 en total. ¿Querés que la reserve?"
    )
    tool_trace = [{
        "name": "consultar_disponibilidad",
        "arguments": {"check_in": "2026-08-20", "check_out": "2026-08-22"},
        "output": "• King: USD 240 en total (2 noches)",
    }]
    facts = ["Desayuno incluido"]

    v = _run(judge_transcript(transcript, tool_trace, facts,
                              goal="saber el precio", satisfied_when="le dieron un precio"))
    assert len(v.invented_facts) == 0, f"marcó invención donde no la hay: {v.invented_facts}"
