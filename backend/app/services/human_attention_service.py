"""
Servicio de ATENCIÓN HUMANA — disponibilidad para el handoff del agente a una persona.

`is_human_available(db)` es la función central: decide si el agente puede OFRECER pasar con un
humano AHORA. Se usa para poblar la señal del prompt (handoff_block) y para el veredicto de la
tool `derivar_a_humano`.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.human_attention_config import HumanAttentionConfig, _default_schedule
from app.utils.timezone_utils import now_business
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

_EDITABLE = {"enabled", "on_call", "schedule"}


def get_config(db: Session) -> HumanAttentionConfig:
    """Fila única id=1 (get-or-create), molde de exchange_rate_service."""
    cfg = db.query(HumanAttentionConfig).filter(HumanAttentionConfig.id == 1).first()
    if cfg is None:
        cfg = HumanAttentionConfig(id=1, enabled=False, on_call=False, schedule=_default_schedule())
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def update_config(db: Session, data: dict) -> dict:
    """Actualiza solo los campos editables presentes. Devuelve el dict actualizado."""
    cfg = get_config(db)
    for key, value in (data or {}).items():
        if key in _EDITABLE and value is not None:
            setattr(cfg, key, value)
    db.commit()
    db.refresh(cfg)
    logger.info("HumanAttentionConfig actualizado", fields=list((data or {}).keys()))
    return cfg.to_dict()


def _hhmm_to_minutes(s: str) -> Optional[int]:
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return None


def is_human_available(db: Session, now=None) -> bool:
    """¿Hay atención humana disponible AHORA?

    enabled AND (on_call OR la hora local de hoy cae dentro de la franja activa del día).
    El horario se interpreta en HORA LOCAL del negocio (now_business()). Fail-closed: ante
    cualquier problema devuelve False (mejor no prometer un handoff que nadie tomará).
    """
    try:
        cfg = get_config(db)
        if not cfg.enabled:
            return False
        if cfg.on_call:
            return True
        ahora = now or now_business()          # datetime local naive
        dia = str(ahora.weekday())             # "0"=lunes … "6"=domingo
        franja = (cfg.schedule or {}).get(dia) or {}
        if not franja.get("active"):
            return False
        desde = _hhmm_to_minutes(franja.get("from"))
        hasta = _hhmm_to_minutes(franja.get("to"))
        if desde is None or hasta is None:
            return False
        minutos = ahora.hour * 60 + ahora.minute
        return desde <= minutos < hasta
    except Exception as e:  # noqa: BLE001 — nunca romper el turno por esta consulta
        logger.warning("is_human_available falló, asumo NO disponible", error=str(e))
        return False
