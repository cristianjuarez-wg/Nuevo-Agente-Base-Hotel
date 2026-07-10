"""Handlers de hotel tools — grupo misc (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared


def _handle_guardar_preferencia(args: Dict, ctx: Dict) -> Dict:
    """Guarda una preferencia/alergia del huésped en su perfil (para tener siempre en cuenta).

    Distingue ALERGIAS (seguridad alimentaria, categoría `allergies`) de las preferencias
    dietéticas (vegano, vegetariano, sin TACC → `dietary`). El agente puede mandar un
    `tipo` ('alergia'|'dieta'); si no, se clasifica por el texto.
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
        return {"tool_result": "¿Qué preferencia o alergia querés que guarde? (ej: vegetariano, sin TACC, alergia al maní)"}

    tipo_hint = args.get("tipo")

    try:
        profile = contact_service.get_guest_profile(contact.id, db)
        prefs = (profile or {}).get("preferences") or {}
    except Exception:
        prefs = {}

    nuevas_alergias, nuevas_dietas = persist_preferences(db, contact, nuevas, tipo_hint)

    # Mensaje de confirmación diferenciado: la alergia se confirma con énfasis.
    partes = []
    if nuevas_alergias:
        partes.append(
            f"⚠️ Anoté tu alergia/intolerancia ({', '.join(nuevas_alergias)}). "
            "La voy a tener SIEMPRE en cuenta: no te voy a sugerir nada que la contenga."
        )
    if nuevas_dietas:
        partes.append(
            f"Guardé tus preferencias ({', '.join(nuevas_dietas)}) en tu perfil. "
            "Las voy a usar para sugerirte opciones acordes. 🌿"
        )
    return {
        "tool_result": " ".join(partes) or "Listo, lo guardé en tu perfil.",
        "saved": True,
    }
