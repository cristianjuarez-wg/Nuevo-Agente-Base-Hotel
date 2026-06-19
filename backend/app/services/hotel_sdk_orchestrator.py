"""
Orquestador de PRE-VENTA del HOTEL sobre el OpenAI Agents SDK.

Clon adaptado de agent_sdk_orchestrator.py (Freeway). Mismo contrato público
`run(db, message, session_id, history) -> Dict`. Cambios respecto a Freeway:
  - Tools de HOTEL (info_hotel, consultar_disponibilidad, crear_reserva, consultar_reserva)
    vía hotel_tools.execute_tool.
  - Sin obtener_clima ni guardrail de países disponibles (eran de turismo).
  - Prompt de concierge hotelero (HOTEL_AGENT_SYSTEM).

Conserva del original: análisis de lead transversal, input guardrail anti-jailbreak,
catch genérico anti-500, extracción de tools_used, max_turns.
"""
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from agents import (
    Agent,
    Runner,
    RunContextWrapper,
    function_tool,
    input_guardrail,
    GuardrailFunctionOutput,
    ModelSettings,
    OpenAIChatCompletionsModel,
    set_default_openai_client,
    set_tracing_disabled,
    set_tracing_export_api_key,
)

from app.config import settings
from app.utils.timezone_utils import now_argentina
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai
from app.services.lead_service import lead_service
from app.services.rag_service import rag_service
from app.services.hotel_tools import execute_tool
from app.prompts.tool_agent_prompts import TOOL_AGENT_SYSTEM
from app.prompts.context_blocks import (
    build_lead_context_block,
    build_contact_request_block,
)

logger = get_logger(__name__)

MAX_TURNS = 6
MAX_HISTORY_MESSAGES = 20

# Cliente OpenAI compartido por el SDK (singleton del proyecto).
_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# CONTEXTO POR TURNO
# ---------------------------------------------------------------------------
class HotelContext:
    """Contexto mutable de un turno de pre-venta del hotel.

    Lleva db/message/history para las tools y recoge document_sources (RAG) que el
    orquestador necesita para armar la respuesta final.
    """

    def __init__(self, db: Session, message: str, history: List[Dict]):
        self.db = db
        self.message = message
        self.history = history
        self.document_sources: List = []

    def as_tool_ctx(self) -> Dict:
        return {
            "db": self.db,
            "message": self.message,
            "history": self.history,
            "document_sources": self.document_sources,
        }

    def absorb(self, tool_ctx: Dict):
        self.document_sources = tool_ctx.get("document_sources", self.document_sources)


# ---------------------------------------------------------------------------
# TOOLS — envuelven los handlers de hotel_tools.execute_tool
# ---------------------------------------------------------------------------
@function_tool
async def info_hotel(ctx: RunContextWrapper[HotelContext], query: str) -> str:
    """Consulta información del hotel: habitaciones, servicios, instalaciones, ubicación,
    políticas (check-in/out, mascotas, estacionamiento), promociones y amenities.
    Úsala SIEMPRE que el usuario pregunte sobre el hotel, sus comodidades o servicios.
    Es la única fuente de información oficial del hotel: no inventes datos."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("info_hotel", {"query": query}, tool_ctx)
    ctx.context.absorb(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def consultar_disponibilidad(
    ctx: RunContextWrapper[HotelContext],
    check_in: str,
    check_out: str,
    guests: int = 1,
) -> str:
    """Consulta qué tipos de habitación están disponibles para un rango de fechas y
    cantidad de huéspedes, con el precio total en USD y ARS. Úsala SIEMPRE que el usuario
    quiera reservar o pregunte por disponibilidad/precios para fechas concretas.
    Las fechas deben estar en formato YYYY-MM-DD."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "consultar_disponibilidad",
        {"check_in": check_in, "check_out": check_out, "guests": guests},
        tool_ctx,
    )
    return result.get("tool_result", "")


