"""
Estados válidos para diferentes entidades del sistema
"""

# Estados de tickets de soporte
TICKET_STATUS = {
    "open": {
        "label": "Abierto",
        "color": "blue",
        "can_transition_to": ["in_progress", "waiting_customer", "resolved", "closed"]
    },
    "in_progress": {
        "label": "En Progreso",
        "color": "orange",
        "can_transition_to": ["waiting_customer", "resolved", "closed", "open"]
    },
    "waiting_customer": {
        "label": "Esperando Cliente",
        "color": "purple",
        "can_transition_to": ["in_progress", "resolved", "closed"]
    },
    "resolved": {
        "label": "Resuelto",
        "color": "green",
        "can_transition_to": ["closed", "open"]  # Puede reabrirse
    },
    "closed": {
        "label": "Cerrado",
        "color": "gray",
        "can_transition_to": ["open"]  # Solo puede reabrirse
    }
}

# Estados de leads
LEAD_STATUS = {
    "new": {
        "label": "Nuevo",
        "color": "blue",
        "stage": "initial"
    },
    "contacted": {
        "label": "Contactado",
        "color": "yellow",
        "stage": "engaged"
    },
    "qualified": {
        "label": "Calificado",
        "color": "orange",
        "stage": "qualified"
    },
    "proposal": {
        "label": "Propuesta",
        "color": "purple",
        "stage": "proposal"
    },
    "won": {
        "label": "Ganado",
        "color": "green",
        "stage": "closed_won"
    },
    "lost": {
        "label": "Perdido",
        "color": "red",
        "stage": "closed_lost"
    },
    "active": {
        "label": "Activo",
        "color": "blue",
        "stage": "active"
    }
}

# Estados de viaje/paquete
TRIP_STATUS = {
    "confirmed": {
        "label": "Confirmado",
        "color": "green",
        "description": "Reserva confirmada y pagada"
    },
    "in_progress": {
        "label": "En Curso",
        "color": "blue",
        "description": "Viaje en progreso"
    },
    "completed": {
        "label": "Completado",
        "color": "gray",
        "description": "Viaje finalizado"
    },
    "cancelled": {
        "label": "Cancelado",
        "color": "red",
        "description": "Reserva cancelada"
    },
    "pending": {
        "label": "Pendiente",
        "color": "yellow",
        "description": "Pendiente de confirmación"
    }
}

# Tipos de interacción en tickets
INTERACTION_TYPES = {
    "user_message": "Mensaje del cliente",
    "agent_response": "Respuesta del agente IA",
    "operator_comment": "Comentario del operador",
    "operator_action": "Acción del operador",
    "system_event": "Evento del sistema",
    "escalation": "Escalación"
}
