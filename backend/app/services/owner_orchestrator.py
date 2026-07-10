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
from app.utils.timezone_utils import now_business
from app.core.observability.logging_config import get_logger
from app.core.llm.openai_client import get_async_openai
from app.core.llm.sdk_usage import extract_usage
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
    realized, projected = rev.get("realized", {}), rev.get("projected", {})
    r_usd, p_usd = realized.get("usd", 0), projected.get("usd", 0)
    # Gráfico realizado vs proyectado (on-the-books) cuando hay algo que mostrar.
    if rev["usd"]:
        ctx.context.chart_url = chart_service.bars_chart_url(
            ["Realizado", "Reservado a futuro"], [round(r_usd), round(p_usd)],
            f"Facturación USD — {label}",
        )
    base = (
        f"Facturación de {label}: USD {rev['usd']:,.0f} / ARS {rev['ars']:,.0f} "
        f"en {rev['count']} reserva(s)."
    )
    # Distinguir lo ya facturado de lo comprometido a futuro (on-the-books) si aplica.
    if p_usd and r_usd:
        base += (f" De eso, USD {r_usd:,.0f} ya realizados y USD {p_usd:,.0f} por reservas "
                 f"confirmadas a futuro.")
    elif p_usd and not r_usd:
        base += (f" Todo es ingreso COMPROMETIDO por reservas confirmadas a futuro "
                 f"(aún no realizado): USD {p_usd:,.0f}.")
    return base


@function_tool
async def consultar_leads(ctx: RunContextWrapper[OwnerContext], periodo: str = "semana") -> str:
    """Devuelve cuántos leads se generaron y cuántos se cerraron (convirtieron en reserva)
    en un período, con la tasa de conversión. Úsala para preguntas de captación/ventas/leads."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    s = bm.get_leads_summary(db, start, end)
    by_ch = s.get("by_channel") or {}
    # Torta de origen de los leads (web / whatsapp / …), si hay datos.
    if by_ch:
        ctx.context.chart_url = chart_service.pie_chart_url(
            list(by_ch.keys()), list(by_ch.values()), f"Leads por canal — {label}"
        )
    canal_txt = ", ".join(f"{c}: {n}" for c, n in by_ch.items())
    return (
        f"Leads de {label}: {s['generated']} generados, {s['closed']} cerrados "
        f"(conversión {s['conversion_pct']}%)."
        + (f" Por canal: {canal_txt}." if canal_txt else "")
    )


@function_tool
async def consultar_quejas(ctx: RunContextWrapper[OwnerContext], periodo: str = "hoy") -> str:
    """Devuelve cuántas quejas hubo en un período y cuántas están abiertas/resueltas.
    Úsala para preguntas sobre reclamos, quejas o problemas de huéspedes."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    c = bm.get_complaints(db, start, end)
    # Torta de tickets por categoría (en qué se concentran los pedidos/quejas), si hay datos.
    by_cat = bm.get_tickets_by_category(db, start, end)
    if by_cat:
        ctx.context.chart_url = chart_service.pie_chart_url(
            list(by_cat.keys()), list(by_cat.values()), f"Tickets por categoría — {label}"
        )
    cat_txt = ", ".join(f"{cat}: {n}" for cat, n in by_cat.items())
    return (
        f"Quejas de {label}: {c['total']} en total ({c['open']} abiertas, {c['resolved']} resueltas)."
        + (f" Tickets por categoría: {cat_txt}." if cat_txt else "")
    )


