"""Utilidades para derivar el canal y el teléfono a partir del session_id.

Los session_id se prefijan para distinguir el canal de origen:
  - wa_<phone>    → WhatsApp (huésped)
  - ig_<IGSID>    → Instagram (huésped)
  - web-...       → Web (huésped)
  - owner_...     → WhatsApp de owner/gerencia
  - staff_...     → WhatsApp de staff (operaciones)
  - otros/UUID     → Web por defecto

Este módulo centraliza la lógica para evitar que el prefijo se repita
esparcido en el código (deuda técnica H). Usar siempre estas funciones en
lugar de `session_id.startswith(...)`.
"""
from typing import List, Optional


def channel_from_session(session_id: Optional[str]) -> str:
    """Devuelve el canal (whatsapp | instagram | web) asociado a un session_id."""
    sid = session_id or ""
    if sid.startswith("wa_") or sid.startswith("owner_") or sid.startswith("staff_"):
        return "whatsapp"
    if sid.startswith("ig_"):
        return "instagram"
    return "web"


def is_whatsapp_session(session_id: Optional[str]) -> bool:
    return (session_id or "").startswith("wa_")


def is_instagram_session(session_id: Optional[str]) -> bool:
    return (session_id or "").startswith("ig_")


def is_web_session(session_id: Optional[str]) -> bool:
    return not (is_whatsapp_session(session_id) or is_instagram_session(session_id))


def phone_from_session(session_id: Optional[str]) -> Optional[str]:
    """Extrae el teléfono (+...) de un session_id de WhatsApp."""
    sid = session_id or ""
    if sid.startswith("wa_"):
        return "+" + sid[3:]
    return None


def session_prefixes_for_role(role: str) -> List[str]:
    """Prefijos de session_id que pertenecen a cada rol (métricas/filtrado)."""
    if role == "management":
        return ["owner_"]
    if role == "staff":
        return ["staff_"]
    # guest: WhatsApp, Instagram y web.
    return ["wa_", "ig_", "web-", "web_"]
