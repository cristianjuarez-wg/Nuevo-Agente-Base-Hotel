"""
Métricas de DESEMPEÑO por agente — el "legajo" del Centro del Empleado Digital.

Distinto de las analíticas del negocio (§2.3): acá la pregunta es "¿cómo trabajó
ESTE agente?" — cuánto atendió, qué resolvió, qué escaló, qué ahorró y cuánto
costó en IA. Reusa lo que ya existe:
  - business_metrics: períodos, leads, tickets, reservas.
  - usage_service / token_pricing: tokens → USD.

Atribución SIN migrar esquema (§8): el costo IA se filtra por el prefijo del
session_id (agent_directory); el desempeño operativo se atribuye al agente cuyo
rol lo produce (Aura/guest capta leads y reservas; Operaciones/staff cierra
tickets). Cuando una feature pida granularidad fina, se agrega la FK agent_id.
"""
from datetime import date, datetime
from typing import Dict, Optional

import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.hotel import Booking, HotelTicket, TICKET_RESOLVED_STATES
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.services import business_metrics
from app.services.agent_directory import session_prefixes_for_role
from app.core.token_pricing import cost_usd_from_total
from app.utils.timezone_utils import ARGENTINA_TZ
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# % de comisión OTA que se ahorra por cada reserva directa (Booking.com ~15%).
# Constante de negocio; se podría volver configurable más adelante.
OTA_COMMISSION_PCT = 0.15


def _ar_date_to_utc_naive(d: date, end_of_day: bool = False) -> datetime:
    """Convierte una fecha (interpretada en hora AR) a datetime UTC naive.

    Las marcas created_at de los mensajes/conversaciones son UTC naive; las
    fechas de business_metrics son fechas calendario AR. Convertimos para filtrar.
    """
    t = datetime(d.year, d.month, d.day, 0, 0, 0)
    ar = ARGENTINA_TZ.localize(t)
    return ar.astimezone(pytz.utc).replace(tzinfo=None)


def _cost_for_role(db: Session, role: str, start: date, end: date) -> Dict:
    """Tokens y USD consumidos por el agente de ese rol en el rango.

    Filtra ConversationMessage por el prefijo de session_id que corresponde al rol
    (sin FK agent_id). end es exclusivo (como en business_metrics).
    """
    since = _ar_date_to_utc_naive(start)
    until = _ar_date_to_utc_naive(end)
    prefixes = session_prefixes_for_role(role)

    q = (
        db.query(
            ConversationMessage.model_used,
            func.coalesce(func.sum(ConversationMessage.tokens_used), 0),
        )
        .filter(
            ConversationMessage.role == "assistant",
            ConversationMessage.tokens_used.isnot(None),
            ConversationMessage.created_at >= since,
            ConversationMessage.created_at < until,
        )
    )
    # OR de prefijos (like 'wa_%' o 'web-%' …).
    from sqlalchemy import or_
    q = q.filter(or_(*[ConversationMessage.session_id.like(p + "%") for p in prefixes]))
    rows = q.group_by(ConversationMessage.model_used).all()

    total_tokens = 0
    total_usd = 0.0
    by_model = []
    for model_used, tokens in rows:
        tokens = int(tokens or 0)
        usd = cost_usd_from_total(model_used, tokens)
        total_tokens += tokens
        total_usd += usd
        by_model.append({"model": model_used or "desconocido", "tokens": tokens, "usd": round(usd, 4)})

    return {"tokens": total_tokens, "usd": round(total_usd, 4), "by_model": by_model}


def _conversations_for_role(db: Session, role: str, start: date, end: date) -> int:
    """Cuenta conversaciones atendidas por el agente del rol en el rango (por prefijo)."""
    since = _ar_date_to_utc_naive(start)
    until = _ar_date_to_utc_naive(end)
    prefixes = session_prefixes_for_role(role)
    from sqlalchemy import or_
    return (
        db.query(func.count(func.distinct(ConversationMessage.session_id)))
        .filter(
            ConversationMessage.created_at >= since,
            ConversationMessage.created_at < until,
            or_(*[ConversationMessage.session_id.like(p + "%") for p in prefixes]),
        )
        .scalar()
        or 0
    )


