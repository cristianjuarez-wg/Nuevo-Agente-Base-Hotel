"""
Orquestador del AGENTE DE OPERACIONES del EQUIPO (rol staff) — Fase 4 ("empleado digital").

Agente AISLADO para el personal del hotel (mantenimiento/recepción/housekeeping). Le permite,
por WhatsApp (texto o audio ya transcrito):
  - RESOLVER una tarea asignada → `resolver_ticket` (la deja pre-resuelta y avisa al huésped).
  - REPORTAR una incidencia nueva → `reportar_incidencia` (crea y asigna el ticket).
  - VER sus pendientes → `mis_tickets`.

Patrón clonado de owner_orchestrator (Agent[Context], @function_tool, Runner.run). La lógica
de estados/asignación vive en operations_service (no se duplica acá).
"""
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from agents import (
    Agent, Runner, RunContextWrapper, function_tool,
    ModelSettings, OpenAIChatCompletionsModel, set_default_openai_client,
    set_tracing_export_api_key,
)

from app.config import settings
from app.core.agent_profile import profile_manager
from app.utils.timezone_utils import now_argentina
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai
from app.core.sdk_usage import extract_usage
from app.services import operations_service as ops
from app.models.staff import StaffMember
from app.prompts.staff_tool_prompts import STAFF_AGENT_SYSTEM

logger = get_logger(__name__)

MAX_TURNS = 5
MAX_HISTORY_MESSAGES = 10

_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)


class StaffContext:
    def __init__(self, db: Session, staff: StaffMember, message: str, session_id: str = ""):
        self.db = db
        self.staff = staff
        self.message = message
        self.session_id = session_id


# ---------------------------------------------------------------------------
# TOOLS de operaciones
# ---------------------------------------------------------------------------
@function_tool
async def resolver_ticket(
    ctx: RunContextWrapper[StaffContext], referencia: str, nota: str = "",
) -> str:
    """Marca como RESUELTA una tarea que el miembro del equipo terminó. `referencia` puede ser
    el número de ticket (HT-XXXXXX) o el número de habitación (ej. «401»). `nota` = qué hizo
    (ej. «reparé el compresor del aire»). Deja la tarea pre-resuelta y, si hay un huésped que
    pueda validar, le pide confirmación. Si la referencia es ambigua, NO cierra nada y te pide
    aclarar cuál es."""
    db = ctx.context.db
    staff = ctx.context.staff
    ticket, candidates = ops.match_open_ticket(db, referencia, staff=staff)

    if ticket is None:
        if not candidates:
            return ("No encontré una tarea abierta con esa referencia. ¿Querés que la registre "
                    "como una incidencia nueva con reportar_incidencia?")
        # Varias coincidencias → listar para desambiguar.
        opts = "; ".join(
            f"{t.ticket_number} ({ops._room_label(t)}: {(t.description or '')[:40]})"
            for t in candidates[:5]
        )
        return f"Hay varias tareas que podrían ser. ¿Cuál es? {opts}"

    status = ops.mark_pre_resolved(
        db, ticket, staff, nota or ctx.context.message,
        staff_message=ctx.context.message,
    )
    where = ops._room_label(ticket)
    if status == "resuelto":
        return (f"Listo, marqué {ticket.ticket_number} ({where}) como RESUELTO 👍 "
                "(no requería validación del huésped).")
    return (f"Listo, marqué {ticket.ticket_number} ({where}) como resuelto 👍 "
            "Le avisé al huésped para que confirme. Cuando confirme, queda cerrado.")


@function_tool
async def reportar_incidencia(
    ctx: RunContextWrapper[StaffContext], descripcion: str, area: str = "",
) -> str:
    """Registra una INCIDENCIA o pedido NUEVO que el miembro del equipo detectó (no es una tarea
    que ya tenía asignada). Ej.: «fuga de agua en el garage», «la 401 pidió wake-up call 8am»,
    «lámpara quemada en el pasillo del 3°». `area` = mantenimiento | recepcion | housekeeping |
    general (deducíla del contenido si no es explícita). Crea la tarea y la asigna a quien deba
    ocuparse."""
    db = ctx.context.db
    ticket, staff = ops.create_staff_ticket(
        db, description=descripcion, area_hint=(area or None),
        session_id=ctx.context.session_id,
    )
    asignado = f" Se la asigné a {staff.name}." if staff else " (todavía sin nadie del área cargado.)"
    return (f"Anotado ✅ Creé el ticket {ticket.ticket_number} "
            f"(área: {ticket.assigned_area}).{asignado}")


