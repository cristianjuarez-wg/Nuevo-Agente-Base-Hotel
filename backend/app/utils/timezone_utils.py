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
