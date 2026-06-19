"""
Tests unitarios de la LÓGICA del agente (sin llamar a OpenAI real).

Cubren las decisiones determinísticas y de resiliencia que NO dependen del LLM:
  - Cortocircuito por código de reserva (rutea a post-venta sin gastar LLM).
  - Acción determinística sobre el ticket (escalar vs auto-resolver).
  - Escalado de seguridad cuando el análisis de severidad falla (P1).
  - Fallback ante error del Runner del SDK, sin propagar 500 (P0).
  - Caché de embeddings y circuit breaker acotado (P2).

Son rápidos, deterministas y aptos para CI: cualquier acceso a OpenAI está mockeado.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# 1. Cortocircuito por código de reserva (ruteo a post-venta sin LLM)
# ---------------------------------------------------------------------------
class TestBookingCodeDetection:
    def _svc(self):
        from app.services.agent_service import agent_service
        return agent_service

    @pytest.mark.parametrize("message", [
        "Mi código es BK-2026-001",
        "hola, reserva BK41281119",
        "consulta sobre PKG-2025-001",
        "mi numero es AB-123456",
    ])
    def test_detecta_codigo_de_reserva(self, message):
        assert self._svc()._contains_booking_code(message) is True

    @pytest.mark.parametrize("message", [
        "quiero viajar a Japón",
        "qué paquetes tienen para Europa",
        "hola, busco unas vacaciones de playa",
        "cuánto sale un viaje a Tailandia",
    ])
    def test_no_detecta_en_consulta_normal(self, message):
        assert self._svc()._contains_booking_code(message) is False


# ---------------------------------------------------------------------------
# 2. Acción determinística sobre el ticket (escalar vs auto-resolver)
# ---------------------------------------------------------------------------
class TestApplyTicketAction:
    def _orchestrator(self):
        from app.services.postsale_orchestrator import postsale_orchestrator
        return postsale_orchestrator

    def _fake_service(self):
        service = MagicMock()
        service.db = MagicMock()
        return service

    def _fake_ticket(self):
        ticket = MagicMock()
        ticket.ticket_number = "TKT-TEST-001"
        ticket.has_escalated_issues = False
        ticket.escalated_issues_count = 0
        return ticket

    def test_escala_cuando_requires_escalation(self):
        orch = self._orchestrator()
        service, ticket = self._fake_service(), self._fake_ticket()

        status = orch._apply_ticket_action(
            service, ticket, requires_escalation=True,
            response_text="Un asesor te contactará.",
            message="el traslado no llegó y estoy varada",
            escalation={"escalation_reason": "cliente varado"},
        )

        assert status == "escalated"
        service.escalate_ticket.assert_called_once()
        service.resolve_ticket.assert_not_called()
        assert ticket.has_escalated_issues is True

    def test_auto_resuelve_consulta_simple(self):
        orch = self._orchestrator()
        service, ticket = self._fake_service(), self._fake_ticket()

        status = orch._apply_ticket_action(
            service, ticket, requires_escalation=False,
            response_text="El check-in es a las 14:00.",
            message="a qué hora es el check-in?",
            escalation={"suggested_category": "informativa"},
        )

        assert status == "auto_resolving"
        service.resolve_ticket.assert_called_once()
        service.escalate_ticket.assert_not_called()

    def test_no_auto_resuelve_si_ya_tiene_issues_escalados(self):
        orch = self._orchestrator()
        service, ticket = self._fake_service(), self._fake_ticket()
        ticket.has_escalated_issues = True  # ya hubo un problema serio antes

        status = orch._apply_ticket_action(
            service, ticket, requires_escalation=False,
            response_text="info adicional",
            message="otra consulta",
            escalation=None,
        )

        # Responde pero NO marca resuelto (hay issues escalados pendientes)
        assert status == "auto_resolving"
        service.resolve_ticket.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Escalado de seguridad ante análisis de severidad fallido (P1)
# ---------------------------------------------------------------------------
class TestSeverityAnalysisFailsSafe:
    @pytest.mark.asyncio
    async def test_analisis_fallido_escala_por_seguridad(self):
        from app.services.postsale_tools import _handle_analizar_severidad

        class FakeServiceThatFails:
            async def analyze_with_intelligence(self, *a, **k):
                raise RuntimeError("clasificador caído (simulado)")

        ctx = {
            "service": FakeServiceThatFails(),
            "package": object(),
            "message": "perdí mi pasaporte en París",
            "history": [],
        }
        result = await _handle_analizar_severidad(
            {"consulta": "perdí mi pasaporte"}, ctx
        )

        analysis = ctx.get("escalation_analysis")
        assert analysis is not None, "debe dejar un análisis en ctx aunque falle"
        assert analysis.get("requires_escalation") is True, "ante fallo => escalar, no auto-resolver"
        assert "ESCALACIÓN" in result["tool_result"].upper()


# ---------------------------------------------------------------------------
# 4. Fallback ante error del Runner del SDK, sin propagar 500 (P0)
# ---------------------------------------------------------------------------
class TestSDKRunnerFallback:
    @pytest.mark.asyncio
    async def test_preventa_fallback_no_propaga_excepcion(self):
        from app.services import agent_sdk_orchestrator as mod

        orch = mod.agent_sdk_orchestrator

        # Mockear lo I/O: lead block vacío y Runner que revienta
        async def fake_lead_block(*a, **k):
            return ("", {"lead_type": "FRIO"}, False)

        with patch.object(orch, "_build_lead_block", side_effect=fake_lead_block), \
             patch.object(mod.Runner, "run", new=AsyncMock(side_effect=RuntimeError("OpenAI 500"))), \
             patch.object(mod.rag_service.vector_store, "get_available_countries", return_value=["japón"]):
            db = MagicMock()
            result = await orch.run(db, "quiero ir a Japón", "test-fallback-pre", [])

        # No propaga: devuelve dict con respuesta de fallback amable
        assert "response" in result
        assert result["response"]  # no vacío
        assert result["tools_used"] == []


# ---------------------------------------------------------------------------
# 5. Caché de embeddings (P2)
# ---------------------------------------------------------------------------
class TestEmbeddingCache:
    @pytest.mark.asyncio
    async def test_segundo_embed_viene_del_cache(self):
        from app.services.embeddings import EmbeddingService

        svc = EmbeddingService.__new__(EmbeddingService)  # sin __init__ (evita crear cliente)
        from collections import OrderedDict
        svc._cache = OrderedDict()
        # Mock del cliente langchain: cuenta cuántas veces se llama
        svc.embeddings = MagicMock()
        svc.embeddings.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        texto = "paquetes a Japón en primavera"
        e1 = await svc.embed_text(texto)
        e2 = await svc.embed_text(texto)  # debe venir del cache

        assert e1 == e2
        # Solo UNA llamada real a OpenAI: el segundo fue cache hit
        assert svc.embeddings.aembed_query.await_count == 1
        assert len(svc._cache) == 1


# ---------------------------------------------------------------------------
# 6. Circuit breaker acotado a errores de API OpenAI (P2)
# ---------------------------------------------------------------------------
class TestCircuitBreakerScope:
    def test_no_incluye_exception_generica(self):
        from app.core.circuit_breaker import openai_circuit_breaker
        from openai import APIError

        exc = openai_circuit_breaker.expected_exception
        # Debe ser una tupla de excepciones específicas de OpenAI, no Exception genérica
        assert isinstance(exc, tuple)
        assert Exception not in exc
        assert APIError in exc


# ---------------------------------------------------------------------------
# 7. Métricas de negocio post-venta (P3 / observabilidad)
# ---------------------------------------------------------------------------
class TestPostsaleMetrics:
    def test_metricas_vacias_no_dividen_por_cero(self, db):
        """Sin tickets, las tasas son 0.0 y no revienta."""
        from app.services.metrics_service import metrics_service

        data = metrics_service.get_postsale_metrics(db)
        assert data["total_tickets"] == 0
        assert data["escalation_rate"] == 0.0
        assert data["auto_resolution_rate"] == 0.0
        # Estructura completa presente
        for key in ("escalated_tickets", "auto_resolved_tickets", "open_tickets"):
            assert key in data


# ---------------------------------------------------------------------------
# 8. Ruteo del flujo chat() — contrato de las ramas (P1 / post-P4)
# ---------------------------------------------------------------------------
# El refactor P4 reescribió la orquestación de chat(); estos tests fijan su
# contrato sin llamar a OpenAI real. Se mockea en los límites de I/O:
#   - _get_or_create_history → historial vacío
#   - conversation_state_manager.get_state → sin estado multi-paso
#   - la query de PostSaleSession (db es un MagicMock; .first() → None)
#   - el triage y los orquestadores SDK
class TestChatRouting:
    def _db_sin_postsale_activa(self):
        """db MagicMock cuyo query(...).filter(...).first() devuelve None."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    def _svc(self):
        from app.services.agent_service import agent_service
        return agent_service

    @pytest.mark.asyncio
    async def test_codigo_de_reserva_va_a_postventa_sin_triage(self):
        """Señal dura (código de reserva) ⇒ post-venta sin gastar el triage."""
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod

        svc = agent_service
        db = self._db_sin_postsale_activa()

        fake_postsale = MagicMock()
        fake_postsale.run_gate = AsyncMock(return_value={
            "handled": True,
            "result": {"response": "No encuentro esa reserva, ¿la verificás?"},
        })

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch("app.services.conversation_state_manager.conversation_state_manager.get_state", return_value=None), \
             patch.object(svc, "_contains_booking_code", return_value=True), \
             patch.object(svc, "_get_postsale_service", return_value=fake_postsale), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route", new=AsyncMock()) as mock_route:
            result = await svc.chat(db, "consulta de mi reserva BK41281119", "sess-postventa-dura")

        assert result["response"]
        assert result.get("context_type") == "postsale"
        mock_route.assert_not_called()  # el cortocircuito duro no llama al triage

    @pytest.mark.asyncio
    async def test_triage_casual_genera_respuesta_social(self):
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod

        svc = agent_service
        db = self._db_sin_postsale_activa()

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch("app.services.conversation_state_manager.conversation_state_manager.get_state", return_value=None), \
             patch.object(svc, "_contains_booking_code", return_value=False), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route",
                          new=AsyncMock(return_value={"route": triage_mod.ROUTE_CASUAL})), \
             patch.object(svc, "_generate_casual_response",
                          new=AsyncMock(return_value="¡Hola! ¿Pensando tu próximo viaje? 😊")):
            result = await svc.chat(db, "hola, cómo estás?", "sess-casual-001")

        assert result["intent"] == "casual_conversation"
        assert result["has_context"] is False
        assert "viaje" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_triage_postventa_delega_al_orquestador(self):
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod
        from app.services import postsale_sdk_orchestrator as post_mod

        svc = agent_service
        db = self._db_sin_postsale_activa()

        fake_postsale = MagicMock()
        fake_postsale.run_gate = AsyncMock(return_value={
            "handled": False, "package": object(), "ticket": object(),
            "query_to_process": "el traslado no llegó",
        })

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch("app.services.conversation_state_manager.conversation_state_manager.get_state", return_value=None), \
             patch.object(svc, "_contains_booking_code", return_value=False), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route",
                          new=AsyncMock(return_value={"route": triage_mod.ROUTE_POSTVENTA})), \
             patch.object(svc, "_get_postsale_service", return_value=fake_postsale), \
             patch.object(post_mod.postsale_sdk_orchestrator, "run",
                          new=AsyncMock(return_value={"response": "Escalé tu caso a un asesor.",
                                                      "context_type": "postsale"})):
            result = await svc.chat(db, "el traslado no llegó y estoy varada", "sess-post-triage")

        assert result["response"] == "Escalé tu caso a un asesor."
        assert result["context_type"] == "postsale"

    @pytest.mark.asyncio
    async def test_triage_preventa_delega_al_orquestador(self):
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod
        from app.services import agent_sdk_orchestrator as pre_mod

        svc = agent_service
        db = self._db_sin_postsale_activa()

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch("app.services.conversation_state_manager.conversation_state_manager.get_state", return_value=None), \
             patch.object(svc, "_contains_booking_code", return_value=False), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route",
                          new=AsyncMock(return_value={"route": triage_mod.ROUTE_PREVENTA})), \
             patch.object(pre_mod.agent_sdk_orchestrator, "run",
                          new=AsyncMock(return_value={"response": "Tenemos un paquete a Japón...",
                                                      "tools_used": []})), \
             patch.object(svc, "_save_message_to_db"):
            result = await svc.chat(db, "quiero ir a Japón en primavera", "sess-pre-triage")

        assert "japón" in result["response"].lower()
        assert result["tools_used"] == []

    @pytest.mark.asyncio
    async def test_estado_conversacional_corta_antes_del_ruteo(self):
        """Si hay captura multi-paso activa, se maneja antes de tocar el triage."""
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod

        svc = agent_service
        db = MagicMock()

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch("app.services.conversation_state_manager.conversation_state_manager.get_state",
                   return_value={"step": "awaiting_name"}), \
             patch.object(svc, "_handle_conversation_state",
                          new=AsyncMock(return_value={"response": "¿Cuál es tu nombre?", "has_context": False})), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route", new=AsyncMock()) as mock_route:
            result = await svc.chat(db, "Juan Pérez", "sess-estado-activo")

        assert result["response"] == "¿Cuál es tu nombre?"
        mock_route.assert_not_called()

    @pytest.mark.asyncio
    async def test_entrada_invalida_corta_temprano(self):
        """session_id corto ⇒ error de validación, sin tocar el ruteo."""
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod

        svc = agent_service
        with patch.object(triage_mod.triage_sdk_orchestrator, "route", new=AsyncMock()) as mock_route:
            result = await svc.chat(MagicMock(), "hola", "corto")  # session_id < 8 chars

        assert result["error"] is True
        assert result["error_type"] == "validation_error"
        mock_route.assert_not_called()


# ---------------------------------------------------------------------------
# 9. Fallback del triage ante error del Runner (P1 / resiliencia)
# ---------------------------------------------------------------------------
class TestTriageFallback:
    @pytest.mark.asyncio
    async def test_triage_falla_cae_a_preventa(self):
        """Si el Runner del triage revienta, route() devuelve PREVENTA (conservador)."""
        from app.services import triage_sdk_orchestrator as mod

        with patch.object(mod.Runner, "run", new=AsyncMock(side_effect=RuntimeError("triage 500"))):
            result = await mod.triage_sdk_orchestrator.route("una consulta cualquiera", "sess-triage-falla", [])

        assert result["route"] == mod.ROUTE_PREVENTA
