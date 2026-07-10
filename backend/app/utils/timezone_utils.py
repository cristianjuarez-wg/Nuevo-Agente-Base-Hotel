"""
Utilidades de zona horaria del NEGOCIO.

Fase 1.3: el timezone deja de estar hardcodeado en Argentina y se lee del
BusinessProfile (`timezone`). `now_business()`/`iso_business()` son las funciones
canónicas; `now_argentina()`/`iso_argentina()` quedan como ALIAS delegantes para no
romper los ~21 call-sites existentes (se migran con sed en un paso aparte).

Fallback robusto: si el perfil no está disponible (arranque, o import temprano), se usa
la zona de Argentina — el comportamiento histórico, así nada se rompe.
"""
from datetime import datetime, timezone
import pytz


def utcnow_naive() -> datetime:
    """UTC naive — reemplazo EXACTO de datetime.utcnow() sin la deprecación (P4).

    Devuelve la hora UTC como datetime naive (sin tzinfo), idéntico a lo que devolvía
    datetime.utcnow(). NO confundir con now_business(), que devuelve la hora LOCAL del negocio:
    este helper es para timestamps de auditoría/DB (UTC), no para mostrar al usuario.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Zona por defecto (fallback y compatibilidad): Argentina.
ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# Caché del objeto tzinfo del negocio, para no reconstruirlo en cada llamada.
_business_tz_cache = None
_business_tz_name = None


def _business_tz():
    """tzinfo del negocio, leído del BusinessProfile (cacheado). Fallback: Argentina.

    Import diferido de business_profile_service para evitar ciclos de import (este
    módulo es de bajo nivel y lo importa media app).
    """
    global _business_tz_cache, _business_tz_name
    if _business_tz_cache is not None:
        return _business_tz_cache
    try:
        from app.services import business_profile_service
        from app.models.database import SessionLocal
        _db = SessionLocal()
        try:
            tz_name = business_profile_service.get_profile(_db).get("timezone")
        finally:
            _db.close()
        _business_tz_name = tz_name or "America/Argentina/Buenos_Aires"
        _business_tz_cache = pytz.timezone(_business_tz_name)
    except Exception:
        # DB no lista / perfil ausente → Argentina (comportamiento histórico).
        _business_tz_cache = ARGENTINA_TZ
    return _business_tz_cache


def invalidate_tz_cache():
    """Descarta el tz cacheado (llamar si el perfil cambia de timezone)."""
    global _business_tz_cache, _business_tz_name
    _business_tz_cache = None
    _business_tz_name = None


def now_business():
    """Fecha/hora actual en la zona horaria del NEGOCIO (naive, para compat SQLite)."""
    return datetime.now(_business_tz()).replace(tzinfo=None)


def now_argentina():
    """ALIAS deprecado de now_business() (Fase 1.3). Migrar call-sites y luego borrar."""
    return now_business()

def iso_business(dt, source="utc"):
    """Serializa un datetime a ISO 8601 en la zona del NEGOCIO, con offset explícito.

    Pensado para la capa de API: el frontend recibe una fecha inequívoca ya en hora local
    del negocio, sin importar en qué zona guardó la base.

    Args:
        dt: datetime (normalmente naive) o None.
        source: zona en que está guardado `dt`:
            - "utc" (default): la fecha está en UTC (datetime.utcnow en Render).
            - "ar"/"business": la fecha YA está en hora del negocio (modelos que usan
              now_business). No se le resta nada, solo se le pone el offset.

    Returns:
        String ISO con offset (ej. "2026-06-25T15:09:03-03:00") o None.
    """
    if dt is None:
        return None
    tz = _business_tz()
    if dt.tzinfo is None:
        if source in ("ar", "business"):
            dt = tz.localize(dt)
        else:  # "utc"
            dt = pytz.utc.localize(dt)
    return dt.astimezone(tz).isoformat()


def iso_argentina(dt, source="utc"):
    """ALIAS deprecado de iso_business() (Fase 1.3)."""
    return iso_business(dt, source=source)


def to_argentina(utc_datetime):
    """
    Convierte un datetime UTC a hora Argentina
    
    Args:
        utc_datetime: datetime en UTC
        
    Returns:
        datetime en hora Argentina (sin tzinfo para compatibilidad con SQLite)
    """
    if utc_datetime is None:
        return None
    
    if utc_datetime.tzinfo is None:
        # Asumir que es UTC si no tiene timezone
        utc_datetime = pytz.utc.localize(utc_datetime)
    
    argentina_time = utc_datetime.astimezone(ARGENTINA_TZ)
    return argentina_time.replace(tzinfo=None)

def argentina_datetime(*args, **kwargs):
    """
    Crea un datetime en zona horaria Argentina
    
    Ejemplo:
        argentina_datetime(2025, 11, 6, 11, 20)  # 6 nov 2025, 11:20 AM Argentina
    """
    naive_dt = datetime(*args, **kwargs)
    return ARGENTINA_TZ.localize(naive_dt).replace(tzinfo=None)

def format_argentina_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """
    Formatea un datetime en hora Argentina
    
    Args:
        dt: datetime a formatear
        format_str: formato de salida
        
    Returns:
        string formateado
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Ya está en hora Argentina
        return dt.strftime(format_str)
    
    # Convertir a Argentina primero
    argentina_time = to_argentina(dt)
    return argentina_time.strftime(format_str)
