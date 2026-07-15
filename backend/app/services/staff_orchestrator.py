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
from app.core.profile.agent_profile import profile_manager
from app.utils.timezone_utils import now_business
from app.core.observability.logging_config import get_logger
from app.core.llm.openai_client import get_async_openai
from app.core.llm.sdk_usage import extract_usage
from app.services import operations_service as ops
from app.models.staff import StaffMember
from app.domains.hotel.prompts.staff_tool_prompts import STAFF_AGENT_SYSTEM

logger = get_logger(__name__)

# Config real del loop en la AgentSpec (agent_specs.py:hotel_staff). MAX_TURNS sin uso (eliminado);
# MAX_HISTORY_MESSAGES solo lo usa el _build_input_list local.
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

# Fase 2.2: registro en el ToolRegistry — la spec del agente referencia las tools por key.
from app.core.agents.tool_registry import register_tool  # noqa: E402
register_tool("staff.resolver_ticket", resolver_ticket)
register_tool("staff.reportar_incidencia", reportar_incidencia)
register_tool("staff.mis_tickets", mis_tickets)


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class StaffOrchestrator:
    def __init__(self):
        # El modelo real lo construye el runtime desde la spec; solo el nombre se usa (usage).
        self._model_name = settings.OPENAI_MODEL

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
            f"{self._ticket_allergy_note(db, t)}"
            for t in tickets[:max_tickets]
        )

    def _ticket_allergy_note(self, db: Session, ticket) -> str:
        """Nivel STAFF (mínimo): si el huésped del ticket tiene alergias declaradas, avisarlas.

        Es un dato de SEGURIDAD (no comercial): operaciones no recibe perfil 360 ni datos de
        venta, pero sí debe conocer alergias. Nunca rompe el resumen."""
        try:
            booking = getattr(ticket, "booking", None)
            contact_id = getattr(booking, "contact_id", None) if booking else None
            if not contact_id:
                return ""
            from app.services.contact_service import contact_service
            prefs = (contact_service.get_guest_profile(contact_id, db) or {}).get("preferences") or {}
            allergies = prefs.get("allergies") or []
            return f"  ⚠️ Alergias: {', '.join(allergies)}." if allergies else ""
        except Exception:  # noqa: BLE001 — la anotación nunca debe romper el resumen
            return ""

    def _build_instructions(self, db: Session, staff: StaffMember) -> str:
        now = now_business()
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
        """Turno del agente de operaciones — Fase 2.2: corre por el runtime declarativo.

        Este orquestador queda como capa FINA de dominio: compone las instrucciones
        (composer) y adapta el resultado; el loop del SDK vive en core/agents/sdk_runtime
        con los parámetros de la spec (paridad: turns=5, hist=10, temp=0.4, mismas tools).
        """
        start = time.time()
        from app.core.agents.sdk_runtime import run_agent, build_input_list
        from app.domains.hotel.agent_specs import SPECS
        spec = SPECS["hotel_staff"]

        run_ctx = StaffContext(db, staff, message, session_id=session_id)
        out = await run_agent(
            spec,
            instructions=self._build_instructions(db, staff),
            context=run_ctx,
            input_list=build_input_list(history, message, spec.max_history),
            fallback_response="Disculpá, tuve un problema procesando eso. ¿Podés repetirlo?",
        )
        response_text = out["response"] or (
            "No te entendí bien. ¿Me lo decís de nuevo? (¿resolviste algo o reportás una incidencia?)"
        )

        logger.info("Staff orchestrator turn completed",
                    session_id=session_id, staff=staff.name, tools_used=out["tools_used"],
                    duration=f"{time.time() - start:.2f}s")
        return {"response": response_text, "tools_used": out["tools_used"], "usage": out["usage"]}


staff_orchestrator = StaffOrchestrator()
