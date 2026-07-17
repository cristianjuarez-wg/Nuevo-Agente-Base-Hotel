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
        "Mi código es HTL-6XV6",
        "hola, mi reserva HTL-7F3A",
        "consulta sobre la reserva HTL-ABCD",
        "tengo el código htl-9z3k",  # case-insensitive
    ])
    def test_detecta_codigo_de_reserva(self, message):
        assert self._svc()._contains_booking_code(message) is True

    @pytest.mark.parametrize("message", [
        "quiero una habitación con vista al lago",
        "tienen disponibilidad para el finde?",
        "hola, cuánto sale la noche en julio?",
        "qué servicios incluye el desayuno?",
    ])
    def test_no_detecta_en_consulta_normal(self, message):
        assert self._svc()._contains_booking_code(message) is False


# ---------------------------------------------------------------------------
# 1b. Interceptor del ACUSE de reserva de mesa (solo el acuse real del frontend,
#     no un MESA-XXXX suelto que el usuario tipea a mano pidiendo otra cosa).
# ---------------------------------------------------------------------------
class TestTableConfirmationInterceptor:
    def _svc(self):
        from app.services.agent_service import agent_service
        return agent_service

    @pytest.mark.parametrize("message", [
        # El acuse real que emite el frontend (i18n/chat.js:tableConfirmedMsg), 4 idiomas.
        "Confirmé mi reserva de mesa MESA-HHHR.",
        "I confirmed my table booking MESA-HHHR.",
        "Confirmei minha reserva de mesa MESA-HHHR.",
        "J’ai confirmé ma réservation de table MESA-HHHR.",
    ])
    def test_acuse_real_dispara(self, message):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None  # sin detalle
        resp = self._svc()._handle_table_confirmation(db, message, "web-test", [])
        assert resp is not None
        assert resp.get("intent") == "table_reservation_confirmed"

    @pytest.mark.parametrize("message", [
        # Código de mesa tipeado a mano PIDIENDO otra cosa: NO debe secuestrar la conversación.
        "MESA-HHHR, recomendame algo de la carta",
        "mi código es MESA-HHHR, qué me recomendás?",
        "MESA-HHHR",
        # Sin código: tampoco.
        "tenés mesa para hoy a la noche?",
    ])
    def test_codigo_suelto_no_dispara(self, message):
        db = MagicMock()
        resp = self._svc()._handle_table_confirmation(db, message, "web-test", [])
        assert resp is None




# ---------------------------------------------------------------------------
# 2. Acción determinística sobre el ticket del HOTEL (escalar vs auto-resolver)
# ---------------------------------------------------------------------------
class TestApplyTicketAction:
    def _service(self):
        # HotelPostSaleService sin __init__ (evita crear cliente OpenAI); solo
        # necesitamos su db (mock) para el commit y el método apply_ticket_action.
        from app.services.hotel_postsale import HotelPostSaleService
        svc = HotelPostSaleService.__new__(HotelPostSaleService)
        svc.db = MagicMock()
        return svc

    def _fake_ticket(self):
        ticket = MagicMock()
        ticket.ticket_number = "HTL-TKT-001"
        ticket.description = "Sesión de soporte iniciada"
        return ticket

    def test_escala_cuando_requires_escalation(self):
        svc, ticket = self._service(), self._fake_ticket()

        status = svc.apply_ticket_action(
            ticket, requires_escalation=True,
            response_text="Un asesor te contactará.",
            query="quiero cancelar mi reserva y que me devuelvan la plata",
            analysis={"escalation_reason": "pide cancelar", "category": "cancel",
                      "urgency_level": "alta"},
        )

        assert status == "escalated"
        assert ticket.status == "escalated"
        assert ticket.escalated == 1

    def test_auto_resuelve_consulta_simple(self):
        svc, ticket = self._service(), self._fake_ticket()

        status = svc.apply_ticket_action(
            ticket, requires_escalation=False,
            response_text="El check-in es a las 14:00.",
            query="a qué hora es el check-in?",
            analysis={"category": "info", "urgency_level": "baja"},
        )

        assert status == "resolved"
        assert ticket.status == "resolved"
        # Guarda la respuesta con la que auto-resolvió, para auditoría.
        assert "14:00" in ticket.auto_resolved_by_agent


