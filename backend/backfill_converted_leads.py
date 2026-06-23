"""
Backfill ONE-OFF: marca como CONVERTIDO a los leads que YA reservaron pero quedaron
con un scoring frío/tibio (bug histórico: la reserva no actualizaba el lead).

Recorre las reservas y, para cada una, busca el lead asociado por session_id y luego por
contact_id; si existe y aún NO está convertido, lo marca CALIENTE/won con
lead_service.mark_lead_converted (idempotente).

NO se ejecuta en el deploy (no está en start.sh): es una corrección puntual. Correr a mano:
    python backfill_converted_leads.py
"""
import app.main  # noqa: F401 — registra todos los modelos antes de tocar la DB
from app.models.database import SessionLocal
from app.models.hotel import Booking
from app.models.lead import Lead
from app.services.lead_service import lead_service


def backfill():
    db = SessionLocal()
    try:
        bookings = db.query(Booking).filter(Booking.status != "cancelled").all()
        converted, skipped = 0, 0
        for b in bookings:
            # ¿Hay un lead asociado y todavía sin convertir?
            lead = None
            if b.session_id:
                lead = db.query(Lead).filter(Lead.session_id == b.session_id).first()
            if not lead and b.contact_id:
                lead = (
                    db.query(Lead)
                    .filter(Lead.contact_id == b.contact_id)
                    .order_by(Lead.updated_at.desc())
                    .first()
                )
            if not lead:
                continue
            if lead.status == "converted":
                skipped += 1
                continue
            ok = lead_service.mark_lead_converted(
                db, session_id=b.session_id, contact_id=b.contact_id, booking_code=b.code,
            )
            if ok:
                converted += 1
                print(f"  Lead #{lead.id} ({lead.get_display_name()}) -> CONVERTIDO por reserva {b.code}")

        print(f"\n[backfill] {converted} leads marcados como convertidos; {skipped} ya lo estaban.")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
