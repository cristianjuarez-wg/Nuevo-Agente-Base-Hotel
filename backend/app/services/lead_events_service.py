"""
Bitácora de actividad de un lead (mismo patrón que operations_service.log_event para tickets).

Registra, en la línea de tiempo del lead, las ACCIONES de Aura (resumidas en una frase) y el
SEGUIMIENTO humano. Es la fuente de la pestaña "Actividad" dentro de la card del lead y
alimenta la observabilidad del agente.

Las acciones de Aura se anotan de forma DETERMINÍSTICA (una frase fija) en los puntos donde el
agente ya actúa — sin costo de IA. El seguimiento humano lo escribe el equipo desde el backoffice.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadEvent
from app.core.logging_config import get_logger

logger = get_logger(__name__)

AGENT_NAME = "Aura"

# Frases fijas por acción de Aura (determinístico, sin IA). El front mapea `action` a ícono.
ACTION_SUMMARY = {
    "availability_shown": "Ofreció disponibilidad de habitaciones",
    "booking_confirmed": "Confirmó la reserva",
    "contact_requested": "Solicitó datos de contacto",
    "reengaged": "Retomó el contacto",
}


def log_lead_event(db: Session, lead_id: int, action: str,
                   actor_type: str = "aura", actor_name: Optional[str] = None,
                   summary: Optional[str] = None, note: Optional[str] = None) -> Optional[LeadEvent]:
    """Registra un evento en la bitácora del lead. Best-effort: un fallo NUNCA rompe el flujo.

    `actor_type="aura"` → actor_name="Aura" por defecto. Si no se pasa `summary` y la acción es
    una de Aura conocida, se usa la frase fija de ACTION_SUMMARY.
    """
    try:
        if actor_type == "aura" and not actor_name:
            actor_name = AGENT_NAME
        if summary is None and actor_type == "aura":
            summary = ACTION_SUMMARY.get(action)
        ev = LeadEvent(
            lead_id=lead_id, actor_type=actor_type, actor_name=actor_name,
            action=action, summary=summary, note=(note or None),
        )
        db.add(ev)
        db.commit()
        return ev
    except Exception as e:  # noqa: BLE001 — la bitácora nunca debe tumbar el flujo principal
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("No se pudo registrar el evento del lead", lead_id=lead_id,
                       action=action, error=str(e))
        return None


def _aura_action_logged(db: Session, lead_id: int, action: str) -> bool:
    """True si esta acción de Aura ya quedó registrada para el lead (para no duplicar)."""
    return db.query(LeadEvent).filter(
        LeadEvent.lead_id == lead_id, LeadEvent.action == action
    ).first() is not None


def log_aura_action_once(db: Session, lead_id: int, action: str,
                         summary: Optional[str] = None, note: Optional[str] = None) -> None:
    """Registra una acción de Aura SOLO si no estaba ya registrada (idempotente). Evita spamear
    la bitácora cuando un mismo hecho (p. ej. 'ofreció disponibilidad') se repite en la charla."""
    if _aura_action_logged(db, lead_id, action):
        return
    log_lead_event(db, lead_id, action, actor_type="aura", summary=summary, note=note)


def log_lead_event_by_session(db: Session, session_id: str, action: str,
                              actor_type: str = "aura", summary: Optional[str] = None,
                              note: Optional[str] = None, once: bool = True) -> None:
    """Conveniencia: resuelve el lead por session_id y registra el evento. No-op si no hay lead.
    Con `once=True` (default para acciones de Aura) no duplica la misma acción."""
    lead = db.query(Lead).filter(Lead.session_id == session_id).first()
    if not lead:
        return
    if once and actor_type == "aura":
        log_aura_action_once(db, lead.id, action, summary=summary, note=note)
    else:
        log_lead_event(db, lead.id, action, actor_type=actor_type, summary=summary, note=note)


async def generate_ai_summary(db: Session, lead_id: int) -> Optional[LeadEvent]:
    """Genera (bajo demanda) un resumen en lenguaje natural de la charla del lead y lo agrega a
    la bitácora. Barato: usa el modelo económico y RESPETA el freno de gasto. Best-effort:
    si no hay charla, el presupuesto está excedido, o falla, devuelve None sin romper nada.
    """
    from app.models.conversation_message import ConversationMessage
    from app.services import usage_service
    from app.core.openai_client import get_async_openai
    from app.config import settings

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead or not lead.session_id:
        return None

    if usage_service.is_budget_exceeded(db):
        logger.info("Resumen IA omitido: presupuesto excedido", lead_id=lead_id)
        return None

    msgs = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.session_id == lead.session_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .all()
    )
    if not msgs:
        return None

    # Transcripto compacto (acota tamaño: últimos ~30 mensajes).
    lines = []
    for m in msgs[-30:]:
        who = "Huésped" if m.role == "user" else "Aura"
        lines.append(f"{who}: {(m.content or '').strip()}")
    transcript = "\n".join(lines)[:6000]

    prompt = (
        "Resumí en UNA o dos frases, en español rioplatense y en tercera persona, la charla "
        "de este posible huésped con el hotel: qué buscaba, qué se le ofreció y en qué quedó. "
        "Sé concreto y breve, sin saludos ni encabezados.\n\n"
        f"Conversación:\n{transcript}\n\nResumen:"
    )
    try:
        client = get_async_openai()
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=120,
            timeout=30,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return None
        return log_lead_event(db, lead_id, action="resumen", actor_type="aura",
                              summary=None, note=text)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo generar el resumen IA del lead", lead_id=lead_id, error=str(e))
        return None
