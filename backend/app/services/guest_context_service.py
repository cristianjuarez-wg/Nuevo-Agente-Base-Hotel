"""
Contexto del huésped (Capa 2) inyectable en el prompt, con NIVELES DE ACCESO POR ROL.

Único punto donde se decide QUÉ datos del huésped ve cada agente en su prompt (política de
privacidad centralizada). Antes esta lógica estaba duplicada en pre-venta
(`hotel_sdk_orchestrator._build_guest_block`) y casual (`casual_agent.build_casual_guest_block`);
ahora ambos —y el post-venta y el staff— pasan por acá.

Niveles (Fase 1):
  guest      → perfil 360 completo (estadías, recurrencia, preferencias, consumo) + ai_summary.
  management → VACÍO. Gerencia no ve huésped individual en el prompt. (La tool buscar_huesped
               sí devuelve datos de una reserva puntual cuando el dueño la invoca a propósito:
               eso es una acción deliberada, no una inyección pasiva — ver AGENT_REUSE.md.)
  staff      → MÍNIMO: nombre + habitación del ticket. Nada comercial (sin gasto, sin consumo,
               sin recurrencia, sin preferencias de venta).

Nunca rompe el turno: ante cualquier error devuelve "" con un warning (igual que los helpers
que reemplaza).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.observability.logging_config import get_logger
from app.utils.channel_utils import is_whatsapp_session, phone_from_session

logger = get_logger(__name__)


def resolve_contact_id(session_id: str, lead, db: Session) -> Optional[int]:
    """Resuelve el contact_id de una sesión (lógica antes duplicada en pre-venta y casual).

    Orden: lead.contact_id → teléfono del session_id de WhatsApp → Lead de la sesión.
    """
    try:
        contact_id = getattr(lead, "contact_id", None) if lead is not None else None
        if not contact_id and session_id and is_whatsapp_session(session_id):
            from app.models.contact import Contact
            phone = phone_from_session(session_id)
            c = db.query(Contact).filter(Contact.phone_number == phone).first()
            contact_id = c.id if c else None
        if not contact_id and session_id:
            from app.models.lead import Lead
            row = db.query(Lead).filter(Lead.session_id == session_id).first()
            contact_id = row.contact_id if row else None
        return contact_id
    except Exception as e:  # noqa: BLE001 — resolver el contacto nunca debe romper el turno
        logger.warning("No se pudo resolver el contact_id", error=str(e))
        return None


def _guest_full_block(contact_id: int, db: Session) -> str:
    """Perfil 360 completo para Aura (guest). Paridad con el bloque anterior + ai_summary."""
    from app.services.contact_service import contact_service
    from app.domains.hotel.prompts.context_blocks import build_guest_profile_block

    profile = contact_service.get_guest_profile(contact_id, db)
    # Solo personalizamos si hay algo que contar (estadías o preferencias) — paridad con hoy.
    if not profile or (not profile.get("stays_count") and not profile.get("preferences")):
        return ""
    return build_guest_profile_block(profile)


def _staff_min_block(contact_id: int, db: Session) -> str:
    """Nivel MÍNIMO para operaciones: nombre + habitación. Nada comercial."""
    from app.services.contact_service import contact_service
    from app.domains.hotel.prompts.context_blocks import build_staff_guest_block

    profile = contact_service.get_guest_profile(contact_id, db)
    if not profile:
        return ""
    return build_staff_guest_block(profile)


def build_guest_context(agent_role: str, contact_id: Optional[int], db: Session) -> str:
    """Bloque de contexto del huésped para el prompt, FILTRADO POR ROL.

    agent_role: "guest" | "management" | "staff" (el display_role del AgentSpec).
    Devuelve el texto del bloque ya renderizado, o "" si no corresponde / no hay datos.
    """
    # management: nunca datos individuales en el prompt (privacidad de gerencia).
    if agent_role == "management":
        return ""
    if not contact_id:
        return ""
    try:
        if agent_role == "staff":
            return _staff_min_block(contact_id, db)
        # guest (Aura: pre-venta, post-venta, casual) → 360 completo.
        return _guest_full_block(contact_id, db)
    except Exception as e:  # noqa: BLE001 — la personalización nunca debe romper el turno
        logger.warning("No se pudo armar el guest context", role=agent_role, error=str(e))
        return ""