# ---------------------------------------------------------------------------
# 3. Escalado de seguridad ante análisis fallido del HOTEL (P1, fail-safe)
# ---------------------------------------------------------------------------
class TestSeverityAnalysisFailsSafe:
    @pytest.mark.asyncio
    async def test_analisis_fallido_escala_por_seguridad(self):
        """Si el clasificador de escalación revienta, analyze_escalation escala por
        seguridad (requires_escalation=True) en vez de auto-resolver un caso serio."""
        from app.services.hotel_postsale import HotelPostSaleService

        svc = HotelPostSaleService.__new__(HotelPostSaleService)
        # Cliente cuyo create() falla → debe caer al fallback seguro.
        svc.client = MagicMock()
        svc.client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("clasificador caído (simulado)")
        )

        result = await svc.analyze_escalation("cancelá mi reserva ya", booking=MagicMock())

        assert result["requires_escalation"] is True, "ante fallo => escalar, no auto-resolver"
        assert result["urgency_level"] == "alta"


# ---------------------------------------------------------------------------
# 4. Fallback ante error del Runner del SDK, sin propagar 500 (P0)
# ---------------------------------------------------------------------------
class TestSDKRunnerFallback:
    @pytest.mark.asyncio
    async def test_preventa_fallback_no_propaga_excepcion(self):
        """Si el Runner del SDK revienta, la pre-venta del hotel devuelve un fallback
        amable en vez de propagar un 500."""
        import app.services.hotel_sdk_orchestrator as mod

        orch = mod.hotel_sdk_orchestrator

        # Mockear lo I/O: lead block vacío y Runner que revienta.
        async def fake_lead_block(*a, **k):
            return ("", {"lead_type": "FRIO"}, False, None)

        with patch.object(orch, "_build_lead_block", side_effect=fake_lead_block), \
             patch.object(mod.Runner, "run", new=AsyncMock(side_effect=RuntimeError("OpenAI 500"))):
            db = MagicMock()
            result = await orch.run(db, "tienen habitaciones?", "test-fallback-pre", [])

        # No propaga: devuelve dict con respuesta de fallback amable.
        assert "response" in result
        assert result["response"]  # no vacío
        assert result["tools_used"] == []


# ---------------------------------------------------------------------------
# 5. Caché de embeddings (P2)
# ---------------------------------------------------------------------------
class TestEmbeddingCache:
    @pytest.mark.asyncio
    async def test_segundo_embed_viene_del_cache(self):
        from app.core.rag.embeddings import EmbeddingService

        svc = EmbeddingService.__new__(EmbeddingService)  # sin __init__ (evita crear cliente)
        from collections import OrderedDict
        svc._cache = OrderedDict()
        svc._model = "text-embedding-3-small"
        # Mock del SDK de OpenAI directo: client.embeddings.create(...) -> resp.data[0].embedding
        resp = MagicMock()
        resp.data = [MagicMock(embedding=[0.1, 0.2, 0.3], index=0)]
        svc._client = MagicMock()
        svc._client.embeddings.create = AsyncMock(return_value=resp)

        texto = "paquetes a Japón en primavera"
        e1 = await svc.embed_text(texto)
        e2 = await svc.embed_text(texto)  # debe venir del cache

        assert e1 == e2
        # Solo UNA llamada real a OpenAI: el segundo fue cache hit
        assert svc._client.embeddings.create.await_count == 1
        assert len(svc._cache) == 1


