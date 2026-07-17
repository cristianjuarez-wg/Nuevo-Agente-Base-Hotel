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


@function_tool
async def info_pago(ctx: RunContextWrapper[HotelToolCtx], consulta: str = "") -> str:
    """Devuelve los datos EXACTOS de pago y transferencia bancaria del hotel: medios de
    pago aceptados, y para transferencias el titular, banco, CBU y alias.
    Úsala SOLO cuando el usuario pregunte específicamente cómo pagar, dónde/cómo transferir,
    pida el CBU, el alias o los datos bancarios. Para cualquier OTRA consulta del hotel
    (servicios, habitaciones, políticas, ubicación) usá `info_hotel`, no esta.
    El parámetro `consulta` es la pregunta del usuario (opcional, informativo).
    Devolvé los datos tal cual, sin inventar ni alterar."""
    result = await execute_tool("info_pago", {"consulta": consulta}, ctx.context.knowledge_ctx())
    return result.get("tool_result", "")


@function_tool
async def promos_vigentes(ctx: RunContextWrapper[HotelToolCtx], consulta: str = "") -> str:
    """Devuelve las promociones y ofertas especiales VIGENTES del hotel en este momento,
    con descripción de cada una, el tipo de descuento y las condiciones.
    Úsala SIEMPRE que el usuario pregunte EN GENERAL sobre promociones, ofertas, descuentos,
    tarifas especiales o 'qué promociones tienen' (listado informativo).
    Para CALCULAR el precio con descuento de una estadía concreta, usá `calcular_precio_promo`.
    Devolvé los datos tal cual, sin inventar ni modificar ningún beneficio."""
    result = await execute_tool("promos_vigentes", {"consulta": consulta}, ctx.context.knowledge_ctx())
    return result.get("tool_result", "")


# ── Tools de RESTAURANTE (necesitan session_id/contact_id/booking_code del ctx) ──
@function_tool
async def ver_carta(ctx: RunContextWrapper[HotelToolCtx], categoria: str = "") -> str:
    """Devuelve la carta de nuestro restaurante (platos, precios, tags dietéticos) y un link
    para que el cliente arme su pedido en la pantalla de carrito.
    Úsala cuando pregunten por el menú, qué hay para comer/tomar, room service o pedir comida.
    `categoria` opcional filtra (ej. "tapas", "postre", "trago"). Si el cliente tiene
    preferencias dietéticas guardadas, sugerí acorde."""
    tool_ctx = ctx.context.restaurant_ctx()
    result = await execute_tool("ver_carta", {"categoria": categoria}, tool_ctx)
    ctx.context.absorb_restaurant(tool_ctx)
    return result.get("tool_result", "")


@function_tool
async def armar_pedido_carta(ctx: RunContextWrapper[HotelToolCtx], items_texto: str = "") -> str:
    """Cuando el cliente diga POR TEXTO qué quiere comer/tomar (ej. "quiero el ojo de bife y una
    pinta"), usá esta tool para devolverle la carta interactiva YA con esos platos precargados,
    para que confirme o ajuste y elija dónde lo quiere. Pasale en `items_texto` lo que pidió,
    tal cual. Si algún plato no se reconoce, el sistema te avisa para que lo aclares (NUNCA
    inventes platos ni precios)."""
    tool_ctx = ctx.context.restaurant_ctx()
    result = await execute_tool("armar_pedido_carta", {"items_texto": items_texto}, tool_ctx)
    ctx.context.absorb_restaurant(tool_ctx)
    return result.get("tool_result", "")


# ── Cuerpo compartido de tools cuyo DOCSTRING diverge legítimamente por rol ──────
# derivar_a_humano: el docstring de post referencia tools hermanas (analizar_escalacion,
# solicitar_servicio) que no existen en pre. El bug reincidente (x2) era del CUERPO, no
# del texto: se comparte el cuerpo acá y cada orquestador deja un wrapper delgado con su
# propio docstring. El handler solo usa db + session_id, presentes en restaurant_ctx() de
# ambos roles.
async def derivar_a_humano_body(ctx: RunContextWrapper[HotelToolCtx], motivo: str = "") -> str:
    tool_ctx = ctx.context.restaurant_ctx()
    result = await execute_tool("derivar_a_humano", {"motivo": motivo}, tool_ctx)
    return result.get("tool_result", "")


# reservar_mesa: la FIRMA diverge por rol. Pre-venta expone codigo_reserva al LLM (el huésped
# puede dar su HTL-XXXX); post-venta NO lo expone y lo inyecta desde booking.code. El cuerpo
# (armar args + execute_tool + absorb) es idéntico → se comparte acá; cada orquestador deja un
# wrapper delgado que resuelve codigo_reserva a su manera y llama a este body.
async def reservar_mesa_body(
    ctx: RunContextWrapper[HotelToolCtx], fecha: str, turno: str, personas: int,
    nombre: str, codigo_reserva: str, notas: str,
) -> str:
    tool_ctx = ctx.context.restaurant_ctx()
    result = await execute_tool("reservar_mesa", {
        "fecha": fecha, "turno": turno, "personas": personas,
        "nombre": nombre, "codigo_reserva": codigo_reserva, "notas": notas,
    }, tool_ctx)
    ctx.context.absorb_restaurant(tool_ctx)
    return result.get("tool_result", "")
