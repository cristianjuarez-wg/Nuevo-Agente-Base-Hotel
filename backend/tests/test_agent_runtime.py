"""
Fase 2.2 — runtime declarativo de agentes (core/agents).

Verifica, sin gastar OpenAI (Runner mockeado):
  - run_agent extrae response/tools_used/usage del resultado del SDK.
  - El fallback anti-500 devuelve el texto amable (sin propagar) y marca error=True.
  - Sin fallback, la excepción PROPAGA (el orquestador decide).
  - Las specs del hotel replican los parámetros históricos (paridad).
  - El staff orchestrator migrado conserva su contrato {response, tools_used, usage}.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.agents.agent_spec import AgentSpec, resolve_temperature, resolve_model_name
from app.config import settings


def _spec(**kw):
    base = dict(key="t", display_name="T", display_role="staff", tools=(), prompt_composer="x")
    base.update(kw)
    return AgentSpec(**base)


# ── AgentSpec ────────────────────────────────────────────────────────────────

def test_temperatura_por_setting_tiene_prioridad():
    s = _spec(temperature=0.9, temperature_setting="OPENAI_TEMPERATURE")
    assert resolve_temperature(s, settings) == settings.OPENAI_TEMPERATURE
    s2 = _spec(temperature=0.4)
    assert resolve_temperature(s2, settings) == 0.4


def test_modelo_por_nombre_de_setting():
    s = _spec(model_setting="OPENAI_MODEL_CLASSIFIER")
    assert resolve_model_name(s, settings) == settings.OPENAI_MODEL_CLASSIFIER


# ── Paridad de las specs del hotel con los valores históricos ────────────────

def test_specs_hotel_paridad_historica():
    from app.domains.hotel.agent_specs import SPECS
    st = SPECS["hotel_staff"]
    assert (st.max_turns, st.max_history, st.temperature) == (5, 10, 0.4)
    assert st.tools == ("staff.resolver_ticket", "staff.reportar_incidencia", "staff.mis_tickets")
    ow = SPECS["hotel_owner"]
    assert (ow.max_turns, ow.max_history, ow.temperature_setting) == (6, 20, "OPENAI_TEMPERATURE")
    po = SPECS["hotel_postsale"]
    assert (po.max_turns, po.max_history, po.temperature) == (5, 8, 0.7)
    pr = SPECS["hotel_presale"]
    assert (pr.max_turns, pr.max_history, pr.temperature_setting) == (6, 20, "OPENAI_TEMPERATURE")


# ── run_agent ────────────────────────────────────────────────────────────────

def _fake_result(text="hola", tool_names=()):
    result = MagicMock()
    result.final_output = text
    items = []
    for n in tool_names:
        it = MagicMock()
        it.type = "tool_call_item"
        it.raw_item.name = n
        items.append(it)
    result.new_items = items
    return result


@pytest.mark.asyncio
async def test_run_agent_extrae_contrato_comun():
    import app.core.agents.sdk_runtime as rt
    # tools del staff ya registradas (importar el orquestador las registra)
    import app.services.staff_orchestrator  # noqa: F401

    from app.domains.hotel.agent_specs import SPECS
    spec = SPECS["hotel_staff"]

    with patch.object(rt.Runner, "run", new=AsyncMock(return_value=_fake_result("listo", ["resolver_ticket"]))):
        out = await rt.run_agent(spec, instructions="X", context=MagicMock(), input_list=[])

    assert out["response"] == "listo"
    assert out["tools_used"] == ["resolver_ticket"]
    assert out["error"] is False
    assert "total_tokens" in out["usage"]


@pytest.mark.asyncio
async def test_run_agent_fallback_anti_500():
    import app.core.agents.sdk_runtime as rt
    import app.services.staff_orchestrator  # noqa: F401
    from app.domains.hotel.agent_specs import SPECS

    with patch.object(rt.Runner, "run", new=AsyncMock(side_effect=RuntimeError("OpenAI 500"))):
        out = await rt.run_agent(SPECS["hotel_staff"], instructions="X", context=MagicMock(),
                                 input_list=[], fallback_response="disculpá, problema")
    assert out["response"] == "disculpá, problema"
    assert out["error"] is True and out["tools_used"] == []


@pytest.mark.asyncio
async def test_run_agent_sin_fallback_propaga():
    import app.core.agents.sdk_runtime as rt
    import app.services.staff_orchestrator  # noqa: F401
    from app.domains.hotel.agent_specs import SPECS

    with patch.object(rt.Runner, "run", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError):
            await rt.run_agent(SPECS["hotel_staff"], instructions="X", context=MagicMock(), input_list=[])


# ── Staff migrado: conserva su contrato ──────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_orchestrator_contrato_intacto():
    import app.core.agents.sdk_runtime as rt
    from app.services.staff_orchestrator import staff_orchestrator

    staff = MagicMock()
    staff.name = "Diego"
    staff.area = "mantenimiento"

    with patch.object(rt.Runner, "run", new=AsyncMock(return_value=_fake_result("Listo, marcado 👍", ["resolver_ticket"]))), \
         patch.object(staff_orchestrator, "_build_instructions", return_value="INSTR"), \
         patch.object(staff_orchestrator, "_pending_summary", return_value="-"):
        out = await staff_orchestrator.run(MagicMock(), staff, "reparé el aire", "staff_123", [])

    assert set(out.keys()) == {"response", "tools_used", "usage"}
    assert out["response"] == "Listo, marcado 👍"
    assert out["tools_used"] == ["resolver_ticket"]
