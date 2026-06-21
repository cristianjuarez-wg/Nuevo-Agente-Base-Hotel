"""
Métricas de negocio para el AGENTE DE GERENCIA (BI conversacional).

Funciones por rango de fechas que devuelven dicts simples, reutilizando las queries y
helpers que ya existen en el proyecto (reservation_service, modelos hotel/lead/contact).
Son la "fuente de datos" del consultor: el orquestador del dueño las llama vía owner_tools.

Todas usan hora de Argentina (now_argentina) y aceptan un período en lenguaje natural
("hoy", "semana", "mes", "anio") que se resuelve a un rango (start, end).
"""
from datetime import date, timedelta
from typing import Dict, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.hotel import Room, Booking, HotelTicket
from app.models.lead import Lead
from app.utils.timezone_utils import now_argentina
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Reservas que NO cuentan para negocio (canceladas).
_NON_BLOCKING = ("cancelled",)


def resolve_period(period: str) -> Tuple[date, date, str]:
    """Convierte un período en lenguaje natural a (start, end, etiqueta). end es exclusivo
    (mañana) para incluir el día de hoy completo. Default: último mes (30 días)."""
    today = now_argentina().date()
    end = today + timedelta(days=1)  # exclusivo
    p = (period or "").lower().strip()
    if p in ("hoy", "today", "dia", "día"):
        return today, end, "hoy"
    if p in ("semana", "week", "ultima semana", "última semana", "7"):
        return today - timedelta(days=6), end, "los últimos 7 días"
    if p in ("anio", "año", "ano", "year", "ultimo año", "último año", "365"):
        return today - timedelta(days=364), end, "el último año"
    # default
    return today - timedelta(days=29), end, "los últimos 30 días"


def _total_units(db: Session) -> int:
    """Total de habitaciones del hotel (suma de total_units de los tipos activos)."""
    total = db.query(func.coalesce(func.sum(Room.total_units), 0)).filter(
        (Room.status == "active") | (Room.status.is_(None))
    ).scalar()
    return int(total or 0)


def get_occupancy(db: Session, start: date, end: date) -> Dict:
    """% de ocupación en [start, end): noches-habitación vendidas / (unidades × días).

    Para cada booking no cancelado que solapa el rango, suma las noches que caen DENTRO
    del rango. Devuelve el % global, por tipo de habitación, y una serie diaria (para gráfico).
    """
    days = max((end - start).days, 1)
    total_units = _total_units(db)
    capacity_nights = total_units * days

    bookings = (
        db.query(Booking)
        .filter(
            Booking.check_in < end,
            Booking.check_out > start,
            ~Booking.status.in_(_NON_BLOCKING),
        )
        .all()
    )

    sold_nights = 0
    by_type: Dict[str, int] = {}
    # Serie diaria: habitaciones ocupadas por día.
    daily_counts = {start + timedelta(days=i): 0 for i in range(days)}

    for b in bookings:
        # Intersección del booking con el rango.
        ci = max(b.check_in, start)
        co = min(b.check_out, end)
        nights = (co - ci).days
        if nights <= 0:
            continue
        sold_nights += nights
        rt = b.room.room_type if b.room else "—"
        by_type[rt] = by_type.get(rt, 0) + nights
        # Sumar a cada día ocupado.
        d = ci
        while d < co:
            if d in daily_counts:
                daily_counts[d] += 1
            d += timedelta(days=1)

    occupancy_pct = round((sold_nights / capacity_nights) * 100, 1) if capacity_nights else 0.0
    by_room_type = {
        rt: round((n / (total_units * days) * 100), 1) if capacity_nights else 0.0
        for rt, n in by_type.items()
    }
    daily = [
        {"date": d.isoformat(),
         "pct": round((c / total_units * 100), 1) if total_units else 0.0}
        for d, c in sorted(daily_counts.items())
    ]
    return {
        "occupancy_pct": occupancy_pct,
        "sold_nights": sold_nights,
        "capacity_nights": capacity_nights,
        "total_units": total_units,
        "by_room_type": by_room_type,
        "daily": daily,
    }


def get_revenue(db: Session, start: date, end: date) -> Dict:
    """Facturación de reservas creadas en el rango (no canceladas), en USD y ARS."""
    rows = (
        db.query(Booking.total_price_usd, Booking.total_price_ars)
        .filter(
            Booking.created_at >= start,
            Booking.created_at < end,
            ~Booking.status.in_(_NON_BLOCKING),
        )
        .all()
    )
    usd = round(sum((r[0] or 0) for r in rows), 2)
    ars = round(sum((r[1] or 0) for r in rows), 2)
    return {"usd": usd, "ars": ars, "count": len(rows)}


def get_leads_summary(db: Session, start: date, end: date) -> Dict:
    """Leads generados en el rango y cuántos se cerraron (su Contact ya tiene compra)."""
    from app.models.contact import Contact

    leads = (
        db.query(Lead)
        .filter(Lead.created_at >= start, Lead.created_at < end)
        .all()
    )
    generated = len(leads)
    closed = 0
    for lead in leads:
        if lead.contact_id:
            c = db.query(Contact).filter(Contact.id == lead.contact_id).first()
            if c and (c.purchases_made or 0) > 0:
                closed += 1
    conversion_pct = round((closed / generated * 100), 1) if generated else 0.0
    return {"generated": generated, "closed": closed, "conversion_pct": conversion_pct}


def get_complaints(db: Session, start: date, end: date) -> Dict:
    """Quejas (HotelTicket category='complaint') creadas en el rango, por estado."""
    base = db.query(func.count(HotelTicket.id)).filter(
        HotelTicket.category == "complaint",
        HotelTicket.created_at >= start,
        HotelTicket.created_at < end,
    )
    total = base.scalar() or 0
    open_ = (
        db.query(func.count(HotelTicket.id))
        .filter(
            HotelTicket.category == "complaint",
            HotelTicket.created_at >= start,
            HotelTicket.created_at < end,
            HotelTicket.status.in_(["open", "in_progress", "escalated"]),
        )
        .scalar()
        or 0
    )
    return {"total": total, "open": open_, "resolved": total - open_}


def get_business_summary(db: Session, start: date, end: date) -> Dict:
    """Panorama combinado del negocio en el rango — para preguntas amplias del dueño."""
    return {
        "occupancy": get_occupancy(db, start, end),
        "revenue": get_revenue(db, start, end),
        "leads": get_leads_summary(db, start, end),
        "complaints": get_complaints(db, start, end),
    }