# ---------------------------------------------------------------------------
# 6. Circuit breaker acotado a errores de API OpenAI (P2)
# ---------------------------------------------------------------------------
class TestCircuitBreakerScope:
    def test_no_incluye_exception_generica(self):
        from app.core.llm.circuit_breaker import openai_circuit_breaker
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
#   - la query de PostSaleSession (db es un MagicMock; .first() → None)
#   - el triage y los orquestadores SDK
class TestChatRouting:
    def _db_sin_postsale_activa(self):
        """db MagicMock sin post-venta activa: cualquier query(...).first() ⇒ None.

        El chequeo real encadena varios .filter()/.order_by(), así que devolvemos un
        query 'auto-encadenable' que siempre termina en first()=None (y all()=[]).
        """
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = None
        chain.all.return_value = []
        db.query.return_value = chain
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
             patch.object(svc, "_contains_booking_code", return_value=True), \
             patch("app.services.hotel_postsale.HotelPostSaleService", return_value=fake_postsale), \
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
             patch.object(svc, "_contains_booking_code", return_value=False), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route",
                          new=AsyncMock(return_value={"route": triage_mod.ROUTE_CASUAL, "usage": {}})), \
             patch.object(svc, "_build_casual_guest_block", return_value=""), \
             patch.object(svc, "_should_capture_lead_in_casual", new=AsyncMock(return_value=False)), \
             patch.object(svc, "_generate_casual_response",
                          new=AsyncMock(return_value=("¡Hola! ¿En qué puedo ayudarte con tu estadía? 😊", {}))), \
             patch.object(svc, "_save_message_to_db"):
            result = await svc.chat(db, "hola, cómo estás?", "sess-casual-001")

        assert result["intent"] == "casual_conversation"
        assert result["has_context"] is False
        assert "ayudarte" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_triage_postventa_delega_al_orquestador(self):
        """Ruta post-venta del HOTEL: gate (HotelPostSaleService) + orquestador del hotel."""
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod
        import app.services.hotel_postsale as hps_mod
        import app.services.hotel_postsale_orchestrator as orch_mod

        svc = agent_service
        db = self._db_sin_postsale_activa()

        # El gate no resuelve solo: deja pasar al loop con tools del hotel.
        fake_service = MagicMock()
        fake_service.run_gate = AsyncMock(return_value={
            "handled": False, "booking": object(), "ticket": object(),
            "query_to_process": "el aire de la habitación no enfría",
        })

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch.object(svc, "_contains_booking_code", return_value=False), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route",
                          new=AsyncMock(return_value={"route": triage_mod.ROUTE_POSTVENTA, "usage": {}})), \
             patch.object(hps_mod, "HotelPostSaleService", return_value=fake_service), \
             patch.object(orch_mod.hotel_postsale_sdk_orchestrator, "run",
                          new=AsyncMock(return_value={"response": "Generé un ticket para mantenimiento.",
                                                      "usage": {}})):
            result = await svc.chat(db, "el aire de la habitación no enfría", "sess-post-triage")

        assert result["response"] == "Generé un ticket para mantenimiento."
        assert result["context_type"] == "postsale"

    @pytest.mark.asyncio
    async def test_triage_preventa_delega_al_orquestador(self):
        """Ruta pre-venta del HOTEL: delega en hotel_sdk_orchestrator."""
        from app.services.agent_service import agent_service
        from app.services import triage_sdk_orchestrator as triage_mod
        import app.services.hotel_sdk_orchestrator as pre_mod

        svc = agent_service
        db = self._db_sin_postsale_activa()

        with patch.object(svc, "_get_or_create_history", return_value=[]), \
             patch.object(svc, "_contains_booking_code", return_value=False), \
             patch.object(triage_mod.triage_sdk_orchestrator, "route",
                          new=AsyncMock(return_value={"route": triage_mod.ROUTE_PREVENTA, "usage": {}})), \
             patch.object(pre_mod.hotel_sdk_orchestrator, "run",
                          new=AsyncMock(return_value={"response": "Tenemos la habitación King disponible.",
                                                      "tools_used": []})), \
             patch.object(svc, "_save_message_to_db"):
            result = await svc.chat(db, "tienen disponibilidad para el finde?", "sess-pre-triage")

        assert "king" in result["response"].lower()
        assert result["tools_used"] == []

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
