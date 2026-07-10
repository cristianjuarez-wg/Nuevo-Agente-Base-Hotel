"""
Capacidades LEGIBLES de cada agente, para mostrar en el backoffice (rediseño F0.2).

El usuario final no necesita ver las ~28 tool keys crudas con prefijos internos
(`presale.ver_carta` y `postsale.ver_carta` son la MISMA capacidad para él). Este módulo
traduce las tools de un rol a un puñado de GRUPOS legibles con una línea cada uno.

Fuente de verdad de las tools: `agent_specs.py` (SPECS). Acá solo vive la PRESENTACIÓN:
cada grupo declara qué tool keys lo componen (por rol) y su resumen en lenguaje humano.
Si una tool nueva no cae en ningún grupo, va a parar a "Otras capacidades" — señal de que
hay que sumarla a un grupo acá.
"""
from typing import Dict, List

from app.domains.hotel.agent_specs import SPECS


# Grupos curados por rol. Cada grupo: {group, summary, keys}. Las keys se comparan por el
# nombre SIN prefijo (así presale.ver_carta y postsale.ver_carta caen en el mismo grupo).
_CAPABILITY_GROUPS: Dict[str, List[dict]] = {
    "guest": [
        {
            "group": "Reservas y precios",
            "summary": "Consulta disponibilidad, cotiza y crea o busca reservas de habitaciones.",
            "keys": {"consultar_disponibilidad", "crear_reserva", "consultar_reserva",
                     "calcular_precio_promo"},
        },
        {
            "group": "Restaurante",
            "summary": "Muestra la carta, arma pedidos, reserva mesa y vende vouchers gastronómicos.",
            "keys": {"ver_carta", "armar_pedido_carta", "registrar_pedido", "reservar_mesa",
                     "comprar_voucher"},
        },
        {
            "group": "Información y llegada",
            "summary": "Responde sobre el hotel y sus servicios, cómo llegar y las fotos de las habitaciones.",
            "keys": {"info_hotel", "consultar_info_hotel", "como_llegar", "ver_fotos_habitacion"},
        },
        {
            "group": "Extras y recomendaciones",
            "summary": "Recomienda comercios amigos, excursiones y atracciones, y las promociones vigentes.",
            "keys": {"comercios_amigos", "excursiones_y_atracciones", "promos_vigentes",
                     "promociones_vigentes"},
        },
        {
            "group": "Pagos y preferencias",
            "summary": "Comparte los datos de pago y guarda las preferencias del huésped para su estadía.",
            "keys": {"info_pago", "consultar_pago", "guardar_preferencia", "registrar_preferencia"},
        },
        {
            "group": "Post-venta y atención",
            "summary": "Toma pedidos de servicio durante la estadía y escala los reclamos al equipo.",
            "keys": {"solicitar_servicio", "analizar_escalacion"},
        },
    ],
    "management": [
        {
            "group": "Ocupación e ingresos",
            "summary": "Analiza ocupación, ingresos, tarifas y el ranking de habitaciones del hotel.",
            "keys": {"consultar_ocupacion", "consultar_ingresos", "analizar_ingresos",
                     "analizar_ocupacion", "ranking_habitaciones", "comparar_periodos",
                     "consultar_habitacion"},
        },
        {
            "group": "Comercial y leads",
            "summary": "Reporta leads y el embudo de conversión de consultas a reservas.",
            "keys": {"consultar_leads", "consultar_embudo"},
        },
        {
            "group": "Operación y soporte",
            "summary": "Resume la operación del día, las quejas y los tickets de soporte.",
            "keys": {"operacion_hoy", "consultar_quejas", "consultar_soporte", "buscar_huesped"},
        },
        {
            "group": "Equipo y conocimiento",
            "summary": "Consulta el equipo del hotel y el conocimiento cargado por la gerencia.",
            "keys": {"consultar_equipo", "consultar_conocimiento", "consultar_resumen_negocio"},
        },
        {
            "group": "Planes de acción",
            "summary": "Registra, consulta y actualiza los planes de acción acordados con la gerencia.",
            "keys": {"registrar_plan", "consultar_planes", "actualizar_plan"},
        },
    ],
    "staff": [
        {
            "group": "Tickets e incidencias",
            "summary": "Registra incidencias, consulta los tickets asignados y los marca como resueltos.",
            "keys": {"resolver_ticket", "reportar_incidencia", "mis_tickets"},
        },
    ],
}


def _tool_names_for_role(role: str) -> set:
    """Nombres de tool (sin prefijo) que tiene un rol, uniendo todas sus specs."""
    names = set()
    for spec in SPECS.values():
        if spec.display_role != role:
            continue
        for key in spec.tools:
            names.add(key.split(".", 1)[-1])  # quita el prefijo presale./postsale./owner./staff.
    return names


def capability_groups_for_role(role: str) -> List[dict]:
    """Grupos legibles de capacidades de un rol, según las tools que REALMENTE tiene.

    Solo devuelve un grupo si el agente tiene al menos una tool de ese grupo. Las tools que
    no caen en ningún grupo curado se juntan en 'Otras capacidades' (para no ocultarlas y
    delatar que falta curarlas).
    """
    have = _tool_names_for_role(role)
    if not have:
        return []

    groups: List[dict] = []
    covered: set = set()
    for g in _CAPABILITY_GROUPS.get(role, []):
        present = g["keys"] & have
        if present:
            groups.append({"group": g["group"], "summary": g["summary"]})
            covered |= present

    leftover = have - covered
    if leftover:
        groups.append({
            "group": "Otras capacidades",
            "summary": "Herramientas adicionales del empleado.",
        })
    return groups
