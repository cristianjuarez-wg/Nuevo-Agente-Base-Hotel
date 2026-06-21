"""
Dispatcher por ROL del canal de WhatsApp — punto único de ruteo multi-rol.

El webhook de WhatsApp llama SOLO a route_whatsapp(); este módulo resuelve el rol del
remitente y despacha al agente correcto, sin que el webhook conozca los detalles de cada
agente. Sumar un rol nuevo = una rama acá, nada más.

Roles y agentes:
  - guest → agente concierge actual (agent_service.chat) — flujo de huésped, sin cambios.
  - owner → agente de gerencia / consultor (owner_orchestrator) — BI + recomendaciones.
  - staff → reservado para el Caso 1 (cerrar tickets por audio); por ahora, stub.

Sesión por rol: el session_id se prefija distinto para no mezclar historiales
(`wa_` huésped, `owner_` gerencia, `staff_` operaciones).
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.role_service import resolve_role
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Historial en memoria por sesión de rol interno (owner/staff). El flujo de huésped ya
# maneja su propio historial dentro de agent_service; acá solo guardamos el de roles
# internos para dar memoria conversacional al consultor.
_role_histories: Dict[str, List[Dict]] = {}

# Último gráfico (chart_url) enviado por sesión del owner. Evita reenviar el MISMO gráfico
# en turnos seguidos (el modelo a veces vuelve a llamar la tool aunque ya lo mandó).
_last_owner_chart: Dict[str, str] = {}


async def route_whatsapp(db: Session, phone: str, message: str) -> Dict:
    """Rutea un mensaje de WhatsApp al agente correcto según el rol del teléfono.

    Devuelve un dict con al menos {"response": str}; puede incluir {"chart_url": str}
    cuando el agente de gerencia generó un gráfico. NO maneja el envío (eso es del webhook).
    """
    role = resolve_role(phone, db)

    if role == "owner":
        return await _route_owner(db, phone, message)

    if role == "staff":
        # Caso 1 (cerrar tickets por audio) — todavía no implementado.
        logger.info("WhatsApp staff message (no implementado aún)", phone=phone[-4:])
        return {
            "response": ("¡Hola! La función de gestión de tareas para el equipo está en "
                         "preparación. Por ahora podés coordinar con recepción. 🙌"),
        }

    # Huésped: flujo actual sin cambios (el agente concierge usa su propio session_id wa_).
    from app.services.agent_service import agent_service
    session_id = "wa_" + (phone or "").lstrip("+")
    return await agent_service.chat(db, message, session_id)


async def _route_owner(db: Session, phone: str, message: str) -> Dict:
    """Despacha al consultor de gerencia con memoria de sesión propia."""
    from app.services.owner_orchestrator import owner_orchestrator
    from app.models.staff import StaffMember
    from app.utils.phone_normalizer import normalize_phone

    norm = normalize_phone(phone) or phone
    session_id = "owner_" + norm.lstrip("+")
    history = _role_histories.setdefault(session_id, [])

    # Nombre del dueño para personalizar el saludo del consultor.
    owner_name = ""
    try:
        member = db.query(StaffMember).filter(StaffMember.phone == norm).first()
        owner_name = member.name if member else ""
    except Exception:  # noqa: BLE001
        pass

    result = await owner_orchestrator.run(db, message, session_id, history, owner_name=owner_name)

    # Anti-duplicado de gráfico: si el chart_url de este turno es el MISMO que el último
    # enviado en la sesión, no lo reenviamos (el modelo a veces re-llama la tool aunque ya
    # lo mandó). El texto del agente ya avisa que lo envió arriba (regla del prompt).
    chart_url = result.get("chart_url")
    if chart_url:
        if _last_owner_chart.get(session_id) == chart_url:
            result["chart_url"] = None  # mismo gráfico → no reenviar
        else:
            _last_owner_chart[session_id] = chart_url

    # Actualizar memoria del hilo (acotada). Si en este turno se envió un gráfico (uno
    # nuevo), lo anotamos en el mensaje del assistant (nota interna, no la ve el dueño)
    # para que el agente sepa que ya lo mandó y no lo repita.
    assistant_content = result.get("response", "")
    if result.get("chart_url"):
        assistant_content += "\n\n[Nota interna: en este turno ya se envió al dueño un gráfico de los datos consultados.]"
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": assistant_content})
    if len(history) > 40:
        _role_histories[session_id] = history[-40:]

    return result
