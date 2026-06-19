"""
Tools (function calling) del agente de PRE-VENTA.

Define el schema declarativo de las herramientas que el LLM puede invocar y un
dispatcher que mapea cada tool_call a su servicio existente. NO contiene lógica
de negocio nueva: cada handler reutiliza los servicios ya probados
(rag_service, weather_service, event_detector, contact_service).

El Agents SDK (agent_sdk_orchestrator) envuelve estos handlers vía execute_tool()
con @function_tool. TOOLS_SCHEMA (formato OpenAI clásico) quedó sin consumidores tras
retirar el orquestador casero en P4; se conserva como documentación del contrato de tools.
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.services.rag_service import rag_service
from app.services.weather_service import weather_service
from app.services.event_detector import event_detector
from app.services.contact_service import ContactService
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Instancia local (ContactService no expone singleton global)
contact_service = ContactService()


# ---------------------------------------------------------------------------
# SCHEMA DECLARATIVO (formato OpenAI tool calling)
# ---------------------------------------------------------------------------
# Estas son las acciones DISCRETAS que el LLM decide invocar. El análisis de
# lead NO va acá: es transversal y lo ejecuta el orquestador en cada turno
# (igual que el flujo legacy), inyectando el resultado en el system prompt.
TOOLS_SCHEMA: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_paquetes",
            "description": (
                "Busca paquetes turísticos disponibles en el catálogo de la agencia "
                "según el destino, continente, presupuesto o tipo de viaje que pide el "
                "usuario. Úsala SIEMPRE que el usuario consulte por un destino, país, "
                "ciudad, región o tipo de experiencia de viaje. Devuelve el contexto "
                "real de los paquetes (precios, itinerarios, países) que debés usar "
                "para responder. NUNCA inventes paquetes ni precios: usá solo lo que "
                "devuelve esta tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "La consulta de viaje del usuario, lo más fiel posible a lo "
                            "que pidió (ej: 'playas en el Caribe', 'Punta Cana', "
                            "'viaje a Europa con menos de 3000 USD')."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_clima",
            "description": (
                "Obtiene el clima actual de una ciudad/país destino para enriquecer la "
                "recomendación (qué empacar, mejor época, comparación con Argentina). "
                "Úsala solo cuando ya identificaste un destino concreto y aporta valor "
                "mencionar el clima."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ciudad": {"type": "string", "description": "Ciudad del destino."},
                    "pais": {"type": "string", "description": "País del destino (opcional pero ayuda)."},
                },
                "required": ["ciudad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_evento",
            "description": (
                "Detecta si la consulta del usuario es sobre un EVENTO TEMPORAL que "
                "cambia de fecha/sede cada año (Mundial de fútbol, Fórmula 1, "
                "Olimpiadas, carnavales, festivales). Úsala cuando el usuario menciona "
                "un evento así y NO encontraste un paquete específico para él. Devuelve "
                "los países relacionados al evento para poder ofrecer alternativas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "El texto del usuario que menciona el evento.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "identificar_contacto",
            "description": (
                "Busca si el usuario actual ya es un contacto conocido (lead previo o "
                "cliente que ya viajó) a partir de su teléfono o email, para personalizar "
                "el trato. NOTA: hoy solo úsala si el usuario menciona explícitamente su "
                "teléfono o email; el reconocimiento automático aún no está activo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "telefono": {"type": "string", "description": "Teléfono del usuario si lo mencionó."},
                    "email": {"type": "string", "description": "Email del usuario si lo mencionó."},
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# HANDLERS — cada uno reutiliza un servicio existente
# ---------------------------------------------------------------------------
async def _handle_buscar_paquetes(args: Dict, ctx: Dict) -> Dict:
    """Envuelve rag_service.retrieve_context_with_sources preservando el historial."""
    query = (args.get("query") or "").strip() or ctx.get("message", "")
    result = await rag_service.retrieve_context_with_sources(
        query=query,
        conversation_history=ctx.get("history"),
    )
    context = result.get("context", "NO_CONTEXT_FOUND")

    if context == "NO_CONTEXT_FOUND":
        # Preservar la lógica de alternativas por continente del flujo legacy.
        geo_analysis = rag_service.analyze_query_geography(query)
        no_ctx = rag_service.format_no_context_response(geo_analysis)
        no_ctx_text = no_ctx["response"] if isinstance(no_ctx, dict) else no_ctx
        return {
            "found": False,
            "message_for_user": no_ctx_text,
            "tool_result": (
                "No hay paquetes en catálogo para esa consulta. "
                "Ofrecé al usuario estas alternativas disponibles, sin inventar otras:\n"
                + no_ctx_text
            ),
        }

    # Guardar fuentes para el response final (tracking de documentos)
    ctx["document_sources"] = result.get("sources", [])
    ctx["relevance_mode"] = result.get("relevance_mode")
    return {
        "found": True,
        "tool_result": context,
        "relevance_mode": result.get("relevance_mode"),
    }


def _handle_obtener_clima(args: Dict, ctx: Dict) -> Dict:
    """Envuelve weather_service (sincrónico), consciente de la fecha del viaje.

    Si el LLM pasa `fecha` (YYYY-MM-DD):
      - dentro del rango de pronóstico → forecast real,
      - fecha lejana → señal estacional (el LLM aporta el promedio histórico).
    Sin fecha → clima actual (comportamiento previo).
    """
    from datetime import datetime as _dt

    ciudad = (args.get("ciudad") or "").strip()
    pais = (args.get("pais") or "").strip() or None
    if not ciudad:
        return {"tool_result": "No se especificó ciudad para consultar el clima."}

    # Parseo tolerante de la fecha objetivo
    target_date = None
    fecha_raw = (args.get("fecha") or "").strip()
    if fecha_raw:
        try:
            target_date = _dt.strptime(fecha_raw, "%Y-%m-%d").date()
        except ValueError:
            target_date = None  # fecha inválida → tratamos como clima actual

    data = weather_service.get_weather_for_date(ciudad, pais, target_date)
    if not data:
        return {"tool_result": f"No hay datos de clima disponibles para {ciudad}."}

    # La comparación con Argentina solo aplica al clima actual real.
    compare = data.get("mode") == "current"
    formatted = weather_service.format_for_date(data, compare_with_argentina=compare)
    return {"tool_result": formatted}


async def _handle_buscar_evento(args: Dict, ctx: Dict) -> Dict:
    """Envuelve event_detector.detect_event."""
    query = (args.get("query") or "").strip() or ctx.get("message", "")
    event_info = await event_detector.detect_event(query)
    if event_info and event_info.get("is_temporal_event"):
        # Señalizar al orquestador para que active el flujo de evento (notif/alternativas)
        ctx["event_info"] = event_info
        countries = ", ".join(event_info.get("related_countries", [])[:3])
        return {
            "is_event": True,
            "tool_result": (
                f"Es un evento temporal: {event_info.get('event_name')}. "
                f"No tenemos paquete específico. Países relacionados: {countries}. "
                "Ofrecé al usuario notificarlo cuando haya paquetes o mostrarle destinos similares."
            ),
        }
    return {"is_event": False, "tool_result": "No es un evento temporal."}


def _handle_identificar_contacto(args: Dict, ctx: Dict) -> Dict:
    """Envuelve contact_service para reconocer un contacto conocido."""
    db: Optional[Session] = ctx.get("db")
    telefono = (args.get("telefono") or "").strip()
    if not telefono or db is None:
        return {"tool_result": "No hay teléfono para identificar al contacto."}

    contact = contact_service.normalize_and_find_contact(telefono, db)
    if not contact:
        return {"known": False, "tool_result": "Es un contacto nuevo (no registrado previamente)."}

    return {
        "known": True,
        "tool_result": (
            f"Contacto conocido: {contact.get_display_name()}. "
            f"Tipo: {contact.contact_type}. Compras previas: {contact.purchases_made}. "
            f"Resumen: {contact.ai_summary or 'sin resumen'}."
        ),
    }


_DISPATCH = {
    "buscar_paquetes": _handle_buscar_paquetes,
    "obtener_clima": _handle_obtener_clima,
    "buscar_evento": _handle_buscar_evento,
    "identificar_contacto": _handle_identificar_contacto,
}


async def execute_tool(name: str, args: Dict, ctx: Dict) -> Dict:
    """
    Ejecuta una tool por nombre. `ctx` es un dict mutable compartido por turno
    (lleva db, message, history y recoge document_sources / event_info que el
    orquestador necesita después).

    Returns:
        Dict con al menos la key 'tool_result' (string que se reinyecta al LLM).
    """
    handler = _DISPATCH.get(name)
    if handler is None:
        logger.warning("Unknown tool requested", tool=name)
        return {"tool_result": f"Herramienta desconocida: {name}"}

    try:
        import inspect
        if inspect.iscoroutinefunction(handler):
            return await handler(args, ctx)
        return handler(args, ctx)
    except Exception as e:
        logger.error("Error executing tool", tool=name, error=str(e))
        return {"tool_result": f"Error ejecutando {name}: {e}"}
