"""
Origen unificado de reservas, leads y contactos — fuente única de verdad.

Modelo de DOS DIMENSIONES (a prueba de futuro):
  - generated_by: "aura" (agente IA) | "human" (equipo del hotel)
  - channel:      "whatsapp" | "web" | "site" | "phone" | "desk" | "manual"

Hoy todo lo genera Aura; mañana convivirán cargas humanas (teléfono/mostrador)
distinguidas, sin rehacer el modelo. La etiqueta visible se compone de ambos.

Las vistas del backoffice consumen `key` (para elegir icono/color) y `label`.
"""
from typing import Dict, Optional

# key -> etiqueta mostrable. El front mapea la key a icono + color.
_LABELS = {
    "aura_whatsapp": "WhatsApp",   # 🤖 Aura por WhatsApp
    "aura_web": "ChatWeb",         # 🤖 Aura por el chat del sitio
    "web": "Sitio web",            # 🌐 el huésped reservó solo en el motor del sitio
    "manual": "Manual",            # 👤 carga del equipo (futuro)
}


def _make(generated_by: str, channel: str, key: str) -> Dict:
    return {
        "generated_by": generated_by,
        "channel": channel,
        "key": key,
        "label": _LABELS.get(key, "—"),
    }


def origin_from_booking(source: Optional[str], session_id: Optional[str],
                        generated_by: Optional[str] = None) -> Dict:
    """Origen de una RESERVA, derivado de source + session_id.

    Regla:
      - source "agente" + session_id "wa_..."  -> Aura · WhatsApp
      - source "agente" + session_id (otro)     -> Aura · ChatWeb
      - source "web" + session_id presente      -> Sitio web (huésped solo)
      - sin session_id (o carga humana futura)  -> Manual
    `generated_by` explícito (carga humana futura) tiene prioridad.
    """
    sid = session_id or ""
    if generated_by == "human":
        return _make("human", "manual", "manual")

    if source == "agente":
        # La reserva la hizo Aura; el canal lo da el session_id (wa_ = WhatsApp, resto = ChatWeb).
        if sid.startswith("wa_"):
            return _make("aura", "whatsapp", "aura_whatsapp")
        return _make("aura", "web", "aura_web")

    # source == "web": el motor de reserva del sitio (el huésped reservó solo). Si por
    # algún caso llegara con session_id de WhatsApp, lo respetamos como Aura·WhatsApp.
    if sid.startswith("wa_"):
        return _make("aura", "whatsapp", "aura_whatsapp")
    return _make("site", "site", "web")


def origin_from_channel(channel: Optional[str], generated_by: str = "aura") -> Dict:
    """Origen de un LEAD/CONTACTO, derivado de su canal.

    Un lead/contacto representa a la persona: hoy lo generó Aura conversando, así que
    `generated_by="aura"` por defecto. A futuro, un lead humano pasaría "human".
    """
    if generated_by == "human":
        return _make("human", channel or "manual", "manual")
    if channel == "whatsapp":
        return _make("aura", "whatsapp", "aura_whatsapp")
    if channel == "web":
        return _make("aura", "web", "aura_web")
    # canal desconocido -> ChatWeb por defecto (un lead siempre pasó por el chat)
    return _make("aura", "web", "aura_web")
