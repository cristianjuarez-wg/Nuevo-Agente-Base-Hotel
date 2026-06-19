"""
Tools (function calling) del agente de POST-VENTA.

Envuelven los servicios de clasificación/análisis ya existentes para que el LLM
los invoque dentro de un único loop, en lugar de ejecutarse siempre en cadena.

IMPORTANTE: estas tools NO modifican tickets ni escalan. Solo ANALIZAN y devuelven
información. La acción determinística sobre el ticket (escalar/resolver) la ejecuta
el orquestador según el resultado de `analizar_severidad_y_escalacion`. Esto preserva
la integridad de la lógica de negocio.

El `ctx` compartido por turno lleva: service (PostSaleService), package (SoldPackage),
message, history. Las tools recogen en ctx la decisión de escalación para el orquestador.
"""
from typing import Dict, List
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# El Agents SDK (postsale_sdk_orchestrator) envuelve estos handlers vía execute_tool()
# con @function_tool. TOOLS_SCHEMA (formato OpenAI clásico) quedó sin consumidores tras
# retirar el orquestador casero en P4; se conserva como documentación del contrato de tools.
TOOLS_SCHEMA: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "analizar_severidad_y_escalacion",
            "description": (
                "Analiza la consulta del cliente sobre su viaje ya comprado y determina "
                "si podés resolverla vos (informativa, dudas, detalles del paquete) o si "
                "requiere escalación a un asesor humano (problemas, cambios, reclamos, "
                "urgencias). OBLIGATORIO llamarla una vez antes de dar tu respuesta final "
                "a una consulta de soporte. Devuelve la decisión de escalación, urgencia "
                "y categoría que debés respetar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "La consulta o problema del cliente, tal como lo expresó.",
                    }
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_estado_vuelo",
            "description": (
                "Consulta el estado actual de los vuelos del paquete del cliente "
                "(demoras, cancelaciones, cambios). Úsala cuando el cliente pregunta por "
                "su vuelo o cuando una consulta puede depender del estado del vuelo."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_contacto_proveedor",
            "description": (
                "Obtiene los datos de contacto del proveedor relacionado con la consulta "
                "(hotel, transfer, aerolínea, actividad) para ofrecérselos al cliente "
                "cuando es útil que contacte directamente al proveedor. Devuelve nombre y "
                "teléfono reales del proveedor del paquete."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {
                        "type": "string",
                        "description": "Categoría: hotel, transfer, flight o activity.",
                    }
                },
                "required": ["categoria"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------
async def _handle_analizar_severidad(args: Dict, ctx: Dict) -> Dict:
    """Consolida severity_classifier + escalation_analyzer (vía analyze_with_intelligence)."""
    service = ctx["service"]
    package = ctx["package"]
    consulta = (args.get("consulta") or "").strip() or ctx.get("message", "")

    try:
        analysis = await service.analyze_with_intelligence(
            consulta, package, ctx.get("history")
        )
    except Exception as e:
        # Si el análisis falla, NO auto-resolver: escalar por seguridad. Un caso serio
        # ("perdí el pasaporte") no debe resolverse solo porque el clasificador cayó.
        logger.error("analyze_with_intelligence failed, escalando por seguridad", error=str(e))
        analysis = {
            "requires_escalation": True,
            "urgency_level": "alta",
            "escalation_reason": "no se pudo analizar la severidad (falla del análisis)",
            "suggested_category": "general",
        }

    # Guardar para que el orquestador ejecute la acción determinística sobre el ticket
    ctx["escalation_analysis"] = analysis
    requires_escalation = analysis.get("requires_escalation", True)

    if requires_escalation:
        result_text = (
            f"REQUIERE ESCALACIÓN a un asesor humano. "
            f"Urgencia: {analysis.get('urgency_level')}. "
            f"Motivo: {analysis.get('escalation_reason', 'requiere intervención humana')}. "
            f"Categoría: {analysis.get('suggested_category', 'general')}. "
            "Informá al cliente con empatía que un asesor especializado lo contactará, "
            "sin prometer plazos exactos que no podés garantizar."
        )
    else:
        result_text = (
            f"PODÉS RESOLVERLA vos con la info del paquete. "
            f"Categoría: {analysis.get('suggested_category', 'general')}. "
            f"Tono sugerido: {analysis.get('recommended_response_tone', 'cálido')}. "
            "Respondé directamente usando solo los datos reales del paquete del contexto."
        )

    return {"tool_result": result_text, "requires_escalation": requires_escalation}


def _handle_consultar_estado_vuelo(args: Dict, ctx: Dict) -> Dict:
    """Envuelve _get_flight_status_with_monitoring."""
    service = ctx["service"]
    package = ctx["package"]
    try:
        flight_status = service._get_flight_status_with_monitoring(package, ctx.get("message", ""))
    except Exception as e:
        logger.error("Error consulting flight status", error=str(e))
        return {"tool_result": "No pude obtener el estado de los vuelos en este momento."}

    if flight_status.get("has_issues"):
        ctx["flight_issues"] = True
        issues = "; ".join(str(i) for i in flight_status.get("issues", []))
        return {"tool_result": f"Se detectaron problemas en los vuelos: {issues}. Esto puede requerir escalación."}

    flights = flight_status.get("flights", [])
    if not flights:
        return {"tool_result": "No hay información de estado de vuelos disponible para este paquete."}
    return {"tool_result": f"Estado de vuelos sin novedades. Detalle: {flights}"}


def _handle_obtener_contacto_proveedor(args: Dict, ctx: Dict) -> Dict:
    """Envuelve _identify_provider_for_interaction + _build_provider_response."""
    service = ctx["service"]
    package = ctx["package"]
    db = ctx["db"]
    categoria = (args.get("categoria") or "").strip()

    provider_id = service._identify_provider_for_interaction(package, categoria, ctx.get("message", ""))
    if not provider_id:
        return {"tool_result": f"No hay un proveedor de {categoria or 'esa categoría'} asociado a este paquete."}

    from app.models.provider import Provider
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        return {"tool_result": "No se encontraron los datos del proveedor."}

    response = service._build_provider_response(provider, True, package)
    return {"tool_result": f"Datos del proveedor para ofrecer al cliente: {response}"}


_DISPATCH = {
    "analizar_severidad_y_escalacion": _handle_analizar_severidad,
    "consultar_estado_vuelo": _handle_consultar_estado_vuelo,
    "obtener_contacto_proveedor": _handle_obtener_contacto_proveedor,
}


async def execute_tool(name: str, args: Dict, ctx: Dict) -> Dict:
    """Ejecuta una tool de post-venta por nombre."""
    handler = _DISPATCH.get(name)
    if handler is None:
        logger.warning("Unknown postsale tool requested", tool=name)
        return {"tool_result": f"Herramienta desconocida: {name}"}
    try:
        import inspect
        if inspect.iscoroutinefunction(handler):
            return await handler(args, ctx)
        return handler(args, ctx)
    except Exception as e:
        logger.error("Error executing postsale tool", tool=name, error=str(e))
        return {"tool_result": f"Error ejecutando {name}: {e}"}
