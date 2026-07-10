# Models package.
# Fase 0.2: se retiraron los modelos de turismo (postsale/paquetes, provider, etc.).
#
# NO importamos todos los modelos acá: el barrido de imports lo hacen los puntos de entrada
# (main.py en el server; conftest.py en los tests), con el ORDEN correcto de create_all.
# Importar modelos con create_all a nivel de módulo desde este __init__ rompería ese orden
# (dispararía create_all contra el engine equivocado en el entorno de test). El registro de
# mappers para relationships cross-módulo se garantiza en ensure_domain_models_registered().
from app.models.agent_snapshot import AgentSnapshot

__all__ = ["AgentSnapshot", "ensure_domain_models_registered"]


def ensure_domain_models_registered() -> None:
    """Importa (registra) los modelos de dominio cuyas relationships se declaran por STRING.

    Necesario para que SQLAlchemy resuelva referencias como Booking.extra_charges →
    "ExtraCharge" (restaurant.py) o HotelTicket → "StaffMember" (staff.py). Sin esto,
    consultar un Booking/HotelTicket revienta con "name X is not defined" y el gate de
    post-venta cae a pre-venta (regresión detectada por las evals tras la Fase 0.2).

    Idempotente: importar un módulo ya importado es un no-op. Se llama en el startup del
    server (main.py). Los tests ya hacen su propio barrido en conftest.
    """
    from app.models import staff  # noqa: F401  (StaffMember, antes que hotel)
    from app.models import restaurant  # noqa: F401  (ExtraCharge, Voucher, etc.)
    from app.models import hotel  # noqa: F401  (Booking, HotelTicket)
    from app.models import contact  # noqa: F401
    from app.models import lead  # noqa: F401
    from app.models import lead_message  # noqa: F401
    from app.models import conversation  # noqa: F401
    from app.models import conversation_message  # noqa: F401  (Conversation→ConversationMessage)
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
