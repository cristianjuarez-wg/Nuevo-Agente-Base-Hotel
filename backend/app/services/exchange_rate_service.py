"""
Servicio de cotización USD → ARS.

Resuelve la cotización vigente según el modo configurado (auto/manual), con
cache en proceso (~15 min) para no pegarle a la API externa en cada request de
disponibilidad, y fallback a la última cotización cacheada en DB.

Fuente automática: dólar oficial venta de dolarapi.com (gratis, sin API key).
"""
import time
from datetime import datetime
from typing import Optional, Dict

import requests
from sqlalchemy.orm import Session

from app.models.exchange_rate import ExchangeRateConfig, DEFAULT_RATE
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

DOLARAPI_URL = "https://dolarapi.com/v1/dolares/oficial"
_FETCH_TIMEOUT = 5          # segundos
_CACHE_TTL = 15 * 60        # 15 minutos

# Cache en proceso: evita pegarle a la API en cada consulta de disponibilidad.
_cache: Dict[str, float] = {"rate": 0.0, "ts": 0.0}


def fetch_official_rate() -> Optional[float]:
    """Cotización del dólar oficial venta. Devuelve None si la API falla."""
    try:
        resp = requests.get(DOLARAPI_URL, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        venta = data.get("venta")
        if venta and float(venta) > 0:
            return float(venta)
        return None
    except Exception as e:
        logger.warning("Exchange rate fetch failed", error=str(e))
        return None


def get_config(db: Session) -> ExchangeRateConfig:
    """Obtiene (o crea) la fila única de configuración de cotización."""
    config = db.query(ExchangeRateConfig).filter(ExchangeRateConfig.id == 1).first()
    if config is None:
        config = ExchangeRateConfig(id=1, mode="auto")
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def invalidate_cache() -> None:
    """Fuerza re-fetch en la próxima consulta (al cambiar config desde el backoffice)."""
    _cache["ts"] = 0.0


def get_current_rate(db: Session) -> Dict:
    """
    Cotización vigente USD→ARS.

    Returns dict: { rate, mode, source, updated_at }
    """
    config = get_config(db)

    # Modo manual: valor fijo configurado por el operador.
    if config.mode == "manual" and config.manual_rate and config.manual_rate > 0:
        return {
            "rate": float(config.manual_rate),
            "mode": "manual",
            "source": "Manual (configurado)",
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    # Modo auto: cache en proceso vigente → usarla sin pegarle a la API.
    now = time.time()
    if _cache["rate"] > 0 and (now - _cache["ts"]) < _CACHE_TTL:
        return {
            "rate": _cache["rate"],
            "mode": "auto",
            "source": config.source or "Oficial (dolarapi)",
            "updated_at": config.cached_at.isoformat() if config.cached_at else None,
        }

    # Cache vencida: intentar API.
    fresh = fetch_official_rate()
    if fresh:
        _cache["rate"] = fresh
        _cache["ts"] = now
        config.cached_rate = fresh
        config.cached_at = datetime.now()
        config.source = "Oficial (dolarapi)"
        db.commit()
        return {
            "rate": fresh,
            "mode": "auto",
            "source": "Oficial (dolarapi)",
            "updated_at": config.cached_at.isoformat(),
        }

    # API falló: última cotización cacheada en DB.
    if config.cached_rate and config.cached_rate > 0:
        _cache["rate"] = config.cached_rate
        _cache["ts"] = now
        return {
            "rate": float(config.cached_rate),
            "mode": "auto",
            "source": (config.source or "Oficial (dolarapi)") + " · cacheada",
            "updated_at": config.cached_at.isoformat() if config.cached_at else None,
        }

    # Nunca hubo cotización: fallback final.
    return {
        "rate": DEFAULT_RATE,
        "mode": "auto",
        "source": "Valor por defecto",
        "updated_at": None,
    }


def convert(amount: float, from_ccy: str, to_ccy: str, db: Session) -> Optional[float]:
    """Convierte `amount` de `from_ccy` a `to_ccy` (Tarea B).

    Hoy la única cotización disponible es USD↔ARS (dolarapi). Para ese par convierte con
    get_current_rate; para el mismo par (from==to) devuelve el monto; para CUALQUIER OTRO par
    devuelve None (no inventa una cotización que no existe — el llamador cae a su fallback).
    Cuando se sumen más fuentes de cotización, se extiende acá sin tocar a los llamadores.
    """
    if amount is None:
        return None
    f = (from_ccy or "").upper()
    t = (to_ccy or "").upper()
    if f == t:
        return float(amount)
    rate = get_current_rate(db).get("rate") or 0.0
    if rate <= 0:
        return None
    if f == "USD" and t == "ARS":
        return round(float(amount) * rate, 2)
    if f == "ARS" and t == "USD":
        return round(float(amount) / rate, 2)
    return None  # par sin cotización disponible
