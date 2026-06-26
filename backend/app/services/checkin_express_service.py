"""
Check-in Express por WhatsApp — flujo GUIADO y DETERMINÍSTICO (fuera del LLM).

El huésped adelanta su check-in desde WhatsApp en pasos cortos que Aura guía:
  1. confirm_identity → confirma su reserva (responde "sí")
  2. await_arrival    → indica la hora estimada de llegada
  3. await_document   → manda una foto del documento (la recibe el gate de media)
  4. done             → completado

DISEÑO: NO pasa por el agente/LLM. Es una máquina de estados pura — no gasta tokens
ni arriesga alucinación. La fuente de verdad del PASO es Booking.pre_checkin["step"]
(persistente en la BD, sobrevive reinicios); el conversation_state_manager se usa como
índice rápido en RAM (session_id → code) pero el estado real vive en la reserva.

Cada función devuelve el texto que Aura debe enviar por WhatsApp (textos fijos cálidos,
sin LLM). El webhook se encarga del envío.
"""
import re
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.hotel import Booking
from app.services.conversation_state_manager import conversation_state_manager
from app.utils.timezone_utils import now_argentina
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Pasos del flujo (se guardan en Booking.pre_checkin["step"]).
STEP_CONFIRM = "confirm_identity"
STEP_ARRIVAL = "await_arrival"
STEP_DOCUMENT = "await_document"
STEP_DONE = "done"

# Marca en el estado del conversation_state_manager para identificar el flujo.
_FLOW = "checkin_express"

_HOTEL_PHONE = "+54 294-474-6200"


def _now() -> str:
    return now_argentina().isoformat()


def _get_booking_by_session(db: Session, session_id: str) -> Optional[Booking]:
    """Encuentra la reserva en check-in express activa para esta sesión de WhatsApp.

    Primero por el índice en RAM (session_id → code); si no está (reinicio del server),
    cae a buscar por session_id una reserva con pre_checkin en progreso.
    """
    st = conversation_state_manager.get_state(session_id)
    code = st.get("code") if st and st.get("flow") == _FLOW else None
    if code:
        b = db.query(Booking).filter(Booking.code == code).first()
        if b:
            return b
    # Fallback: reconstruir desde la BD (sobrevive reinicios del proceso).
    b = (
        db.query(Booking)
        .filter(Booking.session_id == session_id)
        .order_by(Booking.id.desc())
        .first()
    )
    if b and (b.pre_checkin or {}).get("step") in (STEP_CONFIRM, STEP_ARRIVAL, STEP_DOCUMENT):
        return b
    return None


def is_in_flow(db: Session, session_id: str) -> bool:
    """True si esta sesión tiene un check-in express en curso (no terminado)."""
    b = _get_booking_by_session(db, session_id)
    return bool(b and (b.pre_checkin or {}).get("step") in (STEP_CONFIRM, STEP_ARRIVAL, STEP_DOCUMENT))


def awaiting_document(db: Session, session_id: str) -> bool:
    """True si la sesión está esperando la foto del documento (para el gate de media)."""
    b = _get_booking_by_session(db, session_id)
    return bool(b and (b.pre_checkin or {}).get("step") == STEP_DOCUMENT)


def _save(db: Session, booking: Booking, **fields) -> None:
    """Actualiza Booking.pre_checkin (dict) y persiste (flag_modified para JSON mutable)."""
    data = dict(booking.pre_checkin or {})
    data.update(fields)
    booking.pre_checkin = data
    flag_modified(booking, "pre_checkin")
    db.commit()


def start(db: Session, booking: Booking) -> str:
    """Arranca el flujo: setea estado y devuelve el primer mensaje (confirmar reserva)."""
    session_id = booking.session_id or ("wa_" + (booking.guest_phone or "").lstrip("+"))
    _save(db, booking, status="in_progress", step=STEP_CONFIRM, started_at=_now())
    conversation_state_manager.set_state(session_id, {"flow": _FLOW, "code": booking.code})

    nombre = (booking.guest_name or "").split(" ")[0] or "¡Hola!"
    ci = booking.check_in.strftime("%d/%m") if booking.check_in else "—"
    co = booking.check_out.strftime("%d/%m") if booking.check_out else "—"
    hab = booking.room.room_type if booking.room else "tu habitación"
    return (
        f"¡Hola {nombre}! 😊 Soy Aura, del Hampton by Hilton Bariloche. Te escribo para que "
        f"adelantes tu *check-in* y al llegar solo retires tu llave, sin esperas.\n\n"
        f"Tu reserva *{booking.code}*:\n"
        f"🛏️ {hab}\n📅 Del {ci} al {co}\n\n"
        f"¿Confirmás que está todo bien? Respondé *SÍ* para empezar (o *CANCELAR* para hacerlo en recepción)."
    )


def cancel(db: Session, session_id: str) -> str:
    """Cancela el flujo en curso (el huésped hará el check-in en recepción)."""
    b = _get_booking_by_session(db, session_id)
    if b:
        _save(db, b, status="pending", step=None)
    conversation_state_manager.clear_state(session_id)
    return ("Sin problema 🙂 Hacemos tu check-in cuando llegues a recepción. "
            "¡Te esperamos en Bariloche! Si necesitás algo, escribime.")


