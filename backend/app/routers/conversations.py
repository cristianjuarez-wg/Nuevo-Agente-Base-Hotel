"""
API Router para leer la transcripción de una conversación del agente Aura.

Tickets y leads guardan el `session_id` de la charla que los originó; este endpoint
devuelve esos mensajes para mostrarlos en el backoffice (panel del ticket / del lead).
Solo lectura: no toca cómo se crean tickets, leads ni la conversación.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.contact import Contact
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    channel: str = Query("whatsapp"),
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lista las conversaciones de un canal (por defecto WhatsApp), de la más reciente a la
    más vieja. Pensado para VER quién se contactó por WhatsApp aunque no haya dejado datos
    (no aparece en Leads/Pasajeros). Enriquece cada fila con el teléfono y nombre del Contact.
    """
    q = db.query(Conversation).filter(Conversation.channel == channel)
    total = q.count()
    rows = (
        q.order_by(Conversation.last_message_at.desc().nullslast(),
                   Conversation.started_at.desc())
        .limit(limit).offset(offset).all()
    )

    # Lookup de contactos en lote (evita N+1).
    contact_ids = [r.contact_id for r in rows if r.contact_id]
    contacts = {}
    if contact_ids:
        for c in db.query(Contact).filter(Contact.id.in_(contact_ids)).all():
            contacts[c.id] = c

    def _phone_from_session(sid: str) -> Optional[str]:
        return ("+" + sid[3:]) if (sid or "").startswith("wa_") else None

    items = []
    for r in rows:
        c = contacts.get(r.contact_id)
        phone = (c.phone_number if c else None) or _phone_from_session(r.session_id)
        name = (c.full_name or c.first_name) if c else None
        items.append({
            "session_id": r.session_id,
            "contact_id": r.contact_id,
            "phone": phone,
            "name": name,
            "channel": r.channel,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
            "message_count": r.message_count,
            "status": r.status,
            "lead_generated": r.lead_generated,
        })
    return {"conversations": items, "total": total, "limit": limit, "offset": offset}


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