@function_tool
async def consultar_resumen_negocio(ctx: RunContextWrapper[OwnerContext], periodo: str = "mes") -> str:
    """Panorama COMBINADO del negocio en un período: ocupación, facturación, leads y quejas
    de una sola vez. Úsala para preguntas amplias como '¿cómo viene el mes?' o '¿cómo está
    el negocio?', o cuando quieras un análisis integral antes de recomendar."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    s = bm.get_business_summary(db, start, end)
    occ, rev, leads, comp = s["occupancy"], s["revenue"], s["leads"], s["complaints"]
    # Facturación: distinguir realizado de comprometido a futuro (on-the-books) si aplica.
    r_usd = (rev.get("realized") or {}).get("usd", 0)
    p_usd = (rev.get("projected") or {}).get("usd", 0)
    fact = f"• Facturación: USD {rev['usd']:,.0f} / ARS {rev['ars']:,.0f} en {rev['count']} reservas"
    if p_usd and r_usd:
        fact += f" (USD {r_usd:,.0f} realizados + USD {p_usd:,.0f} reservados a futuro)"
    elif p_usd and not r_usd:
        fact += f" — todo comprometido por reservas a futuro (aún no realizado)"
    return (
        f"Resumen del negocio — {label}:\n"
        f"• Ocupación: {occ['occupancy_pct']}% (de {occ['total_units']} habitaciones).\n"
        f"{fact}.\n"
        f"• Leads: {leads['generated']} generados, {leads['closed']} cerrados ({leads['conversion_pct']}%).\n"
        f"• Quejas: {comp['total']} ({comp['open']} abiertas)."
    )


# ---------------------------------------------------------------------------
# TOOLS v2: acceso operativo + análisis flexible (cálculo on-demand)
# ---------------------------------------------------------------------------
@function_tool
async def operacion_hoy(ctx: RunContextWrapper[OwnerContext]) -> str:
    """Estado operativo de HOY: cuántos PASAJEROS (personas) están alojados ahora,
    cuántas habitaciones ocupadas y por qué tipo. Úsala para '¿cuántos pasajeros tenemos
    alojados?', '¿cuántos huéspedes hay hoy?', '¿cuántas habitaciones ocupadas hoy?'."""
    db = ctx.context.db
    g = bm.get_guests_in_house(db)
    by = ", ".join(f"{rt}: {n}" for rt, n in g["by_room_type"].items()) or "—"
    return (
        f"Hoy ({g['date']}) hay {g['guests']} pasajero(s) alojado(s) en "
        f"{g['rooms_occupied']} habitación(es). Por tipo: {by}."
    )


@function_tool
async def buscar_huesped(ctx: RunContextWrapper[OwnerContext], nombre_o_telefono: str) -> str:
    """Busca si una persona TIENE RESERVA y si está alojada ahora, por nombre o teléfono.
    Devuelve su reserva (código, habitación, fechas, estado de estadía). Úsala para
    '¿está alojado/a [nombre]?', '¿qué habitación tiene [persona]?', 'buscá la reserva de…'."""
    from app.models.hotel import Booking
    db = ctx.context.db
    term = (nombre_o_telefono or "").strip()
    if not term:
        return "Necesito un nombre o teléfono para buscar."
    like = f"%{term}%"
    bookings = (
        db.query(Booking)
        .filter(
            (Booking.guest_name.ilike(like)) | (Booking.guest_phone.ilike(like)),
            Booking.status != "cancelled",
        )
        .order_by(Booking.check_in.desc())
        .limit(5)
        .all()
    )
    if not bookings:
        return f"No encontré ninguna reserva activa para '{term}'."
    lines = []
    for b in bookings:
        rt = b.room.room_type if b.room else "—"
        unit = f" (hab. {b.room_unit.unit_number})" if getattr(b, "room_unit", None) else ""
        estado = {"checked_in": "ALOJADO ahora", "upcoming": "llega próximamente",
                  "past": "ya finalizó", "cancelled": "cancelada"}.get(b.stay_status(), b.stay_status())
        lines.append(
            f"• {b.guest_name} — {b.code}: {rt}{unit}, "
            f"{b.check_in.isoformat()}→{b.check_out.isoformat()}, {estado}."
        )
    return "Encontré:\n" + "\n".join(lines)


