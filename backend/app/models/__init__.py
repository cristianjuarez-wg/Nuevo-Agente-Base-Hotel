# Models package.
# Fase 0.2: se retiraron los modelos de turismo (postsale/paquetes, provider,
# flight_tracking, airport_terminal, geography, learning_opportunity). El resto de los
# modelos se autoimporta donde se usa; acá solo queda lo que otros módulos consumían
# vía `app.models`.
from app.models.agent_snapshot import AgentSnapshot

__all__ = [
    'AgentSnapshot',
]
