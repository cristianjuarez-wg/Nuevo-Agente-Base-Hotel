"""
Smoke tests — verifican que las rutas críticas devuelven estructuras válidas.
No llaman a OpenAI real (session_id inválido fuerza validación antes del LLM).
"""
import pytest


def test_greeting_endpoint_returns_message(client):
    """GET /api/chat/greeting debe devolver un mensaje de saludo no vacío."""
    response = client.get("/api/chat/greeting")
    assert response.status_code == 200
    data = response.json()
    # El endpoint devuelve 'greeting' como campo principal
    greeting_field = data.get("greeting") or data.get("message", "")
    assert len(greeting_field) > 0


def test_chat_rejects_empty_message(client):
    """POST /api/chat/message con mensaje vacío debe devolver error de validación."""
    response = client.post(
        "/api/chat/message",
        json={"message": "", "session_id": "smoke00001"},
    )
    # El agente responde 200 con error=True en lugar de 422 (validación interna)
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        data = response.json()
        assert data.get("error") is True


def test_chat_rejects_short_session_id(client):
    """POST /api/chat/message con session_id < 8 chars debe rechazarse."""
    response = client.post(
        "/api/chat/message",
        json={"message": "hola", "session_id": "abc"},
    )
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        data = response.json()
        assert data.get("error") is True


def test_no_context_response_does_not_duplicate():
    """Verifica que format_no_context_response devuelve is_final=True (sin doble procesado)."""
    from app.core.rag.rag_service import rag_service

    # Pasar geo_analysis como dict, igual que lo llama el código real
    geo_analysis = {"continent": "América", "countries": ["Cuba"], "cities": []}
    result = rag_service.format_no_context_response(geo_analysis)
    # Debe ser dict con is_final=True
    assert isinstance(result, dict), "format_no_context_response debe devolver un dict"
    assert result.get("is_final") is True, "is_final debe ser True para evitar doble procesado"


# (El smoke de PostSaleService.cleanup_inactive_sessions se retiró en Fase 0.2:
#  postsale_service era el servicio de post-venta de TURISMO, reemplazado por
#  hotel_postsale / hotel_postsale_orchestrator.)
