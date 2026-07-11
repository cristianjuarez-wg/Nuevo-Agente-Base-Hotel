"""Handlers de hotel tools — grupo misc (Fase 2.3, extraído de hotel_tools.py sin cambios)."""
from datetime import date  # noqa: F401
from typing import Dict, Optional  # noqa: F401
from app.services.hotel_tools_pkg._shared import *  # noqa: F401,F403
from app.services.hotel_tools_pkg import _shared


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
