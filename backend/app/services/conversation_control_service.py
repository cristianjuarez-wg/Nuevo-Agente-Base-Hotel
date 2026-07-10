"""
Control de conversación: toma de control HUMANA (human takeover / HITL).

Cuando un humano "toma" una conversación, Aura deja de responder en esa sesión y el humano
contesta desde el backoffice. Patrón canónico de handoff: pausar el bot → respuesta humana →
release (manual o por inactividad).

FUENTE DE VERDAD: `Conversation.extra_metadata["takeover"]` (persistente en DB) — sobrevive
reinicios/deploys de Render, a diferencia de un flag en RAM. Mantenemos además un cache en
memoria para el chequeo rápido en el path del agente, rehidratable desde la DB en cache-miss.

Forma del estado guardado:
    extra_metadata["takeover"] = {
        "active": True,
        "staff_id": <int|None>, "staff_name": "<str>",
        "started_at": "<iso>", "last_human_activity_at": "<iso>",
    }
"""
from typing import Dict, Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.core.observability.logging_config import get_logger
from app.utils.timezone_utils import utcnow_naive

logger = get_logger(__name__)

_TAKEOVER_KEY = "takeover"

# Minutos sin actividad humana tras los cuales Aura retoma automáticamente la conversación.
AUTO_RELEASE_MINUTES = 10

# Una conversación se considera "en vivo" si tuvo actividad en los últimos N minutos.
# Fuente única (la usa también el listado en routers/conversations.py).
LIVE_WINDOW_MINUTES = 5


class WebChatOffline(Exception):
    """El chat WEB ya no está activo (el visitante cerró el navegador): no se puede tomar
    control ni responder, porque la respuesta humana se entrega por WebSocket al navegador
    abierto y no llegaría. WhatsApp no tiene este problema (entrega por Twilio al teléfono)."""

# Cache en RAM: session_id -> bool (controlada o no). Acelera el chequeo en cada mensaje
# entrante; la DB sigue siendo la verdad. Se rehidrata desde extra_metadata en cache-miss.
_control_cache: Dict[str, bool] = {}


def _now_iso() -> str:
    return utcnow_naive().isoformat()


def _get_conv(db: Session, session_id: str) -> Optional[Conversation]:
    return db.query(Conversation).filter(Conversation.session_id == session_id).first()


def _write_takeover(db: Session, conv: Conversation, state: Optional[Dict]) -> None:
    """Escribe (o limpia) el bloque takeover en extra_metadata. Reasigna el dict para que
    SQLAlchemy detecte el cambio del JSON (mutación in-place no se persiste)."""
    meta = dict(conv.extra_metadata or {})
    if state is None:
        meta.pop(_TAKEOVER_KEY, None)
    else:
        meta[_TAKEOVER_KEY] = state
    conv.extra_metadata = meta
    db.commit()


def get_state(db: Session, session_id: str) -> Optional[Dict]:
    """Devuelve el bloque takeover de la conversación (o None si no está bajo control)."""
    conv = _get_conv(db, session_id)
    if not conv:
        return None
    state = (conv.extra_metadata or {}).get(_TAKEOVER_KEY)
    return state if (state and state.get("active")) else None


def is_human_controlled(db: Session, session_id: str) -> bool:
    """True si la conversación está bajo control humano. Usa cache; en cache-miss consulta la DB
    y rehidrata (cubre reinicios/deploys donde la RAM se perdió). Antes de confirmar, aplica el
    auto-release por inactividad: si venció, libera y devuelve False."""
    cached = _control_cache.get(session_id)
    if cached is False:
        return False
    # cached is True o None (miss) → confirmamos contra la DB (y chequeamos auto-release).
    state = get_state(db, session_id)
    if not state:
        _control_cache[session_id] = False
        return False
    if _is_stale(state):
        release(db, session_id, reason="auto_inactividad")
        return False
    _control_cache[session_id] = True
    return True


def _is_stale(state: Dict) -> bool:
    """True si pasó el umbral de inactividad humana desde la última actividad."""
    ts = state.get("last_human_activity_at") or state.get("started_at")
    if not ts:
        return False
    try:
        last = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return False
    return utcnow_naive() - last > timedelta(minutes=AUTO_RELEASE_MINUTES)


def _is_web_offline(session_id: str, conv: Conversation) -> bool:
    """True si es un chat WEB sin actividad reciente (visitante desconectado).

    WhatsApp ('wa_') e Instagram ('ig_') NUNCA están offline: se entregan por Twilio/Graph API
    al dispositivo. Web sí, porque la entrega es por WebSocket al navegador abierto. Sin
    `last_message_at` se considera offline por las dudas (no hay señal de actividad)."""
    sid = session_id or ""
    if sid.startswith("wa_") or sid.startswith("ig_") or conv.channel in ("whatsapp", "instagram"):
        return False
    last = conv.last_message_at
    if not last:
        return True
    return (utcnow_naive() - last) > timedelta(minutes=LIVE_WINDOW_MINUTES)


def take_over(db: Session, session_id: str, staff_id: Optional[int] = None,
              staff_name: str = "") -> bool:
    """Marca la conversación como bajo control humano. Devuelve True si quedó tomada.

    Lanza WebChatOffline si es un chat web ya inactivo (no se podría entregar la respuesta)."""
    conv = _get_conv(db, session_id)
    if not conv:
        logger.warning("Takeover: conversación inexistente", session_id=session_id)
        return False
    if _is_web_offline(session_id, conv):
        raise WebChatOffline(session_id)
    now = _now_iso()
    _write_takeover(db, conv, {
        "active": True,
        "staff_id": staff_id,
        "staff_name": staff_name or "",
        "started_at": now,
        "last_human_activity_at": now,
    })
    _control_cache[session_id] = True
    logger.info("Conversación tomada por humano", session_id=session_id, staff_id=staff_id)
    return True


def touch_activity(db: Session, session_id: str) -> None:
    """Refresca last_human_activity_at (al enviar una respuesta humana) para postergar el
    auto-release. No-op si la conversación no está bajo control."""
    conv = _get_conv(db, session_id)
    if not conv:
        return
    state = dict((conv.extra_metadata or {}).get(_TAKEOVER_KEY) or {})  # copia, no mutar in-place
    if not state.get("active"):
        return
    state["last_human_activity_at"] = _now_iso()
    _write_takeover(db, conv, state)


def release(db: Session, session_id: str, reason: str = "manual") -> bool:
    """Libera la conversación: Aura retoma. Devuelve True si estaba tomada y se liberó."""
    conv = _get_conv(db, session_id)
    _control_cache[session_id] = False
    if not conv:
        return False
    had = bool((conv.extra_metadata or {}).get(_TAKEOVER_KEY, {}).get("active"))
    _write_takeover(db, conv, None)
    if had:
        logger.info("Conversación liberada (Aura retoma)", session_id=session_id, reason=reason)
    return had
