# Models package
# Importar en orden para resolver dependencias
from app.models.learning_opportunity import LearningOpportunity
from app.models.agent_snapshot import AgentSnapshot
from app.models.provider import Provider
from app.models.postsale import (
    TourPackage,
    SharedFlight,
    SoldPackage,
    PackagePassenger,
    PackageFlight,
    PackageAccommodation,
    PackageTransfer,
    PackageActivity,
    PackageDocument,
    PackageItinerary,
    SupportTicket,
    TicketInteraction,
    PostSaleSession
)

__all__ = [
    'LearningOpportunity',
    'AgentSnapshot',
    'Provider',
    'TourPackage',
    'SharedFlight',
    'SoldPackage',
    'PackagePassenger',
    'PackageFlight',
    'PackageAccommodation',
    'PackageTransfer',
    'PackageActivity',
    'PackageDocument',
    'PackageItinerary',
    'SupportTicket',
    'TicketInteraction',
    'PostSaleSession'
]
