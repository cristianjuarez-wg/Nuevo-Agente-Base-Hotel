"""
Wrappers @function_tool COMPARTIDOS entre pre-venta y post-venta (Fase 6).

Antes cada orquestador (hotel_sdk_orchestrator / hotel_postsale_orchestrator) declaraba
su propia copia de cada wrapper. Como ambos delegan al MISMO handler vía execute_tool, la
única diferencia real era (a) el docstring que ve el LLM y (b) de qué builder sale el ctx.
Mantener dos cuerpos sincronizados a mano era la causa raíz de bugs reincidentes (un fix
tocaba una copia y no la otra). Acá cada tool se declara UNA sola vez; ambos orquestadores
la importan y la meten en su _TOOLS.

El ctx se obtiene por un contrato uniforme (Protocol HotelToolCtx): cada context object
implementa knowledge_ctx()/restaurant_ctx()/absorb_* apuntando a su propio builder. Así la
tool no sabe de qué rol viene, y el ctx correcto (con o sin contact_id, con o sin cards) lo
decide el context object del agente.

Los casos donde el docstring o la firma DEBEN divergir por rol (derivar_a_humano,
reservar_mesa) NO viven acá como definición única: comparten el CUERPO (helper _..._body) y
dejan wrappers delgados en cada orquestador. Ver esas sub-fases.
"""
from typing import Dict, List, Optional, Protocol, runtime_checkable

from agents import RunContextWrapper, function_tool

from app.services.hotel_tools_pkg import execute_tool


@runtime_checkable
class HotelToolCtx(Protocol):
    """Contrato que deben cumplir los context objects (HotelContext / HotelPostventaContext)
    para reusar las tools compartidas. Cada método devuelve el dict-ctx que espera execute_tool.

    - knowledge_ctx(): tools de conocimiento (solo necesitan db + args): comercios_amigos,
      excursiones_y_atracciones, info_pago, promos_vigentes, info_hotel.
    - restaurant_ctx(): tools de restaurante (necesitan session_id/contact_id/booking_code):
      ver_carta, armar_pedido_carta.
    - absorb_knowledge()/absorb_restaurant(): recuperan lo que el handler dejó en el ctx.
    """
    def knowledge_ctx(self) -> Dict: ...
    def restaurant_ctx(self) -> Dict: ...
    def absorb_knowledge(self, tool_ctx: Dict) -> None: ...
    def absorb_restaurant(self, tool_ctx: Dict) -> None: ...


# ── Tools de CONOCIMIENTO (clase B: mismo nombre y firma en ambos roles) ────────
@function_tool
async def comercios_amigos(ctx: RunContextWrapper[HotelToolCtx], rubro: str = "") -> str:
    """Devuelve los comercios amigos del hotel (gastronomía, heladerías, chocolaterías,
    restaurantes con acuerdo) y sus beneficios/descuentos para huéspedes.
    Úsala cuando el usuario pida recomendaciones de dónde comer, lugares con descuento,
    heladerías, chocolaterías o restaurantes cerca del hotel.
    `rubro` (opcional): tipo de comercio que busca (ej. "heladería", "restaurante").
    Si no hay comercios amigos para ese rubro, la herramienta devuelve un link de
    búsqueda en Google Maps; compartilo igual."""
    result = await execute_tool("comercios_amigos", {"rubro": rubro}, ctx.context.knowledge_ctx())
    return result.get("tool_result", "")


@function_tool
async def excursiones_y_atracciones(ctx: RunContextWrapper[HotelToolCtx], categoria: str = "") -> str:
    """Devuelve las EXCURSIONES y ATRACCIONES de la zona cargadas en el backoffice
    (Cerro Catedral, Circuito Chico, miradores, paseos), con su descripción y ubicación.
    Úsala cuando el huésped pregunte QUÉ HACER, qué visitar, qué paseos/excursiones hay
    cerca del hotel o pida recomendaciones de lugares para conocer.
    `categoria` (opcional): tipo de lugar (ej. "excursión", "atracción").
    NO la confundas con `comercios_amigos` (esa es para dónde COMER con descuento) ni con
    `como_llegar` (esa arma la ruta a UN destino puntual)."""
    result = await execute_tool(
        "excursiones_y_atracciones", {"categoria": categoria}, ctx.context.knowledge_ctx()
    )
    return result.get("tool_result", "")
