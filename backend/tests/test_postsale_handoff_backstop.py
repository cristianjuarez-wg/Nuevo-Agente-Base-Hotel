"""
Fase 1 (auditoría) — backstop determinístico de derivación a bandeja en post-venta.

Bug: el carril "derivar a la bandeja" (needs_human) dependía 100% de que el LLM llamara
`derivar_a_humano`. Si el análisis detecta que el huésped PIDE una persona (wants_human) pero
el LLM no llama la tool, el pedido no dejaba rastro. El código ahora lo respalda: marca
needs_human por su cuenta (igual que requires_escalation respalda el ticket).

Y usa el session_id VIVO (no booking.session_id): la marca cae en la conversación en curso.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.conversation import Conversation
from app.services import conversation_control_service as ctrl
from app.services import human_attention_service as has
import app.services.hotel_postsale_orchestrator as mod


def _run(coro):
    return asyncio.run(coro)


def _fake_run_agent_factory(wants_human: bool, called_tool: bool):
    """run_agent mock: setea escalation_analysis en el context (como haría analizar_escalacion)
    y reporta tools_used con o sin derivar_a_humano."""
    async def _fake(spec, *, instructions, context, input_list, display_name):
        context.escalation_analysis = {
            "requires_escalation": False, "urgency_level": "baja",
            "escalation_reason": "el huésped pide una persona", "category": "general",
            "wants_human": wants_human,
        }
        tools = ["analizar_escalacion"] + (["derivar_a_humano"] if called_tool else [])
        return {"response": "ok", "tools_used": tools, "result": MagicMock(),
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": "m"}}
    return _fake


def _invoke(db, session_id, *, wants_human, called_tool):
    orch = mod.hotel_postsale_sdk_orchestrator
    service = MagicMock()
    service.db = db
    booking = MagicMock()
    booking.session_id = "OTRA-sesion-del-booking"  # distinta a la viva → prueba el fix de session_id
    booking.contact_id = None
    ticket = MagicMock()
    ticket.status = "open"
    with patch("app.core.agents.sdk_runtime.run_agent",
               new=_fake_run_agent_factory(wants_human, called_tool)), \
         patch.object(orch, "_build_instructions", return_value="INSTR"), \
         patch("app.core.observability.audit_log.build_tool_trace", return_value=[]):
        return _run(orch.run(service, booking, ticket, "quiero hablar con una persona",
                             session_id, []))


def test_backstop_marca_needs_human_si_wants_human_y_no_llamo_la_tool(db):
    has.update_config(db, {"enabled": False, "on_call": False})  # deferred
    sid = "web-backstop-1"
    db.add(Conversation(session_id=sid, channel="web")); db.commit()

    _invoke(db, sid, wants_human=True, called_tool=False)  # LLM NO llamó la tool

    state = ctrl.get_needs_human(db, sid)
    assert state and state["active"], "el backstop debía marcar needs_human"
    assert state["status"] == "deferred"
    # Cayó en la sesión VIVA, no en booking.session_id.
    assert ctrl.get_needs_human(db, "OTRA-sesion-del-booking") is None


def test_no_backstop_si_el_llm_ya_llamo_la_tool(db):
    # Si el LLM llamó derivar_a_humano, el handler ya marcó; el backstop no debe duplicar
    # (acá el handler real no corre porque run_agent está mockeado, así que solo verificamos
    # que el backstop NO marca de más cuando la tool figura en tools_used).
    has.update_config(db, {"enabled": False, "on_call": False})
    sid = "web-backstop-2"
    db.add(Conversation(session_id=sid, channel="web")); db.commit()

    _invoke(db, sid, wants_human=True, called_tool=True)  # LLM SÍ llamó la tool

    # El backstop se abstiene (derivar_a_humano ∈ tools_used); el handler real lo habría marcado
    # en producción, pero acá está mockeado → no debe haber marca puesta por el backstop.
    assert ctrl.get_needs_human(db, sid) is None


def test_no_backstop_si_no_hay_wants_human(db):
    has.update_config(db, {"enabled": False, "on_call": False})
    sid = "web-backstop-3"
    db.add(Conversation(session_id=sid, channel="web")); db.commit()

    _invoke(db, sid, wants_human=False, called_tool=False)  # consulta normal, no pide persona

    assert ctrl.get_needs_human(db, sid) is None
