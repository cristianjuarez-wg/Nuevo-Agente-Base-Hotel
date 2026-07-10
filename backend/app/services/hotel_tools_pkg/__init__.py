"""
Tools (function calling) del agente de PRE-VENTA del hotel (Fase 2.3).

Antes: un solo hotel_tools.py de 1461 líneas. Ahora: paquete particionado por contexto —
info / booking / promos / restaurant / misc — sobre helpers compartidos (_shared). Este
__init__ es la FACHADA: reexporta la API pública histórica (execute_tool y los símbolos que
otros módulos importan), así el corte es 100% transparente para los llamadores.

Cada handler tiene el contrato (args, ctx) -> {"tool_result": str, ...}; execute_tool es
el dispatcher invocado por hotel_sdk_orchestrator vía @function_tool.
"""
from typing import Dict

from app.core.observability.logging_config import get_logger

# Handlers por grupo.
from app.services.hotel_tools_pkg.info import (
    _handle_info_hotel, _handle_como_llegar, _handle_comercios_amigos,
    _handle_excursiones_y_atracciones,
)
from app.services.hotel_tools_pkg.booking import (
    _handle_consultar_disponibilidad, _handle_crear_reserva, _handle_consultar_reserva,
    _handle_info_pago,
)
from app.services.hotel_tools_pkg.promos import (
    _handle_promos_vigentes, _handle_calcular_precio_promo,
)
from app.services.hotel_tools_pkg.restaurant import (
    _handle_ver_carta, _handle_armar_pedido_carta, _handle_reservar_mesa,
    _handle_comprar_voucher, _handle_registrar_pedido,
)
from app.services.hotel_tools_pkg.misc import _handle_guardar_preferencia

# Símbolos que OTROS módulos importan de hotel_tools (API pública histórica — reexport).
from app.services.hotel_tools_pkg._shared import (  # noqa: F401
    _match_menu_items, persist_preferences, _clasificar_preferencia,
)

logger = get_logger(__name__)


_DISPATCH = {
    "info_hotel": _handle_info_hotel,
    "consultar_disponibilidad": _handle_consultar_disponibilidad,
    "crear_reserva": _handle_crear_reserva,
    "consultar_reserva": _handle_consultar_reserva,
    "info_pago": _handle_info_pago,
    "como_llegar": _handle_como_llegar,
    "comercios_amigos": _handle_comercios_amigos,
    "excursiones_y_atracciones": _handle_excursiones_y_atracciones,
    "promos_vigentes": _handle_promos_vigentes,
    "calcular_precio_promo": _handle_calcular_precio_promo,
    "ver_carta": _handle_ver_carta,
    "armar_pedido_carta": _handle_armar_pedido_carta,
    "reservar_mesa": _handle_reservar_mesa,
    "comprar_voucher": _handle_comprar_voucher,
    "registrar_pedido": _handle_registrar_pedido,
    "guardar_preferencia": _handle_guardar_preferencia,
}


async def execute_tool(name: str, args: Dict, ctx: Dict) -> Dict:
    """
    Ejecuta una tool por nombre. `ctx` es un dict mutable compartido por turno.

    Returns:
        Dict con al menos la key 'tool_result' (string que se reinyecta al LLM).
    """
    handler = _DISPATCH.get(name)
    if handler is None:
        logger.warning("Unknown hotel tool requested", tool=name)
        return {"tool_result": f"Herramienta desconocida: {name}"}

    try:
        import inspect
        if inspect.iscoroutinefunction(handler):
            return await handler(args, ctx)
        return handler(args, ctx)
    except Exception as e:
        logger.error("Error executing hotel tool", tool=name, error=str(e))
        return {"tool_result": f"Error ejecutando {name}: {e}"}
