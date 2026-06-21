"""
Orquestador del AGENTE DE GERENCIA (consultor de negocio) sobre el OpenAI Agents SDK.

Agente AISLADO: tiene SOLO las tools de BI (owner_tools). No referencia las tools de
reserva del huésped — esa separación física es la barrera de seguridad (un huésped jamás
accede a estas métricas). Solo se invoca para el rol `owner`, vía agent_router.

Patrón clonado de hotel_sdk_orchestrator (Agent[Context], @function_tool, Runner.run).
Las tools devuelven datos reales y, cuando aplica, dejan en el contexto una `chart_spec`
para que el orquestador arme la URL del gráfico (QuickChart) a enviar por WhatsApp.
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
from app.utils.timezone_utils import now_argentina
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai
from app.core.sdk_usage import extract_usage
from app.services import business_metrics as bm
from app.services import chart_service
from app.prompts.owner_prompts import OWNER_AGENT_SYSTEM

logger = get_logger(__name__)

MAX_TURNS = 6
MAX_HISTORY_MESSAGES = 20

_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# CONTEXTO POR TURNO
# ---------------------------------------------------------------------------
class OwnerContext:
    def __init__(self, db: Session, message: str, history: List[Dict], session_id: str = ""):
        self.db = db
        self.message = message
        self.history = history
        self.session_id = session_id
        # Una tool puede dejar acá la URL de un gráfico a enviar por WhatsApp.
        self.chart_url: Optional[str] = None


# ---------------------------------------------------------------------------
# TOOLS DE BI (solo accesibles por el agente de gerencia)
# ---------------------------------------------------------------------------
@function_tool
async def consultar_ocupacion(ctx: RunContextWrapper[OwnerContext], periodo: str = "mes") -> str:
    """Devuelve el % de ocupación del hotel en un período ("hoy"/"semana"/"mes"/"anio"),
    por tipo de habitación, y prepara un gráfico de la ocupación diaria. Úsala cuando el
    dueño pregunte por ocupación, habitaciones vacías/llenas o cuán lleno está el hotel."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    occ = bm.get_occupancy(db, start, end)
    # Gráfico de ocupación diaria.
    if occ.get("daily"):
        ctx.context.chart_url = chart_service.occupancy_chart_url(occ["daily"], "Ocupación")
    by_type = ", ".join(f"{rt}: {p}%" for rt, p in occ.get("by_room_type", {}).items()) or "—"
    return (
        f"Ocupación de {label}: {occ['occupancy_pct']}% "
        f"({occ['sold_nights']} noches-habitación vendidas de {occ['capacity_nights']} posibles, "
        f"sobre {occ['total_units']} habitaciones). Por tipo: {by_type}."
    )


@function_tool
async def consultar_ingresos(ctx: RunContextWrapper[OwnerContext], periodo: str = "mes") -> str:
    """Devuelve la facturación del hotel en un período ("hoy"/"semana"/"mes"/"anio"), en USD
    y ARS, y la cantidad de reservas. Úsala para preguntas de ingresos, facturación o ventas."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    rev = bm.get_revenue(db, start, end)
    return (
        f"Facturación de {label}: USD {rev['usd']:,.0f} / ARS {rev['ars']:,.0f} "
        f"en {rev['count']} reserva(s)."
    )


@function_tool
async def consultar_leads(ctx: RunContextWrapper[OwnerContext], periodo: str = "semana") -> str:
    """Devuelve cuántos leads se generaron y cuántos se cerraron (convirtieron en reserva)
    en un período, con la tasa de conversión. Úsala para preguntas de captación/ventas/leads."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    s = bm.get_leads_summary(db, start, end)
    return (
        f"Leads de {label}: {s['generated']} generados, {s['closed']} cerrados "
        f"(conversión {s['conversion_pct']}%)."
    )


@function_tool
async def consultar_quejas(ctx: RunContextWrapper[OwnerContext], periodo: str = "hoy") -> str:
    """Devuelve cuántas quejas hubo en un período y cuántas están abiertas/resueltas.
    Úsala para preguntas sobre reclamos, quejas o problemas de huéspedes."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    c = bm.get_complaints(db, start, end)
    return f"Quejas de {label}: {c['total']} en total ({c['open']} abiertas, {c['resolved']} resueltas)."


@function_tool
async def consultar_resumen_negocio(ctx: RunContextWrapper[OwnerContext], periodo: str = "mes") -> str:
    """Panorama COMBINADO del negocio en un período: ocupación, facturación, leads y quejas
    de una sola vez. Úsala para preguntas amplias como '¿cómo viene el mes?' o '¿cómo está
    el negocio?', o cuando quieras un análisis integral antes de recomendar."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    s = bm.get_business_summary(db, start, end)
    occ, rev, leads, comp = s["occupancy"], s["revenue"], s["leads"], s["complaints"]
    return (
        f"Resumen del negocio — {label}:\n"
        f"• Ocupación: {occ['occupancy_pct']}% (de {occ['total_units']} habitaciones).\n"
        f"• Facturación: USD {rev['usd']:,.0f} / ARS {rev['ars']:,.0f} en {rev['count']} reservas.\n"
        f"• Leads: {leads['generated']} generados, {leads['closed']} cerrados ({leads['conversion_pct']}%).\n"
        f"• Quejas: {comp['total']} ({comp['open']} abiertas)."
    )


_TOOLS = [
    consultar_ocupacion, consultar_ingresos, consultar_leads,
    consultar_quejas, consultar_resumen_negocio,
]


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------
class OwnerOrchestrator:
    """Loop del consultor de gerencia sobre el OpenAI Agents SDK (tools solo de BI)."""

    def __init__(self):
        self._model_name = settings.OPENAI_MODEL
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL,
            openai_client=_sdk_client,
        )

    def _build_instructions(self, owner_name: str = "") -> str:
        now = now_argentina()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        return OWNER_AGENT_SYSTEM.format(owner_name=owner_name or "", fecha_actual=fecha)

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def run(self, db: Session, message: str, session_id: str,
                  history: List[Dict], owner_name: str = "") -> Dict:
        """Procesa un turno del consultor de gerencia. Devuelve {response, chart_url?}."""
        start = time.time()
        agent = Agent[OwnerContext](
            name="Asesor de Gerencia",
            instructions=self._build_instructions(owner_name),
            tools=_TOOLS,
            model=self._model,
            model_settings=ModelSettings(temperature=settings.OPENAI_TEMPERATURE),
        )
        run_ctx = OwnerContext(db, message, history, session_id=session_id)
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
            logger.error("Owner orchestrator: Runner failed", session_id=session_id, error=str(e))
            response_text = ("Disculpá, tuve un problema consultando los datos del negocio. "
                             "¿Podés intentarlo de nuevo en un momento?")
            tools_used = []

        if not response_text:
            response_text = "No pude generar el análisis. ¿Podés reformular la consulta?"

        duration = time.time() - start
        logger.info("Owner orchestrator turn completed",
                    session_id=session_id, tools_used=tools_used,
                    has_chart=bool(run_ctx.chart_url), duration=f"{duration:.2f}s")

        return {
            "response": response_text,
            "chart_url": run_ctx.chart_url,
            "tools_used": tools_used,
            "usage": usage,
        }


owner_orchestrator = OwnerOrchestrator()
