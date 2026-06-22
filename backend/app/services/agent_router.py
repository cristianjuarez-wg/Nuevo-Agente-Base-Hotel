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
# Import a nivel módulo para que la tabla action_plans se cree al arrancar (create_all
# vive en el modelo). El asesor la usa para los planes de acción de largo plazo.
from app.models import action_plan as _action_plan  # noqa: F401

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
        return await _route_staff(db, phone, message)

    # Huésped: flujo actual sin cambios (el agente concierge usa su propio session_id wa_).
    from app.services.agent_service import agent_service
    session_id = "wa_" + (phone or "").lstrip("+")
    return await agent_service.chat(db, message, session_id)


# Cuántos mensajes del historial persistido rehidratar para el asesor (relación de
# largo plazo: SIN ventana de tiempo, a diferencia de Aura). El orquestador igual acota
# cuántos pasa al modelo (MAX_HISTORY_MESSAGES).
_OWNER_REHYDRATE_LIMIT = 30


def _rehydrate_owner_history(db: Session, session_id: str) -> List[Dict]:
    """Reconstruye la memoria del asesor desde la DB (context_type='management'), SIN
    filtro de tiempo: el vínculo con el CEO es de largo plazo. Últimos N en orden cronológico."""
    if db is None:
        return []
    try:
        from app.models.conversation_message import ConversationMessage
        rows = (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.session_id == session_id,
                ConversationMessage.context_type == "management",
            )
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .limit(_OWNER_REHYDRATE_LIMIT)
            .all()
        )
        rows.reverse()
        return [{"role": m.role, "content": m.content} for m in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo rehidratar memoria del asesor", session_id=session_id, error=str(e))
        return []


async def _route_owner(db: Session, phone: str, message: str) -> Dict:
    """Despacha al consultor de gerencia con memoria PERSISTENTE de largo plazo.

    El historial se guarda en conversation_messages (context_type='management') y se
    rehidrata desde la DB en cache-miss (reinicios/deploys), sin ventana de expiración.
    """
    from app.services.owner_orchestrator import owner_orchestrator
    from app.services.agent_service import agent_service
    from app.models.staff import StaffMember
    from app.utils.phone_normalizer import normalize_phone

    norm = normalize_phone(phone) or phone
    session_id = "owner_" + norm.lstrip("+")

    # Memoria en RAM o, si se perdió (reinicio), rehidratada desde la DB (largo plazo).
    if session_id in _role_histories:
        history = _role_histories[session_id]
    else:
        history = _rehydrate_owner_history(db, session_id)
        _role_histories[session_id] = history

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

    # Persistir en la DB (memoria de largo plazo del asesor). Usamos una sesión NUEVA: la
    # `db` del turno ya pasó por el orquestador (OpenAI Agents SDK) y puede quedar en un
    # estado transaccional que impida el commit. Best-effort: un fallo no rompe la respuesta.
    try:
        from app.models.database import SessionLocal
        mem_db = SessionLocal()
        try:
            agent_service._save_message_to_db(
                db=mem_db, session_id=session_id, role="user", content=message,
                context_type="management",
            )
            agent_service._save_message_to_db(
                db=mem_db, session_id=session_id, role="assistant", content=assistant_content,
                context_type="management", model_used=(result.get("usage") or {}).get("model"),
            )
        finally:
            mem_db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo persistir la memoria del asesor", session_id=session_id, error=str(e))

    return result


async def _route_staff(db: Session, phone: str, message: str) -> Dict:
    """Despacha al coordinador de operaciones del equipo (rol staff).

    Memoria conversacional en RAM por sesión (`staff_<phone>`). La identidad del miembro se
    resuelve por teléfono (StaffMember). El audio ya llega transcrito desde el webhook, así
    que para el orquestador es indistinto texto o voz.
    """
    from app.services.staff_orchestrator import staff_orchestrator
    from app.models.staff import StaffMember
    from app.utils.phone_normalizer import normalize_phone

    norm = normalize_phone(phone) or phone
    session_id = "staff_" + norm.lstrip("+")

    staff = db.query(StaffMember).filter(StaffMember.phone == norm).first()
    if not staff:
        # No debería pasar (resolve_role ya lo marcó staff), pero por las dudas.
        return {"response": "No te tengo registrado en el equipo. Avisá a recepción para que te den de alta. 🙌"}

    history = _role_histories.setdefault(session_id, [])
    result = await staff_orchestrator.run(db, staff, message, session_id, history)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": result.get("response", "")})
    if len(history) > 30:
        _role_histories[session_id] = history[-30:]

    return result