@function_tool
async def mis_tickets(ctx: RunContextWrapper[StaffContext]) -> str:
    """Lista las tareas pendientes (asignadas o pre-resueltas) del miembro del equipo. Úsala
    cuando pregunte «¿qué tengo pendiente?», «¿qué me toca?», «¿qué tareas tengo?»."""
    db = ctx.context.db
    staff = ctx.context.staff
    tickets = ops.list_staff_tickets(db, staff)
    if not tickets:
        return "No tenés tareas pendientes ahora mismo. 🙌"
    lines = []
    for t in tickets:
        estado = "esperando confirmación del huésped" if t.status == "pre_resuelto" else "pendiente"
        lines.append(f"• {t.ticket_number} — {ops._room_label(t)}: {(t.description or '')[:50]} ({estado})")
    return "Tus tareas:\n" + "\n".join(lines)


_TOOLS = [resolver_ticket, reportar_incidencia, mis_tickets]


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class StaffOrchestrator:
    def __init__(self):
        self._model_name = settings.OPENAI_MODEL
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )

    def _pending_summary(self, db: Session, staff: StaffMember) -> str:
        tickets = ops.list_staff_tickets(db, staff)
        if not tickets:
            return "No tiene tareas pendientes ahora."
        # Tope configurable desde el flujo de operaciones del Centro (Fase A);
        # sin config → el default histórico de 8 (paridad).
        max_tickets = 8
        try:
            from app.services import skill_service
            flow = skill_service.get_flow_values_by_role(db, "staff", "flujo_operaciones")
            if flow and flow.get("max_tickets"):
                max_tickets = int(flow["max_tickets"])
        except Exception:  # noqa: BLE001 — nunca romper el resumen por config
            pass
        return "\n".join(
            f"- {t.ticket_number} ({ops._room_label(t)}): {(t.description or '')[:50]}"
            for t in tickets[:max_tickets]
        )

    def _build_instructions(self, db: Session, staff: StaffMember) -> str:
        now = now_argentina()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        from app.services import business_profile_service
        profile = business_profile_service.get_profile(db)
        return STAFF_AGENT_SYSTEM.format(
            nombre_agente=profile.get("agent_display_name") or profile_manager.get_agent_name(),
            business_name=profile.get("business_name") or "Hampton by Hilton Bariloche",
            staff_name=staff.name,
            staff_area=staff.area or "general",
            fecha_actual=fecha,
            pending=self._pending_summary(db, staff),
        )

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(self, db: Session, staff: StaffMember, message: str,
                  session_id: str, history: List[Dict]) -> Dict:
        start = time.time()
        agent = Agent[StaffContext](
            name="Coordinador de Operaciones",
            instructions=self._build_instructions(db, staff),
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=0.4),
        )
        run_ctx = StaffContext(db, staff, message, session_id=session_id)
        input_list = self._build_input_list(history, message)

        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": self._model_name}
        try:
            result = await Runner.run(agent, input=input_list, context=run_ctx, max_turns=MAX_TURNS)
            usage = extract_usage(result, model=self._model_name)
            response_text = result.final_output or ""
            tools_used = [
                item.raw_item.name
                for item in getattr(result, "new_items", [])
                if getattr(item, "type", None) == "tool_call_item"
                and hasattr(getattr(item, "raw_item", None), "name")
            ]
        except Exception as e:  # noqa: BLE001
            logger.error("Staff orchestrator: Runner failed", session_id=session_id, error=str(e))
            response_text = ("Disculpá, tuve un problema procesando eso. ¿Podés repetirlo?")
            tools_used = []

        if not response_text:
            response_text = "No te entendí bien. ¿Me lo decís de nuevo? (¿resolviste algo o reportás una incidencia?)"

        duration = time.time() - start
        logger.info("Staff orchestrator turn completed",
                    session_id=session_id, staff=staff.name, tools_used=tools_used,
                    duration=f"{duration:.2f}s")

        return {"response": response_text, "tools_used": tools_used, "usage": usage}


staff_orchestrator = StaffOrchestrator()
