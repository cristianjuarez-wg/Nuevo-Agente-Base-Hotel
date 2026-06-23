"""
Endpoint de transcripción por session_id: GET /api/conversations/{session_id}/messages.

Tickets y leads guardan el session_id de la charla que los originó; el backoffice usa este
endpoint para mostrar esa conversación. Se valida el orden cronológico y el caso "sin charla".
"""
from datetime import datetime, timedelta

from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage


def _seed_conversation(db, session_id: str):
    conv = Conversation(session_id=session_id, channel="web", context_type="pre_sale")
    db.add(conv)
    db.flush()
    base = datetime(2026, 6, 23, 10, 0, 0)
    # Insertados a propósito fuera de orden cronológico para verificar el ordenamiento.
    msgs = [
        ConversationMessage(conversation_id=conv.id, session_id=session_id, role="assistant",
                            content="¡Hola! ¿En qué te ayudo?", sequence_number=2,
                            context_type="pre_sale", created_at=base + timedelta(minutes=1)),
        ConversationMessage(conversation_id=conv.id, session_id=session_id, role="user",
                            content="Hola, quiero info", sequence_number=1,
                            context_type="pre_sale", created_at=base),
    ]
    db.add_all(msgs)
    db.commit()


def test_devuelve_mensajes_en_orden_cronologico(client, db):
    _seed_conversation(db, "web-test-conv-1")
    r = client.get("/api/conversations/web-test-conv-1/messages")
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "web-test-conv-1"
    assert data["total"] == 2
    roles = [m["role"] for m in data["messages"]]
    assert roles == ["user", "assistant"]  # cronológico, no por inserción
    assert data["messages"][0]["content"] == "Hola, quiero info"


def test_session_sin_mensajes_devuelve_lista_vacia(client):
    r = client.get("/api/conversations/no-existe-xyz/messages")
    assert r.status_code == 200
    data = r.json()
    assert data["messages"] == []
    assert data["total"] == 0
