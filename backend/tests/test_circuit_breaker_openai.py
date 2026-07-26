"""
Circuit breaker de OpenAI: que sea REAL, no decorativo (hallazgo C3).

Antes, `openai_circuit_breaker` existía pero no envolvía ninguna llamada: solo se leía para
mostrar estado en /health y el admin lo podía resetear. Si OpenAI se caía, cada turno esperaba
el timeout completo del SDK (y hasta 60s del wait_for de chat/whatsapp) y el health seguía
reportando "closed" mientras todo fallaba.

Ahora envuelve `Runner.run` dentro de `sdk_runtime.run_agent` — el único punto por donde pasan
las llamadas al LLM de los 4 agentes. Estos tests fijan el contrato:
  - N fallos de la API abren el circuito.
  - Con el circuito abierto se falla RÁPIDO (sin llegar a Runner.run).
  - Un error que NO es de la API (tripwire del guardrail, bug de código) no abre el circuito.
  - Pasado el timeout, el circuito se recupera (half-open → closed).
"""
from unittest.mock import AsyncMock, patch

import pytest
from openai import APIConnectionError

from app.core.agents import sdk_runtime
from app.core.llm.circuit_breaker import CircuitState, openai_circuit_breaker
from app.domains.hotel.agent_specs import SPECS
# El registro de tools ocurre por efecto lateral del import del orquestador (deuda I2):
# sin esto, resolve_tools falla con KeyError al construir el Agent.
import app.services.staff_orchestrator  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_breaker():
    """El breaker es un singleton global: se resetea entre tests para no filtrar estado."""
    openai_circuit_breaker.reset()
    yield
    openai_circuit_breaker.reset()


def _api_error() -> APIConnectionError:
    """Error REAL de la API de OpenAI (de los que deben abrir el circuito)."""
    return APIConnectionError(request=None)


async def _run_turn(fallback="fallback"):
    return await sdk_runtime.run_agent(
        SPECS["hotel_staff"], instructions="x", context=object(),
        input_list=[{"role": "user", "content": "hola"}], fallback_response=fallback,
    )


@pytest.mark.asyncio
async def test_fallos_de_api_abren_el_circuito():
    """Al llegar al umbral de fallos consecutivos, el circuito queda OPEN."""
    umbral = openai_circuit_breaker.failure_threshold
    with patch.object(sdk_runtime.Runner, "run", new=AsyncMock(side_effect=_api_error())):
        for _ in range(umbral):
            out = await _run_turn()
            assert out["error"] is True  # cada turno devuelve el fallback, sin propagar

    assert openai_circuit_breaker.state is CircuitState.OPEN, "el circuito debía abrirse"


@pytest.mark.asyncio
async def test_circuito_abierto_falla_rapido_sin_llamar_al_sdk():
    """Con el circuito abierto NO se invoca Runner.run: ese es todo el punto (fail-fast)."""
    umbral = openai_circuit_breaker.failure_threshold
    with patch.object(sdk_runtime.Runner, "run", new=AsyncMock(side_effect=_api_error())):
        for _ in range(umbral):
            await _run_turn()

    # Ahora el circuito está abierto: el siguiente turno no debe tocar el SDK.
    runner_spy = AsyncMock(side_effect=_api_error())
    with patch.object(sdk_runtime.Runner, "run", new=runner_spy):
        out = await _run_turn()

    assert out["error"] is True
    assert out["response"] == "fallback"
    assert runner_spy.await_count == 0, "con el circuito abierto no debe llamarse a Runner.run"


@pytest.mark.asyncio
async def test_un_error_que_no_es_de_la_api_no_abre_el_circuito():
    """Un bug de código (TypeError) no es una caída de OpenAI: no debe abrir el circuito."""
    umbral = openai_circuit_breaker.failure_threshold
    with patch.object(sdk_runtime.Runner, "run", new=AsyncMock(side_effect=TypeError("bug"))):
        for _ in range(umbral + 1):
            out = await _run_turn()
            assert out["error"] is True  # el fallback igual protege el turno

    assert openai_circuit_breaker.state is CircuitState.CLOSED, \
        "un error ajeno a la API no debe silenciar el servicio"


@pytest.mark.asyncio
async def test_turno_exitoso_resetea_el_contador():
    """Un éxito después de fallos parciales vuelve el contador a cero (no se acumula)."""
    with patch.object(sdk_runtime.Runner, "run", new=AsyncMock(side_effect=_api_error())):
        await _run_turn()
    assert openai_circuit_breaker.failure_count == 1

    ok = AsyncMock(return_value=type("R", (), {"final_output": "hola", "new_items": []})())
    with patch.object(sdk_runtime.Runner, "run", new=ok):
        out = await _run_turn()

    assert out["error"] is False
    assert openai_circuit_breaker.failure_count == 0
    assert openai_circuit_breaker.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_pasado_el_timeout_el_circuito_se_recupera():
    """Tras el timeout, el circuito pasa a HALF_OPEN y un éxito lo cierra."""
    from datetime import datetime, timedelta

    umbral = openai_circuit_breaker.failure_threshold
    with patch.object(sdk_runtime.Runner, "run", new=AsyncMock(side_effect=_api_error())):
        for _ in range(umbral):
            await _run_turn()
    assert openai_circuit_breaker.state is CircuitState.OPEN

    # Simular que ya pasó la ventana de timeout.
    openai_circuit_breaker.last_failure_time = (
        datetime.now() - timedelta(seconds=openai_circuit_breaker.timeout_seconds + 1)
    )

    ok = AsyncMock(return_value=type("R", (), {"final_output": "volvió", "new_items": []})())
    with patch.object(sdk_runtime.Runner, "run", new=ok):
        out = await _run_turn()

    assert out["error"] is False
    assert openai_circuit_breaker.state is CircuitState.CLOSED, "debía recuperarse tras el timeout"


def test_el_health_refleja_el_estado_real():
    """El estado que expone /health sale del mismo breaker que ahora envuelve las llamadas."""
    openai_circuit_breaker.reset()
    assert openai_circuit_breaker.get_state()["state"] == "closed"

    openai_circuit_breaker.state = CircuitState.OPEN
    assert openai_circuit_breaker.get_state()["state"] == "open"
