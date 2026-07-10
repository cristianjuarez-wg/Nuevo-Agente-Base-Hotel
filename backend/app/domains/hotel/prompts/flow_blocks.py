"""
Plantillas de VARIANTES del flujo comercial (Fase B del Centro).

Cada variante es un bloque de ESTILO COMERCIAL que se inyecta en {flow_block}
del prompt de pre-venta. Ajusta el estilo; NUNCA reemplaza las reglas de
seguridad, de herramientas ni el carácter del agente (jerarquía de instrucciones,
FLUJOS_Y_ESTRATEGIA.md §10.2).

Las plantillas viven en código (versionadas en git — el cerebro no se muda);
lo que vive en la base es solo la ELECCIÓN del cliente (parámetro `variante`
del flujo_preventa). "estandar" es el bloque VACÍO: el prompt actual ya es el
estilo estándar → elegirlo = paridad exacta.

Textos aprobados por el usuario el 2026-07-02 (junto con el mecanismo de
coherencia de "sin_presion": además del texto, se suprime la captura proactiva
salvo pedido expreso del huésped — ver hotel_sdk_orchestrator._variant_allows_capture).
"""

FLOW_BLOCKS = {
    # El comportamiento actual, sin agregado: paridad por construcción.
    "estandar": "",

    "proactiva": """\
ESTILO COMERCIAL DE ESTE HOTEL — CAPTACIÓN PROACTIVA (ajusta tu estilo comercial; \
NO reemplaza tus reglas de seguridad ni de herramientas):
- Apenas detectes intención de viaje (aunque sea vaga), ofrecé chequear disponibilidad \
y pedí las fechas en ese mismo mensaje.
- Si el huésped ya vio disponibilidad y sigue evaluando, buscá el cierre con tacto: \
recordale que podés dejarle la reserva lista en un minuto.
- Ante una objeción de precio, mencioná las promociones vigentes de inmediato \
(usá calcular_precio_promo) en lugar de esperar más señales.
- Proactivo NO es insistente: mantené la calidez de siempre y hacé como máximo UN \
empuje de cierre por mensaje.""",

    "sin_presion": """\
ESTILO COMERCIAL DE ESTE HOTEL — ATENCIÓN SIN PRESIÓN (ajusta tu estilo comercial; \
NO reemplaza tus reglas de seguridad ni de herramientas):
- Respondé e informá con calidez, pero NO pidas datos de contacto por iniciativa \
propia: tomalos solo si el huésped los ofrece o pide que lo contacten.
- No insistas con cerrar la reserva: ofrecé ver disponibilidad solo si el huésped \
lo pide o da fechas concretas.
- Ante una objeción de precio, no contraofertes promociones salvo que el huésped \
pregunte por descuentos.
- Tu prioridad es que se sienta bien atendido, sin sensación de venta.""",
}


def flow_block_for(variant: str) -> str:
    """Bloque de la variante; desconocida → estándar (vacío, fail-open)."""
    return FLOW_BLOCKS.get((variant or "estandar").strip().lower(), "")