@function_tool
async def consultar_habitacion(ctx: RunContextWrapper[OwnerContext], tipo: str = "") -> str:
    """Precio ACTUAL y datos de las habitaciones (USD y ARS a la cotización del día,
    capacidad, unidades). Si se indica `tipo` filtra por ese tipo. Úsala para '¿a qué precio
    está la King?', '¿cuánto sale la suite?', '¿qué habitaciones tenemos y a cuánto?'."""
    from app.services import reservation_service
    db = ctx.context.db
    rooms = reservation_service.list_rooms(db)
    if tipo:
        t = tipo.strip().lower()
        rooms = [r for r in rooms if t in (r.get("room_type") or "").lower()]
    if not rooms:
        return f"No encontré habitaciones del tipo '{tipo}'."
    lines = []
    for r in rooms:
        lines.append(
            f"• {r.get('room_type')}: USD {r.get('base_price_usd'):,.0f} / "
            f"ARS {r.get('base_price_ars'):,.0f} por noche · "
            f"capacidad {r.get('capacity')} · {r.get('total_units')} unidad(es)."
        )
    return "Tarifas vigentes (cotización del día):\n" + "\n".join(lines)


@function_tool
async def analizar_ingresos(
    ctx: RunContextWrapper[OwnerContext],
    periodo: str = "mes",
    tipo: str = "",
    agrupar_por: str = "",
) -> str:
    """Facturación con FILTROS, base para análisis a medida. `periodo` admite hoy/semana/
    mes/trimestre/semestre/año, estaciones ('invierno 2025'), meses ('junio') o un año
    ('2025'). `tipo` filtra por habitación (ej. 'King'). `agrupar_por` = 'month' (serie
    mensual) o 'room_type' (desglose). Devuelve USD/ARS, cantidad, ADR y promedio por reserva.
    Para COMPARAR dos períodos, llamá esta tool una vez por cada período. Para promedios,
    usá los crudos (USD, noches, reservas) y EXPLICÁ el cálculo."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    gb = agrupar_por if agrupar_por in ("month", "room_type") else None
    r = bm.get_revenue(db, start, end, room_type=(tipo or None), group_by=gb)
    base = (
        f"Facturación de {label}{(' — ' + tipo) if tipo else ''}: "
        f"USD {r['usd']:,.0f} / ARS {r['ars']:,.0f} en {r['count']} reserva(s). "
        f"ADR USD {r['adr']:,.1f}/noche · promedio USD {r['avg_per_booking']:,.0f}/reserva."
    )
    if r.get("by_month"):
        serie = "; ".join(f"{m['month']}: USD {m['usd']:,.0f}" for m in r["by_month"])
        labels = [m["month"] for m in r["by_month"]]
        values = [m["usd"] for m in r["by_month"]]
        ctx.context.chart_url = chart_service.bars_chart_url(labels, values, f"Ingresos {label}")
        base += f"\nPor mes: {serie}."
    if r.get("by_room_type"):
        desg = "; ".join(f"{rt}: USD {v['usd']:,.0f} ({v['count']})"
                         for rt, v in r["by_room_type"].items())
        base += f"\nPor tipo: {desg}."
    return base


@function_tool
async def analizar_ocupacion(
    ctx: RunContextWrapper[OwnerContext], periodo: str = "mes", tipo: str = "",
) -> str:
    """Ocupación con FILTROS. `periodo` admite los mismos valores flexibles que analizar_
    ingresos (incluye estaciones, meses, año). `tipo` filtra por habitación. Devuelve % de
    ocupación, noches vendidas, personas-noche y desglose por tipo + gráfico diario."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    occ = bm.get_occupancy(db, start, end, room_type=(tipo or None))
    if occ.get("daily"):
        ctx.context.chart_url = chart_service.occupancy_chart_url(occ["daily"], "Ocupación")
    by = ", ".join(f"{rt}: {p}%" for rt, p in occ.get("by_room_type", {}).items()) or "—"
    return (
        f"Ocupación de {label}{(' — ' + tipo) if tipo else ''}: {occ['occupancy_pct']}% "
        f"({occ['sold_nights']} noches-habitación vendidas; {occ['guests_nights']} personas-noche). "
        f"Por tipo: {by}."
    )


