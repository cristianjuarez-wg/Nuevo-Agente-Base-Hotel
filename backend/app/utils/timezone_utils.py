"""
Utilidades para manejo de zona horaria Argentina
Todo el sistema usa hora de Buenos Aires (UTC-3)
"""
from datetime import datetime
import pytz

# Zona horaria de Argentina
ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

def now_argentina():
    """
    Retorna la fecha/hora actual de Argentina
    Reemplaza datetime.utcnow() en todo el sistema
    """
    return datetime.now(ARGENTINA_TZ).replace(tzinfo=None)

def iso_argentina(dt, source="utc"):
    """Serializa un datetime a ISO 8601 en hora Argentina, CON offset explícito (-03:00).

    Pensado para la capa de API: garantiza que el frontend reciba una fecha inequívoca y
    ya en hora local de Argentina, sin importar en qué zona guardó la base.

    Args:
        dt: datetime (normalmente naive) o None.
        source: zona en que está guardado `dt`:
            - "utc" (default): la fecha está en UTC (datetime.utcnow / datetime.now en Render).
            - "ar": la fecha YA está en hora Argentina (modelos que usan now_argentina:
              Lead, postsale.*, provider.*). No se le resta nada, solo se le pone el offset.

    Returns:
        String ISO con offset (ej. "2026-06-25T15:09:03-03:00") o None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        if source == "ar":
            dt = ARGENTINA_TZ.localize(dt)
        else:  # "utc"
            dt = pytz.utc.localize(dt)
    return dt.astimezone(ARGENTINA_TZ).isoformat()


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
