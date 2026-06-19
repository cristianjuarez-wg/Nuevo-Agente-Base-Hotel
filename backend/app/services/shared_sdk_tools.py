"""
Tools del OpenAI Agents SDK compartidas entre los agentes PRE-VENTA y POST-VENTA.

Sólo viven acá las tools verdaderamente transversales: read-only, sin lógica de
negocio propia de una etapa y sin mutar el contexto del turno. Hoy, la única que
califica es `obtener_clima` — útil tanto para recomendar un destino (pre-venta)
como para acompañar al cliente que ya está de viaje (post-venta: "¿llevo paraguas
mañana?").

Las tools específicas de cada etapa (catálogo de paquetes, eventos como gancho
comercial, análisis de severidad, estado de vuelo, contacto de proveedor) NO van
acá: dependen de contexto exclusivo de su flujo.

El handler subyacente `_handle_obtener_clima` (agent_tools.execute_tool) sólo lee
`ciudad`/`pais` de los argumentos del LLM y NO toca el ctx, por lo que el mismo
objeto-tool es seguro de reusar entre `PreventaContext` y `PostventaContext`.
"""
from typing import Any

from agents import RunContextWrapper, function_tool

from app.services.agent_tools import execute_tool


@function_tool
async def obtener_clima(
    ctx: RunContextWrapper[Any], ciudad: str, pais: str = "", fecha: str = ""
) -> str:
    """Obtiene el clima de un destino, consciente de la FECHA del viaje.

    En PRE-VENTA sirve para enriquecer la recomendación (qué empacar, mejor época). En
    POST-VENTA sirve para acompañar al cliente que ya está de viaje (qué ropa llevar).
    Usar solo con un destino concreto.

    Parámetro `fecha` (YYYY-MM-DD, opcional):
    - Pasá la fecha del viaje cuando la conozcas: en POST-VENTA es la fecha de salida del
      paquete (está en el contexto); en PRE-VENTA, la que mencione el usuario.
    - Si el usuario pregunta por el clima de HOY o de esta semana, omitila o pasá la fecha cercana.
    - Si la fecha es lejana (más de ~2 semanas), la herramienta te indicará que des el
      promedio estacional histórico en vez de un pronóstico exacto. Seguí esa instrucción
      y aclarale al cliente que es un promedio típico, no un pronóstico."""
    # El handler de clima no usa ni muta el contexto del turno; un dict vacío basta.
    # Igual pasamos as_tool_ctx() si el contexto lo expone, por robustez.
    context_obj = getattr(ctx, "context", None)
    tool_ctx = context_obj.as_tool_ctx() if hasattr(context_obj, "as_tool_ctx") else {}
    result = await execute_tool(
        "obtener_clima", {"ciudad": ciudad, "pais": pais, "fecha": fecha}, tool_ctx
    )
    return result.get("tool_result", "")