@function_tool
async def ranking_habitaciones(
    ctx: RunContextWrapper[OwnerContext], periodo: str = "trimestre", criterio: str = "bookings",
) -> str:
    """Ranking de las habitaciones MÁS SOLICITADAS/RENTABLES en un período. `criterio` =
    'bookings' (más reservada), 'nights' (más noches) o 'revenue' (más facturó). Úsala para
    '¿cuál es la habitación más pedida del trimestre?', '¿qué tipo factura más?'."""
    db = ctx.context.db
    start, end, label = bm.resolve_period(periodo)
    ranking = bm.get_room_ranking(db, start, end, by=criterio)
    if not ranking:
        return f"No hubo reservas en {label}."
    labels = [r["room_type"] for r in ranking]
    if criterio == "revenue":
        values = [r["revenue_usd"] for r in ranking]
    elif criterio == "nights":
        values = [r["nights"] for r in ranking]
    else:
        values = [r["bookings"] for r in ranking]
    # Distribución de RESERVAS por tipo → torta (qué parte del total es cada habitación).
    # Magnitudes (revenue/nights) → barras (comparación/orden).
    if criterio == "bookings":
        ctx.context.chart_url = chart_service.pie_chart_url(labels, values, f"Reservas por tipo — {label}")
    else:
        ctx.context.chart_url = chart_service.bars_chart_url(labels, values, f"Ranking ({label})")
    detalle = "; ".join(
        f"{r['room_type']}: {r['bookings']} reservas, {r['nights']} noches, USD {r['revenue_usd']:,.0f}"
        for r in ranking
    )
    return f"Ranking de habitaciones en {label} (por {criterio}): {detalle}."


@function_tool
async def comparar_periodos(
    ctx: RunContextWrapper[OwnerContext],
    metrica: str = "revenue",
    periodo_a: str = "",
    periodo_b: str = "",
    tipo: str = "",
) -> str:
    """Compara una MÉTRICA entre dos períodos. `metrica` = 'revenue' o 'occupancy'.
    `periodo_a`/`periodo_b` admiten estaciones/meses/año (ej. 'invierno 2026' vs 'invierno
    2025'). `tipo` filtra por habitación. Devuelve ambos valores + variación %. Úsala para
    'facturación de la King este invierno vs el pasado', 'ocupación de junio vs mayo'."""
    db = ctx.context.db
    if not periodo_a or not periodo_b:
        return "Necesito los dos períodos a comparar (ej. 'invierno 2026' y 'invierno 2025')."
    c = bm.compare_periods(db, metrica, periodo_a, periodo_b, room_type=(tipo or None))
    a, b = c["a"], c["b"]
    unit = c["unit"]
    fmt = (lambda v: f"USD {v:,.0f}") if unit == "USD" else (lambda v: f"{v}%")
    var = c["variation_pct"]
    var_txt = (f"{'+' if var >= 0 else ''}{var}%" if var is not None
               else "no comparable (el período base no tiene datos)")
    labels = [a["label"], b["label"]]
    ctx.context.chart_url = chart_service.bars_chart_url(labels, [a["value"], b["value"]],
                                                          f"{metrica}{(' '+tipo) if tipo else ''}")
    return (
        f"Comparación de {metrica}{(' — ' + tipo) if tipo else ''}:\n"
        f"• {a['label']}: {fmt(a['value'])}\n"
        f"• {b['label']}: {fmt(b['value'])}\n"
        f"Variación: {var_txt}."
    )


@function_tool
async def consultar_embudo(ctx: RunContextWrapper[OwnerContext]) -> str:
    """Embudo comercial real: conversaciones → leads → reservas, con tasas de conversión.
    Úsala para '¿cómo viene la conversión?', '¿cuántas charlas terminan en reserva?'."""
    from app.services.metrics_service import metrics_service
    db = ctx.context.db
    f = metrics_service.get_funnel(db)
    stages = " → ".join(f"{s['name']}: {s['count']}" for s in f.get("stages", []))
    rates = f.get("conversion_rates", {})
    return (
        f"Embudo: {stages}. "
        f"Conversión charla→lead: {rates.get('conversation_to_lead', 0)}%; "
        f"lead→reserva: {rates.get('lead_to_reservation', 0)}%."
    )


