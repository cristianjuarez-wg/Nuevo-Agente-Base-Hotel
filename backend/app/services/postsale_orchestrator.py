"""
Acción determinística sobre el ticket de post-venta.

El loop de tool calling de post-venta lo ejecuta el Agents SDK
(`postsale_sdk_orchestrator`). Lo único que vive acá es `_apply_ticket_action`:
la aplicación DETERMINÍSTICA de la acción sobre el ticket (escalar/resolver) según
el análisis recogido en el contexto — NO la decide el LLM libremente. El SDK
orchestrator la reutiliza tras correr el loop.

(El orquestador casero de tool calling — loop + system prompt — fue retirado en P4:
el camino de producción es el Agents SDK.)
"""
from typing import Dict, Optional

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class PostSaleOrchestrator:
    """Acción determinística sobre el ticket de post-venta (reusada por el SDK orchestrator)."""

    def _apply_ticket_action(
        self, service, ticket, requires_escalation: bool,
        response_text: str, message: str, escalation: Optional[Dict]
    ) -> str:
        """Aplica de forma determinística la acción sobre el ticket, reusando los métodos del service."""
        try:
            # Registrar la interacción del usuario y la respuesta del agente
            service._save_interaction(
                ticket=ticket, message=message, interaction_type="user_message",
                created_by="cliente", requires_escalation=requires_escalation,
            )
            if requires_escalation:
                reason = (escalation or {}).get("escalation_reason", "Requiere intervención humana")
                service.escalate_ticket(ticket, reason)
                # Marcar flags de issues escalados (paridad con handle_message legacy)
                ticket.has_escalated_issues = True
                ticket.escalated_issues_count = (ticket.escalated_issues_count or 0) + 1
                service.db.commit()
                # La respuesta empática al cliente va como agent_response (es lo que ve el usuario)
                # escalate_ticket() ya guardó la nota de sistema como "escalation"
                service._save_interaction(
                    ticket=ticket, message=response_text, interaction_type="agent_response",
                    created_by="Kami (Agente IA)", requires_escalation=True,
                )
                return "escalated"
            else:
                service.add_agent_response(ticket.ticket_number, response_text)
                # Marcar resuelto solo si no hay issues escalados previos en el ticket
                if not getattr(ticket, "has_escalated_issues", False):
                    service.resolve_ticket(ticket, response_text, auto_resolved=True)
                return "auto_resolving"
        except Exception as e:
            logger.error("Error applying ticket action", error=str(e),
                         ticket=getattr(ticket, "ticket_number", None))
            return "error"


# Instancia global
postsale_orchestrator = PostSaleOrchestrator()