@function_tool
async def crear_reserva(
    ctx: RunContextWrapper[HotelContext],
    room_type: str,
    check_in: str,
    check_out: str,
    guest_name: str,
    guest_email: str = "",
    guest_phone: str = "",
    guests: int = 1,
) -> str:
    """Crea una reserva confirmada y devuelve el código de reserva (HTL-XXXX).
    Llamala SOLO cuando ya tengas TODOS estos datos confirmados por el usuario:
    tipo de habitación, check_in, check_out (YYYY-MM-DD) y nombre del huésped.
    Si falta algún dato, pedíselo al usuario ANTES de llamar a esta herramienta.
    El pago de la demo se simula como pagado al confirmar."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool(
        "crear_reserva",
        {
            "room_type": room_type,
            "check_in": check_in,
            "check_out": check_out,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "guest_phone": guest_phone,
            "guests": guests,
        },
        tool_ctx,
    )
    return result.get("tool_result", "")


@function_tool
async def consultar_reserva(ctx: RunContextWrapper[HotelContext], code: str) -> str:
    """Consulta el estado y los detalles de una reserva existente a partir de su código
    (formato HTL-XXXX). Úsala cuando el usuario quiera ver o confirmar su reserva."""
    tool_ctx = ctx.context.as_tool_ctx()
    result = await execute_tool("consultar_reserva", {"code": code}, tool_ctx)
    return result.get("tool_result", "")


_TOOLS = [info_hotel, consultar_disponibilidad, crear_reserva, consultar_reserva]


# ---------------------------------------------------------------------------
# GUARDRAIL — input anti-jailbreak (mismo patrón que Freeway)
# ---------------------------------------------------------------------------
_JAILBREAK_MARKERS = (
    "ignore previous", "ignora las instrucciones", "system prompt",
    "olvida tus instrucciones", "reveal your prompt", "actúa como",
)


@input_guardrail
async def relevancia_guardrail(
    ctx: RunContextWrapper[HotelContext], agent: Agent, user_input
) -> GuardrailFunctionOutput:
    text = user_input if isinstance(user_input, str) else str(user_input)
    text_lower = text.lower()
    is_jailbreak = any(m in text_lower for m in _JAILBREAK_MARKERS)

    if is_jailbreak:
        logger.warning("Hotel pre-venta input guardrail: possible jailbreak attempt",
                       preview=text_lower[:80])

    return GuardrailFunctionOutput(
        output_info={"jailbreak_suspected": is_jailbreak},
        tripwire_triggered=is_jailbreak,
    )


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class HotelSDKOrchestrator:
    """Loop de tool calling de pre-venta del hotel sobre el OpenAI Agents SDK."""

    def __init__(self):
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )
        if not settings.DEBUG:
            set_tracing_disabled(False)

    def _build_instructions(self, lead_block: str) -> str:
        now = now_argentina()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        hora = now.strftime("%H:%M")

        return TOOL_AGENT_SYSTEM.format(
            agent_name=profile_manager.get_agent_name(),
            fecha_actual=fecha,
            hora_actual=hora,
            lead_block=lead_block,
        )

    async def _build_lead_block(
        self, db: Session, message: str, session_id: str, history: List[Dict]
    ) -> tuple[str, Dict, bool]:
        """Análisis de lead transversal (igual que Freeway, sin geo)."""
        lead = lead_service._get_or_create_lead(db, session_id)
        has_contact_info = lead.is_complete_lead()

        # Sin análisis geográfico: pasamos dict vacío (el lead_service lo tolera).
        lead_analysis, should_request_contact = await lead_service.process_message_for_lead(
            db, message, session_id, history, "", {}
        )

        lead_block = ""
        if has_contact_info:
            contact_name = lead.name or "este usuario"
            details = []
            if lead.name:
                full = f"{lead.name} {lead.last_name}" if lead.last_name else lead.name
                details.append(f"Nombre: {full}")
            if lead.phone:
                details.append(f"Teléfono: {lead.phone}")
            if lead.email:
                details.append(f"Email: {lead.email}")
            lead_block = build_lead_context_block(contact_name, details)
        elif should_request_contact:
            main_interest = lead_analysis.get("main_interest", "tu estadía")
            lead_block = build_contact_request_block(main_interest)

        return lead_block, lead_analysis, should_request_contact

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(
        self, db: Session, message: str, session_id: str, history: List[Dict]
    ) -> Dict:
        """Procesa un turno de pre-venta del hotel con el SDK."""
        start = time.time()

        # 1. Lead analysis transversal → bloque para el prompt
        lead_block, lead_analysis, should_request_contact = await self._build_lead_block(
            db, message, session_id, history
        )

        # 2. Construir el Agent
        instructions = self._build_instructions(lead_block)
        agent = Agent[HotelContext](
            name=profile_manager.get_agent_name(),
            instructions=instructions,
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=settings.OPENAI_TEMPERATURE),
            input_guardrails=[relevancia_guardrail],
        )

        # 3. Contexto del turno
        run_ctx = HotelContext(db, message, history)
        input_list = self._build_input_list(history, message)

        # 4. Ejecutar el loop del SDK
        from agents import InputGuardrailTripwireTriggered

        try:
            result = await Runner.run(
                agent,
                input=input_list,
                context=run_ctx,
                max_turns=MAX_TURNS,
            )
            response_text = result.final_output or ""
            tools_used = [
                item.raw_item.name
                for item in getattr(result, "new_items", [])
                if getattr(item, "type", None) == "tool_call_item"
                and hasattr(getattr(item, "raw_item", None), "name")
            ]
        except InputGuardrailTripwireTriggered:
            logger.warning("Hotel pre-venta: input guardrail tripwire", session_id=session_id)
            response_text = (
                "Estoy acá para ayudarte con tu estadía en el Hampton by Hilton Bariloche. "
                "¿Querés que te muestre las habitaciones o consultemos disponibilidad? 😊"
            )
            tools_used = []
        except Exception as e:
            logger.error("Hotel pre-venta SDK: Runner failed",
                         session_id=session_id, error=str(e))
            response_text = (
                "Disculpá, tuve un problema procesando tu consulta. "
                "¿Podés intentarlo de nuevo en un momento?"
            )
            tools_used = []

        if not response_text:
            response_text = "Disculpá, no pude generar una respuesta. ¿Podés reformular tu consulta?"

        duration = time.time() - start
        logger.info("Hotel pre-venta SDK turn completed",
                    session_id=session_id,
                    tools_used=tools_used,
                    duration=f"{duration:.2f}s")

        return {
            "response": response_text,
            "has_context": bool(run_ctx.document_sources),
            "document_sources": run_ctx.document_sources,
            "tools_used": tools_used,
            "processing_time": f"{duration:.2f}s",
            "lead_analysis": {
                "lead_type": lead_analysis.get("lead_type"),
                "interest_score": lead_analysis.get("interest_score"),
                "contact_readiness": lead_analysis.get("contact_readiness"),
                "main_interest": lead_analysis.get("main_interest"),
                "has_contact_info": lead_analysis.get("has_contact_info", False),
                "priority_score": lead_analysis.get("priority_score", 0),
                "contact_requested": should_request_contact,
            },
        }


# Instancia global
hotel_sdk_orchestrator = HotelSDKOrchestrator()