@function_tool
async def consultar_soporte(ctx: RunContextWrapper[OwnerContext]) -> str:
    """Estado del soporte/post-venta: tickets totales, abiertos, escalados, resueltos y
    tasa de auto-resolución del agente. Úsala para '¿cómo está el soporte?', '¿hay tickets
    abiertos?', '¿cuántos casos resolvió solo el agente?'."""
    from app.services.metrics_service import metrics_service
    db = ctx.context.db
    m = metrics_service.get_postsale_metrics(db)
    return (
        f"Soporte: {m.get('total_tickets', 0)} tickets "
        f"({m.get('open_tickets', 0)} abiertos, {m.get('escalated_tickets', 0)} escalados, "
        f"{m.get('auto_resolved_tickets', 0)} auto-resueltos). "
        f"Contención {m.get('containment_rate', 0)}% · escalamiento {m.get('escalation_rate', 0)}%."
    )


@function_tool
async def registrar_plan(
    ctx: RunContextWrapper[OwnerContext], titulo: str, descripcion: str = "", metrica: str = "",
) -> str:
    """Registra un PLAN DE ACCIÓN acordado con el CEO (queda guardado para hacerle seguimiento
    en charlas futuras). Úsala cuando acuerden una acción concreta, ej. "vamos a empujar
    tarifas last-minute para subir la ocupación de mayo". `metrica` = qué medir para evaluarlo
    (ej. "ocupación mayo"). Confirmá al CEO que lo anotaste y que se lo vas a recordar."""
    from app.models.action_plan import ActionPlan
    db = ctx.context.db
    session = ctx.context.session_id or ""
    plan = ActionPlan(
        owner_session=session, title=titulo.strip(),
        description=(descripcion or "").strip() or None,
        metric=(metrica or "").strip() or None, status="active",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return f"Plan registrado (#{plan.id}): «{plan.title}». Te voy a hacer el seguimiento."


@function_tool
async def consultar_planes(ctx: RunContextWrapper[OwnerContext]) -> str:
    """Lista los PLANES DE ACCIÓN activos acordados con el CEO, con su antigüedad. Úsala al
    iniciar un tema estratégico para RETOMAR lo pendiente ("la última vez quedamos en X,
    ¿cómo viene?"). Si no hay planes activos, te lo dice."""
    from app.models.action_plan import ActionPlan
    from app.utils.timezone_utils import now_business
    db = ctx.context.db
    session = ctx.context.session_id or ""
    plans = (
        db.query(ActionPlan)
        .filter(ActionPlan.owner_session == session, ActionPlan.status == "active")
        .order_by(ActionPlan.created_at.asc())
        .all()
    )
    if not plans:
        return "No hay planes de acción activos registrados con el CEO."
    hoy = now_business().date()
    lines = []
    for p in plans:
        dias = (hoy - p.created_at.date()).days if p.created_at else 0
        metric = f" · medir: {p.metric}" if p.metric else ""
        lines.append(f"#{p.id} «{p.title}» (hace {dias} día/s{metric})")
    return "Planes activos:\n" + "\n".join(lines)


@function_tool
async def actualizar_plan(
    ctx: RunContextWrapper[OwnerContext], plan_id: int, estado: str = "", nota: str = "",
) -> str:
    """Actualiza un PLAN DE ACCIÓN: marcalo como cumplido/descartado o agregale seguimiento.
    `estado` = "done" (cumplido), "dropped" (descartado) o vacío (solo registrar avance).
    `nota` = avance o resultado. Úsala cuando haya novedades sobre un plan."""
    from app.models.action_plan import ActionPlan
    from app.utils.timezone_utils import now_business
    db = ctx.context.db
    plan = db.query(ActionPlan).filter(
        ActionPlan.id == plan_id, ActionPlan.owner_session == (ctx.context.session_id or "")
    ).first()
    if not plan:
        return f"No encontré el plan #{plan_id}."
    if estado in ("done", "dropped"):
        plan.status = estado
    if nota:
        plan.description = ((plan.description or "") + f"\n[{now_business().date()}] {nota.strip()}").strip()
    plan.last_reviewed_at = now_business().replace(tzinfo=None)
    db.commit()
    estado_txt = {"done": "cumplido", "dropped": "descartado"}.get(plan.status, "en curso")
    return f"Plan #{plan.id} actualizado ({estado_txt})."


@function_tool
async def consultar_conocimiento(ctx: RunContextWrapper[OwnerContext], consulta: str) -> str:
    """CONSULTÁ SIEMPRE esta tool ANTES de dar cualquier recomendación de gestión, estrategia,
    finanzas o revenue management. Es tu material experto: los libros/documentos que el dueño
    cargó. Devuelve fragmentos de esos documentos (citalos al recomendar, aclarando que vienen
    del material de entrenamiento, no de los datos del hotel ni inventado). Si la búsqueda NO
    trae material relevante, te lo dice — en ese caso avisale al dueño que no tenés material
    cargado sobre ese tema y recién ahí respondé con tu criterio general (como estimación)."""
    try:
        from app.core.rag.vector_store import get_management_vector_store
        vs = get_management_vector_store()
        results = await vs.search(consulta, n_results=4, only_active=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("consultar_conocimiento falló", error=str(e))
        return "No pude acceder al material de entrenamiento en este momento."
    if not results:
        return ("No encontré material de entrenamiento relevante para esa consulta. "
                "Puedo responder con mi criterio general (marcándolo como estimación del sector).")
    fragmentos = []
    for r in results:
        src = (r.get("metadata") or {}).get("source", "documento")
        fragmentos.append(f"[{src}] {r.get('text', '').strip()}")
    return ("Material de entrenamiento relevante (citá que proviene de los documentos cargados):\n"
            + "\n\n".join(fragmentos))


@function_tool
async def consultar_equipo(ctx: RunContextWrapper[OwnerContext]) -> str:
    """Listado del EQUIPO del hotel (dueño y staff) cargado en el sistema, con su rol y si
    está activo. Úsala para '¿quiénes están en el equipo?', '¿cuántos miembros tengo?'."""
    from app.models.staff import StaffMember
    db = ctx.context.db
    members = db.query(StaffMember).order_by(StaffMember.role.asc(), StaffMember.name.asc()).all()
    if not members:
        return "Todavía no hay miembros del equipo cargados."
    activos = [m for m in members if m.active]
    lines = [f"• {m.name} — {'Dueño' if m.role == 'owner' else 'Staff'}"
             f"{'' if m.active else ' (inactivo)'}" for m in members]
    return f"Equipo ({len(activos)} activo(s) de {len(members)}):\n" + "\n".join(lines)


_TOOLS = [
    # BI de alto nivel (v1)
    consultar_ocupacion, consultar_ingresos, consultar_leads,
    consultar_quejas, consultar_resumen_negocio,
    # Operativo + análisis flexible (v2)
    operacion_hoy, buscar_huesped, consultar_habitacion,
    analizar_ingresos, analizar_ocupacion, ranking_habitaciones, comparar_periodos,
    consultar_embudo, consultar_soporte, consultar_equipo,
    # Conocimiento de consultoría (RAG separado)
    consultar_conocimiento,
    # Planes de acción (socio de largo plazo con seguimiento)
    registrar_plan, consultar_planes, actualizar_plan,
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
        now = now_business()
        try:
            fecha = now.strftime("%A %d de %B de %Y")
        except Exception:
            fecha = now.strftime("%d/%m/%Y")
        from app.services import business_profile_service
        from app.models.database import SessionLocal
        _db = SessionLocal()
        try:
            business_name = business_profile_service.get_profile(_db).get("business_name") \
                or "Hampton by Hilton Bariloche"
        finally:
            _db.close()
        return OWNER_AGENT_SYSTEM.format(
            owner_name=owner_name or "", fecha_actual=fecha, business_name=business_name,
        )

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
