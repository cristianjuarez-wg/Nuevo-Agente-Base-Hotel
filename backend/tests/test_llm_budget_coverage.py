"""
Cobertura del piso de tokens: que NINGÚN camino esquive `model_compat`.

Contexto (medido, no teórico): en la familia GPT-5 los tokens de razonamiento
salen del mismo presupuesto que la respuesta y se consumen primero. Un
presupuesto calibrado para GPT-4 (10..600 tokens en este proyecto) se agota
razonando y devuelve contenido VACÍO -> `json.loads("")` -> el `except` del
llamador. En `hotel_postsale` ese fail-safe ESCALA por seguridad, así que el
agente derivaba a un humano en vez de registrar el pedido del huésped.

`adapt_params` aplica un piso, pero solo protege lo que pasa por los clientes
compartidos de `openai_client`. Estos tests son el guardarraíl arquitectónico:
si alguien crea un cliente propio, el tráfico deja de estar protegido y el bug
vuelve en silencio (sin excepción, sin test rojo — solo el agente portándose
distinto en producción).
"""
import re
from pathlib import Path

import pytest

from app.core.llm.model_compat import RESTRICTED_MIN_COMPLETION_TOKENS, adapt_params

BACKEND = Path(__file__).resolve().parent.parent
SCANNED = [BACKEND / "app", BACKEND / "evals"]


def _python_files():
    for root in SCANNED:
        for path in root.rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


class TestNingunClientePropio:
    """El piso vive en openai_client; un cliente propio lo saltearía."""

    def test_no_hay_clientes_openai_fuera_del_modulo_compartido(self):
        offenders = []
        for path in _python_files():
            if path.name == "openai_client.py":
                continue  # el único autorizado a construir clientes
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"^\s*\w*\s*=?\s*(Async)?OpenAI\(", text, re.M):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(BACKEND)}:{line}")
        assert not offenders, (
            "Clientes OpenAI creados fuera de app/core/llm/openai_client.py: "
            f"{offenders}. Ese tráfico NO pasa por adapt_params, así que en GPT-5 "
            "se queda sin el piso de tokens. Usá get_async_openai()/get_sync_openai()."
        )


class TestPresupuestosRealesDelCodigo:
    """Todo `max_tokens=N` literal del repo debe sobrevivir la traducción."""

    def _budgets(self):
        for path in _python_files():
            if path.name in ("model_compat.py", "test_llm_budget_coverage.py"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"max_tokens\s*=\s*(\d+)", text):
                line = text[: match.start()].count("\n") + 1
                yield f"{path.relative_to(BACKEND)}:{line}", int(match.group(1))

    def test_hay_presupuestos_para_revisar(self):
        """Si esto falla, el scanner se rompió y los demás tests son vacíos."""
        assert list(self._budgets()), "El scanner no encontró ningún max_tokens"

    def test_todo_presupuesto_queda_sobre_el_piso_en_gpt5(self):
        ahogados = [
            f"{where} (max_tokens={budget})"
            for where, budget in self._budgets()
            if adapt_params("gpt-5-mini", {"max_tokens": budget})["max_completion_tokens"]
            < RESTRICTED_MIN_COMPLETION_TOKENS
        ]
        assert not ahogados, (
            f"Presupuestos que quedarían ahogados en GPT-5: {ahogados}"
        )

    def test_gpt4_conserva_todos_los_presupuestos_intactos(self):
        """El camino de producción no cambia de comportamiento."""
        for where, budget in self._budgets():
            out = adapt_params("gpt-4o", {"max_tokens": budget})
            assert out["max_tokens"] == budget, f"{where} cambió en gpt-4o"


class TestParseoDeJsonDelLlm:
    """Todo parseo de JSON del LLM necesita red: la respuesta puede venir vacía."""

    # Sitios que hacen json.loads sobre una respuesta del modelo.
    PARSERS = [
        "app/services/hotel_postsale.py",
        "app/services/event_detector.py",
        "app/services/severity_classifier.py",
        "app/services/lead_service.py",
        "app/services/training_service.py",
        "app/core/rag/knowledge_extractor.py",
        "app/core/rag/llm_metadata_extractor.py",
        "app/services/escalation_analyzer.py",
        "app/services/lead_analyzer.py",
    ]

    @pytest.mark.parametrize("relpath", PARSERS)
    def test_el_parseo_esta_protegido_por_try_except(self, relpath):
        text = (BACKEND / relpath).read_text(encoding="utf-8", errors="ignore")
        assert "json.loads" in text, f"{relpath}: cambió el parseo, revisar este test"
        assert "except" in text, (
            f"{relpath}: parsea JSON del LLM sin try/except. Si el modelo devuelve "
            "contenido vacío (presupuesto agotado, filtro de contenido), esto revienta "
            "en la cara del huésped en vez de degradar."
        )
