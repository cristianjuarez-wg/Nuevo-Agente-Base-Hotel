"""
Keywords para clasificación de urgencia y escalación
Centralizado desde postsale_service.py y escalation_analyzer.py
"""

# Keywords para prioridad urgente
URGENT_KEYWORDS = [
    "urgente", "emergencia", "ahora", "inmediato", "ya",
    "perdido", "perdí", "perdí", "robo", "robado", "robaron",
    "accidente", "hospital", "policía",
    "cancelado", "no llegó", "no aparece"
]

# Keywords para prioridad alta
HIGH_KEYWORDS = [
    "hoy", "mañana", "problema", "error", "no funciona",
    "no puedo", "ayuda", "necesito"
]

# Keywords que indican necesidad de escalación
ESCALATION_KEYWORDS = [
    # Problemas graves
    "no llegó", "no apareció", "perdido", "robado",
    "accidente", "hospital", "policía", "emergencia",
    
    # Insatisfacción
    "queja", "reclamo", "mal servicio", "pésimo",
    "horrible", "desastre", "inaceptable",
    
    # Cambios importantes
    "cancelar", "cancelación", "cambiar reserva",
    "modificar viaje", "reprogramar",
    
    # Problemas de servicio
    "no funciona", "roto", "sucio", "malo",
    "no corresponde", "diferente a lo prometido"
]

# Keywords de estado de vuelos (para monitoreo)
FLIGHT_STATUS_KEYWORDS = [
    "estado", "cambios", "retrasado", "delay",
    "cancelado", "puerta", "gate", "terminal", "problema"
]

# Keywords de consulta de información (NO requieren escalación)
INFORMATION_KEYWORDS = [
    "información", "detalle", "cuándo", "dónde",
    "qué incluye", "horario", "dirección", "teléfono",
    "contacto", "cómo llegar"
]
