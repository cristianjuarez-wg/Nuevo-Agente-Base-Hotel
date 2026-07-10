"""
Servicio de consumo de tokens / costo USD del agente, y enforcement de topes.

Lee el consumo real desde `conversation_messages` (columna `tokens_used`, que se
empezó a poblar con los tokens reales del SDK) y lo convierte a USD con
`token_pricing`. Provee:

  - get_usage_summary(db): resumen para el panel del backoffice (hoy / mes).
  - is_budget_exceeded(db): True si el gasto superó el tope activo → el agente
    debe detenerse sin llamar a OpenAI.

Las marcas `created_at` de los mensajes se guardan en UTC naive
(utcnow_naive). Para agrupar por "hoy / mes" en hora de Argentina, calculamos
los límites del período en Argentina y los convertimos a UTC para el filtro.
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation_message import ConversationMessage
from app.models.conversation import Conversation
from app.models.agent_budget import AgentBudgetConfig
from app.core.llm.token_pricing import cost_usd_from_total
from app.core.observability.logging_config import get_logger
from app.utils.timezone_utils import ARGENTINA_TZ
from app.utils.timezone_utils import utcnow_naive

logger = get_logger(__name__)

# Cache corto del resultado de enforcement para no agregar la tabla en cada
# request del chat. (segundos)
_BUDGET_CACHE_TTL = 15
_budget_cache: Dict[str, object] = {"checked_at": 0.0, "exceeded": False}


def _ar_period_bounds_utc() -> tuple[datetime, datetime, datetime]:
    """
    Devuelve (inicio_dia_utc, inicio_mes_utc, ahora_utc) donde "día" y "mes" se
    calculan en hora de Argentina. Los datetime resultantes son naive en UTC
    (para comparar con created_at, que es UTC naive).
    """
    now_ar = datetime.now(ARGENTINA_TZ)
    day_start_ar = now_ar.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start_ar = day_start_ar.replace(day=1)

    def _to_utc_naive(dt_ar: datetime) -> datetime:
        return dt_ar.astimezone(pytz.utc).replace(tzinfo=None)

    return (
        _to_utc_naive(day_start_ar),
        _to_utc_naive(month_start_ar),
        utcnow_naive(),
    )


def _aggregate(db: Session, since_utc: datetime) -> Dict:
    """
    Suma tokens y estima USD de los mensajes 'assistant' desde `since_utc`,
    desglosado por modelo. Solo cuentan mensajes con tokens_used registrados.
    """
    rows = (
        db.query(
            ConversationMessage.model_used,
            func.coalesce(func.sum(ConversationMessage.tokens_used), 0),
        )
        .filter(
            ConversationMessage.role == "assistant",
            ConversationMessage.tokens_used.isnot(None),
            ConversationMessage.created_at >= since_utc,
        )
        .group_by(ConversationMessage.model_used)
        .all()
    )

    total_tokens = 0
    total_usd = 0.0
    by_model = []
    for model_used, tokens in rows:
        tokens = int(tokens or 0)
        usd = cost_usd_from_total(model_used, tokens)
        total_tokens += tokens
        total_usd += usd
        by_model.append({
            "model": model_used or "desconocido",
            "tokens": tokens,
            "usd": round(usd, 4),
        })

    return {
        "tokens": total_tokens,
        "usd": round(total_usd, 4),
        "by_model": by_model,
    }


def get_budget_config(db: Session) -> AgentBudgetConfig:
    """Obtiene (o crea) la fila única de configuración de topes."""
    config = db.query(AgentBudgetConfig).filter(AgentBudgetConfig.id == 1).first()
    if config is None:
        config = AgentBudgetConfig(id=1, enabled=False)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _count_conversations(db: Session, since_utc: datetime) -> int:
    """Cuenta conversaciones (pre-venta) iniciadas desde `since_utc`."""
    return (
        db.query(func.count(Conversation.id))
        .filter(Conversation.started_at >= since_utc)
        .scalar()
        or 0
    )


def get_usage_summary(db: Session) -> Dict:
    """Resumen de consumo para el panel del backoffice."""
    day_start_utc, month_start_utc, _ = _ar_period_bounds_utc()

    today = _aggregate(db, day_start_utc)
    month = _aggregate(db, month_start_utc)
    config = get_budget_config(db)

    today["conversations"] = _count_conversations(db, day_start_utc)
    month["conversations"] = _count_conversations(db, month_start_utc)

    daily_limit = config.daily_limit_usd
    monthly_limit = config.monthly_limit_usd

    daily_exceeded = bool(config.enabled and daily_limit is not None and today["usd"] >= daily_limit)
    monthly_exceeded = bool(config.enabled and monthly_limit is not None and month["usd"] >= monthly_limit)

    return {
        "today": today,
        "month": month,
        "limits": {
            "enabled": bool(config.enabled),
            "daily_limit_usd": daily_limit,
            "monthly_limit_usd": monthly_limit,
        },
        "blocked": daily_exceeded or monthly_exceeded,
        "daily_exceeded": daily_exceeded,
        "monthly_exceeded": monthly_exceeded,
    }


def is_budget_exceeded(db: Session, use_cache: bool = True) -> bool:
    """
    True si el gasto superó el tope activo (diario o mensual). Cacheado unos
    segundos para no agregar la tabla en cada mensaje del chat.
    """
    now = time.time()
    if use_cache and (now - float(_budget_cache["checked_at"])) < _BUDGET_CACHE_TTL:
        return bool(_budget_cache["exceeded"])

    try:
        summary = get_usage_summary(db)
        exceeded = bool(summary["blocked"])
    except Exception as e:
        # Ante cualquier error de agregación, NO bloqueamos el agente (fail-open):
        # preferimos seguir respondiendo a romper la demo por un fallo de cálculo.
        logger.warning("Budget check failed, allowing request", error=str(e))
        exceeded = False

    _budget_cache["checked_at"] = now
    _budget_cache["exceeded"] = exceeded
    return exceeded


def invalidate_budget_cache() -> None:
    """Fuerza recalcular en el próximo check (llamar al cambiar la config)."""
    _budget_cache["checked_at"] = 0.0