def _parse_arrival(text: str) -> Optional[str]:
    """Extrae una hora de llegada del texto (HH:MM, '18hs', '6 de la tarde' simple). None si no."""
    t = (text or "").lower().strip()
    # HH:MM o HH.MM
    m = re.search(r"\b([01]?\d|2[0-3])[:\.]([0-5]\d)\b", t)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    # "18 hs", "18hs", "18 h", "a las 18"
    m = re.search(r"\b([01]?\d|2[0-3])\s*(hs|h|horas?)\b", t)
    if m:
        return f"{int(m.group(1)):02d}:00"
    m = re.search(r"a\s*las\s*([01]?\d|2[0-3])\b", t)
    if m:
        return f"{int(m.group(1)):02d}:00"
    return None


def handle_text_step(db: Session, session_id: str, text: str) -> str:
    """Procesa un mensaje de TEXTO según el paso actual. Devuelve el mensaje de Aura.

    Es determinístico (sin LLM). El gate del webhook llama acá cuando la sesión está en
    el flujo y NO es una imagen.
    """
    b = _get_booking_by_session(db, session_id)
    if not b:
        return ("No encontré tu check-in en curso. Si querés adelantarlo, avisanos y te "
                "reenviamos el enlace 🙂")
    step = (b.pre_checkin or {}).get("step")
    low = (text or "").strip().lower()

    # Comando de cancelación en cualquier paso.
    if low in ("cancelar", "cancela", "cancel", "no gracias", "no, gracias"):
        return cancel(db, session_id)

    if step == STEP_CONFIRM:
        if low in ("si", "sí", "si!", "sí!", "dale", "ok", "confirmo", "correcto", "perfecto", "listo"):
            _save(db, b, step=STEP_ARRIVAL)
            return ("¡Genial! 🙌 ¿A qué *hora aproximada* pensás llegar? "
                    "Escribime la hora (por ejemplo *18:30* o *6 de la tarde*).")
        return ("Para adelantar tu check-in, respondé *SÍ* para confirmar tu reserva, "
                "o *CANCELAR* si preferís hacerlo en recepción.")

    if step == STEP_ARRIVAL:
        hora = _parse_arrival(text)
        if not hora:
            return ("No entendí bien la hora 🙈. Escribime solo la hora de llegada, "
                    "por ejemplo *18:30* o *18 hs*.")
        _save(db, b, estimated_arrival=hora, step=STEP_DOCUMENT)
        return (f"¡Perfecto, te esperamos a las *{hora}*! 🕒\n\n"
                f"Último paso: mandame una *foto de tu documento* (DNI o pasaporte) "
                f"para dejar todo listo. Sacale una foto clara y enviámela acá 📸\n\n"
                f"(Si preferís, podés mostrarlo al llegar: escribí *OMITIR*.)")

    if step == STEP_DOCUMENT:
        if low in ("omitir", "omito", "despues", "después", "luego", "al llegar"):
            return _finish(db, b, session_id, with_document=False)
        # Esperábamos una imagen; el huésped mandó texto.
        return ("Estoy esperando la *foto de tu documento* 📸. Sacale una foto clara al DNI "
                "o pasaporte y enviámela. O escribí *OMITIR* para mostrarlo al llegar.")

    # step done o desconocido
    return ("Tu check-in ya está adelantado ✅. ¡Te esperamos en Bariloche! "
            "Si necesitás algo más, escribime.")


def save_document(db: Session, session_id: str, document_url: str) -> Optional[str]:
    """Registra el documento recibido (lo guarda el webhook) y cierra el flujo.

    `document_url` es la ruta pública ya guardada (ej. "/media/checkin/HTL-XXXX.jpg").
    Devuelve el mensaje de cierre, o None si no había flujo activo para esta sesión.
    """
    b = _get_booking_by_session(db, session_id)
    if not b or (b.pre_checkin or {}).get("step") != STEP_DOCUMENT:
        return None
    _save(db, b, document_url=document_url)
    return _finish(db, b, session_id, with_document=True)


def _finish(db: Session, booking: Booking, session_id: str, with_document: bool) -> str:
    """Marca el check-in como completado y devuelve el mensaje final."""
    _save(db, booking, status="completed", step=STEP_DONE, completed_at=_now())
    conversation_state_manager.clear_state(session_id)

    hora = (booking.pre_checkin or {}).get("estimated_arrival")
    nombre = (booking.guest_name or "").split(" ")[0] or ""
    doc_line = ("Ya tenemos tu documento, así que la llegada va a ser rapidísima. "
                if with_document else
                "Acordate de traer tu documento para mostrarlo al llegar. ")
    hora_line = f"Te esperamos a las *{hora}*. " if hora else ""
    return (
        f"¡Listo{', ' + nombre if nombre else ''}! ✅ Tu *check-in está adelantado*.\n\n"
        f"{hora_line}{doc_line}Al llegar, solo pasá por recepción a retirar tu llave 🔑\n\n"
        f"📍 Estamos en *Libertad 290*, San Carlos de Bariloche, a 150 m del Centro Cívico.\n"
        f"Cualquier cosa que necesites antes o durante tu estadía, escribime por acá. "
        f"¡Buen viaje! 🏔️"
    )
