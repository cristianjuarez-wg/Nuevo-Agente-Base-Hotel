"""Handlers de hotel tools — grupo misc (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared


def _handle_derivar_a_humano(args: Dict, ctx: Dict) -> Dict:
    """Deriva la conversación a una persona del equipo (Fase 4).

    Si HAY atención humana disponible ahora: marca la conversación como 'needs_human' (el
    backoffice la resalta y avisa) + adjunta un resumen de la charla, y le confirma al huésped
    que en un momento lo atienden. Si NO hay atención: no promete un pase en vivo; deja constancia
    para seguimiento e informa que el equipo lo retomará (el prompt guía tomar los datos; la
    escalación de ticket / captura de lead siguen disponibles como tools de cada agente)."""
    db: Optional[Session] = ctx.get("db")
    session_id = ctx.get("session_id") or ""
    motivo = (args.get("motivo") or "").strip()
    if db is None or not session_id:
        return {"tool_result": "Le avisé al equipo que necesitás una persona; en breve te contactan."}

    from app.services import human_attention_service, conversation_control_service as ctrl
    disponible = human_attention_service.is_human_available(db)

    if disponible:
        # Resumen puntual de la charla para que el humano la retome con contexto.
        try:
            from app.services.summary_service import summarize_session
            resumen = summarize_session(session_id, db)
        except Exception:  # noqa: BLE001
            resumen = ""
        ctrl.flag_needs_human(db, session_id, motivo=motivo, summary=resumen)
        return {
            "tool_result": "Ya avisé a una persona del equipo, que va a tomar la conversación en "
                           "un momento. Quedate en línea que enseguida te atienden. 😊",
            "handoff": "live",
        }

    # Sin atención en vivo: no prometer pase inmediato. El prompt ya instruye tomar datos/registrar
    # para seguimiento; acá dejamos la marca informativa (sin activar toast de 'tomar ahora').
    return {
        "tool_result": "En este momento no tengo una persona disponible en vivo, pero dejo tu "
                       "consulta registrada para que el equipo te contacte apenas haya atención. "
                       "Si querés, decime cómo prefieren contactarte.",
        "handoff": "deferred",
    }


def _handle_guardar_preferencia(args: Dict, ctx: Dict) -> Dict:
    """Guarda una preferencia del huésped en su perfil (para tenerla siempre en cuenta).

    Categorías (por el `tipo` que manda el agente):
      - 'alergia'  → seguridad alimentaria (allergies)
      - 'dieta'    → vegano/vegetariano/sin TACC (dietary)
      - 'acompañante'/'familia' → con quién viaja (family)
      - 'servicio' → servicio que suele usar, ej. spa, ski storage (services_used)
      - 'nota'     → observación libre para el hotel (notes)
    Sin `tipo`, se clasifica por el texto entre alergia y dieta (comportamiento histórico).
    """
    db: Optional[Session] = ctx.get("db")
    if db is None:
        return {"tool_result": "Error interno: sin conexión a base de datos."}

    contact = _resolve_contact(db, ctx)
    if not contact:
        return {"tool_result": "Anotado. (No pude vincularlo a un perfil, pero lo tendré en cuenta en esta charla.)"}

    nuevas = args.get("preferencias") or []
    if isinstance(nuevas, str):
        nuevas = [nuevas]
    nuevas = [str(p).strip().lower() for p in nuevas if str(p).strip()]
    if not nuevas:
        return {"tool_result": "¿Qué querés que guarde? (ej: vegetariano, alergia al maní, viaja con su hijo, suele usar el spa)"}

    tipo_hint = args.get("tipo")
    agregados = persist_preferences(db, contact, nuevas, tipo_hint)

    # Mensaje de confirmación por categoría; la alergia se confirma con énfasis de seguridad.
    partes = []
    if agregados.get("allergies"):
        partes.append(
            f"⚠️ Anoté tu alergia/intolerancia ({', '.join(agregados['allergies'])}). "
            "La voy a tener SIEMPRE en cuenta: no te voy a sugerir nada que la contenga."
        )
    if agregados.get("dietary"):
        partes.append(
            f"Guardé tus preferencias ({', '.join(agregados['dietary'])}) en tu perfil. "
            "Las voy a usar para sugerirte opciones acordes. 🌿"
        )
    if agregados.get("family"):
        partes.append(f"Anoté que viajás con {', '.join(agregados['family'])}. 😊")
    if agregados.get("services_used"):
        partes.append(f"Guardé que solés usar: {', '.join(agregados['services_used'])}.")
    if agregados.get("notes"):
        partes.append("Anoté tu observación en el perfil.")
    return {
        "tool_result": " ".join(partes) or "Listo, lo guardé en tu perfil.",
        "saved": True,
    }
