"""
Categorías de tickets y sus keywords asociadas
Centralizado desde postsale_service.py, escalation_analyzer.py, intent_classifier.py
"""

# Categorías de tickets con sus keywords
CATEGORY_KEYWORDS = {
    "emergency": ["emergencia", "urgente", "crítico"],
    "service_failure": ["no llegó", "no apareció", "falla"],
    "complaint": ["queja", "reclamo", "mal servicio", "insatisfecho"],
    "flight": ["vuelo", "avión", "aerolínea", "boarding", "check-in", "equipaje"],
    "hotel": ["hotel", "habitación", "alojamiento", "reserva hotel", "check in hotel"],
    "transfer": ["traslado", "transfer", "transporte", "pickup", "conductor"],
    "activity": ["excursión", "actividad", "tour", "guía", "visita"],
    "documentation": ["voucher", "documento", "confirmación", "ticket", "boleto", "pasaporte"],
    "information": ["información", "detalle", "cuándo", "dónde", "qué incluye"],
    "change": ["cambio", "cambiar", "modificar", "modificación", "cancelar", "cancelación", "reprogramar"],
    "general": ["consulta", "pregunta", "ayuda"]
}

# Prioridades de categorías (para actualización dinámica de tickets)
CATEGORY_PRIORITY = {
    "emergency": 10,          # Máxima prioridad
    "service_failure": 9,
    "complaint": 8,
    "change": 7,
    "flight": 6,
    "hotel": 5,
    "transfer": 4,
    "activity": 3,
    "documentation": 2,
    "information": 1,
    "general": 0              # Mínima prioridad
}

# Lista de categorías válidas
TICKET_CATEGORIES = list(CATEGORY_KEYWORDS.keys())