def _tickets_counts(db: Session, start: date, end: date) -> Dict:
    """Tickets resueltos y escalados en el rango (atribuibles al agente de operaciones)."""
    resolved = (
        db.query(func.count(HotelTicket.id))
        .filter(
            HotelTicket.created_at >= start,
            HotelTicket.created_at < end,
            HotelTicket.status.in_(TICKET_RESOLVED_STATES),
        )
        .scalar()
        or 0
    )
    escalated = (
        db.query(func.count(HotelTicket.id))
        .filter(
            HotelTicket.created_at >= start,
            HotelTicket.created_at < end,
            HotelTicket.escalated == 1,
        )
        .scalar()
        or 0
    )
    return {"resolved": int(resolved), "escalated": int(escalated)}


def _bookings_and_savings(db: Session, start: date, end: date) -> Dict:
    """Reservas DIRECTAS (web/agente) creadas en el rango y ahorro estimado de comisión OTA."""
    bookings = (
        db.query(Booking)
        .filter(
            Booking.created_at >= _ar_date_to_utc_naive(start),
            Booking.created_at < _ar_date_to_utc_naive(end),
            ~Booking.status.in_(("cancelled",)),
        )
        .all()
    )
    count = len(bookings)
    base_usd = 0.0
    for b in bookings:
        price = getattr(b, "full_price_usd", None) or getattr(b, "total_price_usd", None) or 0.0
        base_usd += float(price or 0.0)
    savings = round(base_usd * OTA_COMMISSION_PCT, 2)
    return {"bookings_closed": count, "ota_savings_usd": savings}


def get_agent_performance(db: Session, agent: Agent, period: str = "mes") -> Dict:
    """Legajo de desempeño de un agente para un período.

    Atribuye las métricas operativas según el rol del agente:
      - guest (Aura): conversaciones, leads convertidos, reservas, ahorro OTA.
      - staff (Operaciones): conversaciones, tickets resueltos/escalados.
      - management (Asesor): conversaciones (su valor es asesorar, no operar).
    Todos muestran su costo de IA (tokens/USD).
    """
    start, end, label = business_metrics.resolve_period(period)
    role = agent.role

    cost = _cost_for_role(db, role, start, end)
    conversations = _conversations_for_role(db, role, start, end)

    perf: Dict = {"conversations": conversations}

    if role == "guest":
        leads = business_metrics.get_leads_summary(db, start, end)
        bk = _bookings_and_savings(db, start, end)
        perf.update({
            "leads_converted": leads.get("closed", 0),
            "leads_generated": leads.get("generated", 0),
            "bookings_closed": bk["bookings_closed"],
            "ota_savings_usd": bk["ota_savings_usd"],
        })
    elif role == "staff":
        perf.update(_tickets_counts(db, start, end))

    return {
        "agent": agent.to_dict(),
        "period": {"label": label, "start": start.isoformat(), "end": end.isoformat()},
        "performance": perf,
        "cost": cost,
    }


def build_daily_report(db: Session, agent: Agent) -> str:
    """Texto del 'parte de fin de día' del agente (Etapa 2). Lenguaje de negocio."""
    data = get_agent_performance(db, agent, period="hoy")
    p = data["performance"]
    parts = [f"Hoy atendí {p.get('conversations', 0)} conversaciones"]
    if agent.role == "guest":
        if p.get("bookings_closed"):
            extra = f" (~USD {p.get('ota_savings_usd', 0):.0f} de comisión OTA ahorrada)" if p.get("ota_savings_usd") else ""
            parts.append(f"cerré {p['bookings_closed']} reservas directas{extra}")
        if p.get("leads_converted"):
            parts.append(f"convertí {p['leads_converted']} leads")
    elif agent.role == "staff":
        if p.get("resolved"):
            parts.append(f"resolví {p['resolved']} tickets")
        if p.get("escalated"):
            parts.append(f"escalé {p['escalated']} a un humano")
    return ", ".join(parts) + "."
