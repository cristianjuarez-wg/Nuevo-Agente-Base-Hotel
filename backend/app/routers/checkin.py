"""
Check-in Express — disparo del flujo desde el backoffice (y endpoint para cron futuro).

  POST /api/checkin/{code}/send     → arranca el check-in express de UNA reserva (manda WhatsApp)
  POST /api/checkin/cron/tomorrow   → dispara a TODAS las reservas que llegan mañana (para cron)
  GET  /api/checkin/{code}          → estado del pre-check-in (para el backoffice)

El disparo manda WhatsApp (gasta saldo) → protegido por X-Admin-Key, como el resto de las
acciones sensibles. El flujo conversacional posterior lo maneja checkin_express_service
(determinístico, fuera del LLM); ver routers/whatsapp.py.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.hotel import Booking
from app.services import checkin_express_service as checkin
from app.services.whatsapp_service import whatsapp_service
from app.routers.whatsapp import to_whatsapp_text
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/checkin", tags=["Check-in Express"])


def _start_one(db: Session, booking: Booking) -> dict:
    """Arranca el flujo de una reserva y manda el primer WhatsApp. Devuelve el resultado.

    Solo aplica a reservas PRÓXIMAS (upcoming): si el huésped ya está alojado, finalizó o
    canceló, no tiene sentido adelantar el check-in.
    """
    if booking.stay_status() != "upcoming":
        return {"code": booking.code, "sent": False,
                "reason": "El check-in express solo aplica a reservas próximas (el huésped aún no llegó)."}
    phone = (booking.guest_phone or "").strip()
    if not phone:
        return {"code": booking.code, "sent": False, "reason": "La reserva no tiene teléfono."}

    # Asegurar que la reserva tenga un session_id de WhatsApp (para hilar la conversación).
    if not booking.session_id:
        from app.utils.phone_normalizer import normalize_phone
        norm = normalize_phone(phone) or phone
        booking.session_id = "wa_" + norm.lstrip("+")
        db.commit()

    message = checkin.start(db, booking)
    delivered = whatsapp_service.send_text(phone, to_whatsapp_text(message))
    logger.info("Check-in express disparado", code=booking.code, delivered=delivered)
    return {"code": booking.code, "sent": True, "delivered_whatsapp": delivered}


@router.post("/{code}/send", dependencies=[Depends(require_admin_key)])
def send_checkin(code: str, db: Session = Depends(get_db)):
    """Arranca el check-in express de una reserva (manda el WhatsApp inicial)."""
    booking = db.query(Booking).filter(Booking.code == code).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    result = _start_one(db, booking)
    if not result.get("sent"):
        raise HTTPException(status_code=409, detail=result.get("reason", "No se pudo enviar."))
    return result


@router.post("/cron/tomorrow", dependencies=[Depends(require_admin_key)])
def send_checkin_tomorrow(db: Session = Depends(get_db)):
    """Dispara el check-in express a todas las reservas que llegan MAÑANA.

    Pensado para que un cron (Render Cron Job / ping externo) lo llame una vez al día.
    Por ahora también se puede invocar manual desde el backoffice.
    """
    tomorrow = date.today() + timedelta(days=1)
    bookings = (
        db.query(Booking)
        .filter(Booking.check_in == tomorrow, Booking.status == "confirmed")
        .all()
    )
    results = []
    for b in bookings:
        # No re-disparar a quien ya completó o está en proceso.
        if (b.pre_checkin or {}).get("status") in ("in_progress", "completed"):
            continue
        results.append(_start_one(db, b))
    sent = sum(1 for r in results if r.get("sent"))
    return {"date": tomorrow.isoformat(), "candidates": len(bookings), "sent": sent, "results": results}


@router.get("/{code}")
def get_checkin_status(code: str, db: Session = Depends(get_db)):
    """Estado del pre-check-in de una reserva (para mostrar en el backoffice)."""
    booking = db.query(Booking).filter(Booking.code == code).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return {"code": code, "pre_checkin": booking.pre_checkin or {}}
