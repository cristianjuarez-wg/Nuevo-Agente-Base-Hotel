"""
Agente casual — generación de respuestas de conversación social (saludos, charla).

Extraído de agent_service.py (deuda Fase 2.3): es lógica autocontenida del agente casual,
no coordinación. agent_service delega acá desde _chat_impl. Comportamiento byte-idéntico al
original; las funciones reciben `client`/`db` explícitos en vez de leerlos de `self`.
"""
from typing import List, Dict, Optional

from app.config import settings
from app.core.observability.logging_config import get_logger
from app.core.llm.sdk_usage import usage_from_completion

logger = get_logger(__name__)


def build_casual_guest_block(db, session_id: str) -> str:
    """Perfil del huésped conocido para personalizar el saludo casual (nivel guest = 360).

    Delega en guest_context_service (helper único con niveles por rol, Fase 1). Bloque idéntico
    al anterior para un huésped sin ai_summary; con ai_summary suma una línea. Nunca rompe el turno.
    """
    from app.services import guest_context_service
    contact_id = guest_context_service.resolve_contact_id(session_id, None, db)
    return guest_context_service.build_guest_context("guest", contact_id, db)


def build_team_roster_block(db) -> str:
    """Roster del EQUIPO real para el prompt casual.

    Fase 0.1: la construcción vive en base_blocks (única fuente, compartida con
    pre-venta y post-venta para la regla anti-invención de personas).
    """
    from app.domains.hotel.prompts.base_blocks import build_team_roster_block as _build
    return _build(db)


async def should_capture_lead_in_casual(db, message: str, session_id: str, history) -> bool:
    """True si en un turno casual (típicamente despedida) conviene captar el contacto.

    Corre el mismo análisis de lead que pre-venta; devuelve la decisión de captar
    (incluye el "momento de cierre" por despedida). False si el lead ya tiene contacto
    o si no aplica. Nunca rompe el turno.
    """
    try:
        from app.services.lead_service import lead_service

        lead = lead_service._get_or_create_lead(db, session_id)
        if lead.is_complete_lead():
            return False
        _, should_request = await lead_service.process_message_for_lead(
            db, message, session_id, history, "", {}
        )
        return should_request
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo evaluar captación de lead en casual", error=str(e))
        return False


def availability_shown_in_session(db, session_id: str) -> bool:
    """True si en esta sesión la pre-venta ya mostró disponibilidad real (flag en
    Conversation.extra_metadata). Permite al cierre casual ir directo a captar el
    contacto en vez de re-ofrecer disponibilidad ya vista. Best-effort."""
    try:
        from app.models.conversation import Conversation
        conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
        return bool(conv and (conv.extra_metadata or {}).get("availability_shown"))
    except Exception:  # noqa: BLE001
        return False


async def generate_casual_response(client, message: str, history: List[Dict],
                                   language: str = "es", guest_block: str = "",
                                   capture_lead: bool = False,
                                   availability_shown: bool = False,
                                   is_whatsapp: bool = False,
                                   team_block: str = "",
                                   profile: Optional[dict] = None) -> tuple[str, Dict]:
    """
    Genera respuesta natural para conversación casual.

    Args:
        client: cliente AsyncOpenAI compartido.
        message: Mensaje del usuario
        history: Historial de conversación
        language: idioma de respuesta (es | en | pt | fr)
        guest_block: contexto del huésped conocido (perfil 360°) para personalizar
            el saludo cuando es un huésped recurrente/alojado. Vacío si es nuevo.

    Returns:
        (respuesta amigable, usage) — usage con los tokens consumidos.
    """
    from app.domains.hotel.prompts.generation_prompts import CASUAL_RESPONSE_SYSTEM

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": settings.OPENAI_MODEL}
    try:
        # Formatear historial
        history_context = ""
        if history:
            recent = history[-4:]
            history_context = "\n".join([
                f"{'Usuario' if msg['role'] == 'user' else 'Asistente'}: {msg['content'][:200]}"
                for msg in recent
            ])

        history_section = f"Historial de la conversación:\n{history_context}" if history_context else ""
        from app.domains.hotel.prompts.generation_prompts import (
            CASUAL_LEAD_CAPTURE_HINT, CASUAL_LEAD_CAPTURE_HINT_AFTER_AVAILABILITY,
            NATURALIDAD_BLOCK,
        )
        # Si hay que captar y ya se mostró disponibilidad, vamos directo al contacto
        # (sin re-ofrecer disponibilidad ya rechazada). Si no, el cierre estándar.
        # En WhatsApp usamos siempre el hint AFTER_AVAILABILITY: ya tenemos el teléfono
        # (viene en el session_id), así que pedimos SOLO el nombre y confirmamos que le
        # escribimos a este mismo número — sin re-pedir un dato que ya conocemos.
        if capture_lead:
            if is_whatsapp or availability_shown:
                lead_hint = CASUAL_LEAD_CAPTURE_HINT_AFTER_AVAILABILITY
            else:
                lead_hint = CASUAL_LEAD_CAPTURE_HINT
        else:
            lead_hint = ""
        from app.domains.hotel.prompts.identity_blocks import (
            build_casual_identity_block, build_facts_block,
        )
        prof = profile or {}
        # Naturalidad opt-in por customer_facing (Fase 3): casual es customer_facing → lo recibe.
        from app.domains.hotel.agent_specs import SPECS
        _casual_cf = SPECS["casual"].customer_facing
        prompt = CASUAL_RESPONSE_SYSTEM.format(
            identity_block=build_casual_identity_block(prof),
            facts_block=build_facts_block(prof),  # HECHOS del negocio (Fase A → casual)
            naturalidad_block=NATURALIDAD_BLOCK if _casual_cf else "",
            team_block=team_block,
            history_section=history_section,
            message=message,
            lead_capture_hint=lead_hint,
            negocio=prof.get("business_name") or "el hotel",  # límite de dominio (Fase A)
            ciudad=prof.get("city") or "la ciudad",
        )
        # Si conocemos al huésped (recurrente/alojado), anteponemos su perfil para que
        # el saludo lo reconozca por su nombre en vez de tratarlo como desconocido.
        if guest_block:
            prompt = guest_block + "\n" + prompt
        from app.domains.hotel.prompts.context_blocks import build_language_block
        lang_block = build_language_block(language)
        if lang_block:
            prompt = prompt + "\n" + lang_block

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,  # Más creativo para conversación casual
            max_tokens=220  # margen para una respuesta cálida sin cortarla a mitad
        )

        casual_response = response.choices[0].message.content.strip()
        usage = usage_from_completion(response, model=settings.OPENAI_MODEL)

        logger.info("Casual response generated",
                   message=message[:50],
                   response_length=len(casual_response))

        return casual_response, usage

    except Exception as e:
        logger.error("Error generating casual response",
                    error=str(e),
                    message=message[:50])
        # Fallback genérico
        return "¡Hola! 😊 ¿En qué puedo ayudarte con tu estadía en el hotel?", usage
