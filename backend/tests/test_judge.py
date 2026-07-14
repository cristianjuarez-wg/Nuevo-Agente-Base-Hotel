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


# ── Naturalidad (Fase 3): tests deterministas del Verdict, SIN LLM (corren siempre) ──

def test_verdict_naturalidad_ok_helper():
    """naturalidad_ok(): True si todas las señales presentes están en verde; vacío = True."""
    from evals.judge import Verdict
    assert Verdict(naturalidad={}).naturalidad_ok() is True
    assert Verdict(naturalidad={"sin_muletillas_bot": True, "vario_cierres": True}).naturalidad_ok() is True
    assert Verdict(naturalidad={"sin_muletillas_bot": True, "vario_cierres": False}).naturalidad_ok() is False


def test_naturalidad_no_afecta_el_veredicto_ok():
    """La naturalidad es MÉTRICA reportada: mal tono NO tumba `ok` (que mira invenciones + reglas)."""
    from evals.judge import Verdict
    # ok se computa en judge_transcript; acá emulamos su regla para blindar el contrato:
    v = Verdict(invented_facts=[], rules_respected={"no_inventa_precio": True},
                naturalidad={"vario_cierres": False, "sin_muletillas_bot": False})
    reglas_ok = all(bool(x) for x in v.rules_respected.values())
    ok = (len(v.invented_facts) == 0) and reglas_ok
    assert ok is True, "el estilo (naturalidad) no debe afectar la correctitud (ok)"
    assert v.naturalidad_ok() is False, "pero la métrica de naturalidad sí refleja el mal tono"


def test_verdict_to_dict_incluye_naturalidad():
    from evals.judge import Verdict
    d = Verdict(naturalidad={"sin_muletillas_bot": True}).to_dict()
    assert "naturalidad" in d and d["naturalidad"] == {"sin_muletillas_bot": True}


# ── Coherencia (Fase 5): tests deterministas, SIN LLM ──

def test_verdict_coherencia_ok_helper():
    from evals.judge import Verdict
    assert Verdict(coherencia={}).coherencia_ok() is True
    assert Verdict(coherencia={"mantuvo_el_hilo": True, "sin_respuesta_muda": True}).coherencia_ok() is True
    assert Verdict(coherencia={"mantuvo_el_hilo": False}).coherencia_ok() is False


def test_coherencia_no_afecta_el_veredicto_ok():
    """La coherencia es MÉTRICA reportada: perderse NO tumba `ok` (invenciones + reglas duras)."""
    from evals.judge import Verdict
    v = Verdict(invented_facts=[], rules_respected={"no_inventa_precio": True},
                coherencia={"mantuvo_el_hilo": False, "sin_respuesta_muda": False})
    reglas_ok = all(bool(x) for x in v.rules_respected.values())
    ok = (len(v.invented_facts) == 0) and reglas_ok
    assert ok is True
    assert v.coherencia_ok() is False


def test_verdict_to_dict_incluye_coherencia():
    from evals.judge import Verdict
    d = Verdict(coherencia={"mantuvo_el_hilo": True}).to_dict()
    assert "coherencia" in d and d["coherencia"] == {"mantuvo_el_hilo": True}
