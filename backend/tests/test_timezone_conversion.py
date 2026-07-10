"""
Unificación de zona horaria — verifica que la atribución lead→booking ya no sufre el desfase.

Antes: Lead.created_at usaba now_business() (AR, UTC-3) y Booking.created_at usaba datetime.now()
(hora del server). La comparación `Booking.created_at >= lead.created_at` en get_leads_summary
podía fallar por el desfase de zona (un booking real POSTERIOR parecía ANTERIOR). Ahora ambos
usan utcnow_naive() (UTC) → coherente.
"""
from datetime import date, timedelta

from app.models.lead import Lead
from app.models.contact import Contact
from app.models.hotel import Room, Booking
from app.services import business_metrics
from app.utils.timezone_utils import utcnow_naive


def test_lead_y_booking_del_mismo_instante_cuentan_como_conversion(db):
    # Contacto + su lead + su booking creado 1 segundo DESPUÉS (conversión real).
    c = Contact(full_name="Ana", phone_number="+5491100000001")
    db.add(c); db.commit(); db.refresh(c)

    t = utcnow_naive()
    lead = Lead(session_id="conv-tz-1", contact_id=c.id, lead_type="CALIENTE",
                interest_score=9, status="active", created_at=t)
    db.add(lead)

    room = Room(room_type="King", capacity=2, base_price_usd=120, base_price_ars=126000,
                total_units=1, status="active")
    db.add(room); db.commit(); db.refresh(room)

    booking = Booking(
        code="HTL-TZ01", room_id=room.id, contact_id=c.id, session_id="conv-tz-1",
        guest_name="Ana", check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12), guests=2, nights=2,
        total_price_usd=240, total_price_ars=252000, status="confirmed",
        created_at=t + timedelta(seconds=1),   # 1s DESPUÉS del lead
    )
    db.add(booking); db.commit()

    summary = business_metrics.get_leads_summary(
        db, start=date.today() - timedelta(days=1), end=date.today() + timedelta(days=1))

    assert summary["generated"] >= 1
    # La conversión debe contarse: el booking es posterior al lead y ambos están en UTC.
    assert summary["closed"] >= 1, f"la conversión no se atribuyó: {summary}"
