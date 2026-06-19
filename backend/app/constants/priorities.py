"""
Niveles de prioridad y urgencia para tickets
"""

# Niveles de prioridad de tickets
PRIORITY_LEVELS = {
    "urgent": {
        "value": 4,
        "label": "Urgente",
        "color": "red",
        "sla_hours": 2
    },
    "high": {
        "value": 3,
        "label": "Alta",
        "color": "orange",
        "sla_hours": 8
    },
    "medium": {
        "value": 2,
        "label": "Media",
        "color": "yellow",
        "sla_hours": 24
    },
    "low": {
        "value": 1,
        "label": "Baja",
        "color": "blue",
        "sla_hours": 72
    }
}

# Niveles de urgencia (para análisis de escalación)
URGENCY_LEVELS = {
    "critical": {
        "value": 4,
        "requires_immediate_action": True,
        "auto_escalate": True
    },
    "high": {
        "value": 3,
        "requires_immediate_action": False,
        "auto_escalate": True
    },
    "medium": {
        "value": 2,
        "requires_immediate_action": False,
        "auto_escalate": False
    },
    "low": {
        "value": 1,
        "requires_immediate_action": False,
        "auto_escalate": False
    }
}

# Mapeo de urgencia a prioridad
URGENCY_TO_PRIORITY = {
    "critical": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low"
}
