"""
API Router para leer la transcripción de una conversación del agente Aura.

Tickets y leads guardan el `session_id` de la charla que los originó; este endpoint
devuelve esos mensajes para mostrarlos en el backoffice (panel del ticket / del lead).
Solo lectura: no toca cómo se crean tickets, leads ni la conversación.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.conversation_message import ConversationMessage
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/{session_id}/messages")
async def get_conversation_messages(
    session_id: str,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Devuelve los mensajes de una conversación (por session_id) en orden cronológico.

    Se usa para visualizar, desde el ticket o el lead, la charla con Aura que los generó.
    Si el session_id no tiene mensajes (p. ej. un ticket creado por el equipo), devuelve
    una lista vacía.
    """
    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .limit(limit)
        .all()
    )
    return {
        "session_id": session_id,
        "messages": [m.to_dict() for m in messages],
        "total": len(messages),
    }
