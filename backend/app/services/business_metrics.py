"""
Métricas de negocio para el AGENTE DE GERENCIA (BI conversacional).

Funciones por rango de fechas que devuelven dicts simples, reutilizando las queries y
helpers que ya existen en el proyecto (reservation_service, modelos hotel/lead/contact).
Son la "fuente de datos" del consultor: el orquestador del dueño las llama vía owner_tools.

Todas usan hora de Argentina (now_business) y aceptan un período en lenguaje natural
("hoy", "semana", "mes", "anio") que se resuelve a un rango (start, end).
"""
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.hotel import Room, Booking, HotelTicket, TICKET_OPEN_STATES
from app.models.lead import Lead
from app.utils.timezone_utils import now_business
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Reservas que NO cuentan para negocio (canceladas).
_NON_BLOCKING = ("cancelled",)

# Meses en español → número.
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
# Número de mes → nombre, para etiquetas claras ("este mes (junio 2026)").
_MES_NOMBRE = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
               7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
# Estaciones del hemisferio SUR (Argentina): rango de meses (inclusive).
# Invierno cae dentro del mismo año calendario (jun–ago), clave para un hotel de Bariloche.
_ESTACIONES = {
    "verano": (12, 2), "otoño": (3, 5), "otono": (3, 5),
    "invierno": (6, 8), "primavera": (9, 11),
}


def _extract_year(text: str, default_year: int) -> int:
    """Busca un año de 4 dígitos en el texto (ej. '2025'); si no hay, usa el default."""
    m = re.search(r"(20\d{2})", text)
    return int(m.group(1)) if m else default_year


def _first_of_next_month(year: int, month: int) -> date:
    """Primer día del mes siguiente a (year, month). Sirve como fin EXCLUSIVO de un mes."""
    return date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)


def resolve_period(period: str) -> Tuple[date, date, str]:
    """Convierte un período en lenguaje natural a (start, end, etiqueta).

    `end` es EXCLUSIVO. Soporta, además de hoy/semana/mes/año:
      - "trimestre" (últimos 90 días) y "semestre" (últimos 180 días)
      - meses por nombre: "junio", "junio 2025"
      - estaciones AR: "invierno", "verano 2025" (hemisferio sur)
      - año explícito: "2025" → todo ese año
    Mantiene compatibilidad con los períodos originales. Default: últimos 30 días.
    """
    today = now_business().date()
    end = today + timedelta(days=1)  # exclusivo
    p = (period or "").lower().strip()

    # --- Períodos relativos simples ---
    if p in ("hoy", "today", "dia", "día"):
        return today, end, "hoy"
    # Ventanas MÓVILES explícitas (compatibilidad / si el dueño las pide así).
    if p in ("ultimos 7 dias", "últimos 7 días", "7"):
        return today - timedelta(days=6), end, "los últimos 7 días"
    if p in ("ultimos 30 dias", "últimos 30 días", "30"):
        return today - timedelta(days=29), end, "los últimos 30 días"
    # Períodos CALENDARIO corrientes (lo que un dueño entiende por "esta semana/este mes/este año").
    if p in ("semana", "week", "esta semana", "ultima semana", "última semana"):
        monday = today - timedelta(days=today.weekday())  # lunes de esta semana
        return monday, end, "esta semana"
    if p in ("mes", "month", "este mes", "ultimo mes", "último mes"):
        start = today.replace(day=1)
        return start, _first_of_next_month(today.year, today.month), f"este mes ({_MES_NOMBRE.get(today.month, '')} {today.year})"
    if p in ("anio", "año", "ano", "year", "este año", "este ano", "ultimo año", "último año", "365"):
        return date(today.year, 1, 1), date(today.year + 1, 1, 1), f"este año ({today.year})"
    if p in ("trimestre", "ultimo trimestre", "último trimestre", "quarter"):
        return today - timedelta(days=89), end, "el último trimestre"
    if p in ("semestre", "ultimo semestre", "último semestre"):
        return today - timedelta(days=179), end, "el último semestre"

    # --- Estación (hemisferio sur) con año opcional ---
    for est, (m_ini, m_fin) in _ESTACIONES.items():
        if est in p:
            year = _extract_year(p, today.year)
            if est == "verano":  # dic (year-1) → feb (year)
                start = date(year - 1, 12, 1)
                end_excl = date(year, 3, 1)
            else:
                start = date(year, m_ini, 1)
                end_excl = _first_of_next_month(year, m_fin)  # fin exclusivo
            return start, end_excl, f"{est} {year}"

    # --- Mes por nombre con año opcional ---
    for nombre, num in _MESES.items():
        if nombre in p:
            year = _extract_year(p, today.year)
            start = date(year, num, 1)
            end_excl = _first_of_next_month(year, num)
            return start, end_excl, f"{nombre} {year}"

    # --- Año explícito solo (ej. "2025") ---
    m = re.fullmatch(r"\s*(20\d{2})\s*", p)
    if m:
        year = int(m.group(1))
        return date(year, 1, 1), date(year + 1, 1, 1), str(year)

    # default: si no se reconoce el período, asumimos el mes calendario corriente
    # (lo más intuitivo para el dueño; "los últimos 30 días" se pide explícito).
    start = today.replace(day=1)
    return start, _first_of_next_month(today.year, today.month), f"este mes ({_MES_NOMBRE.get(today.month, '')} {today.year})"


def parse_two_periods(text: str) -> Optional[Tuple[str, str]]:
    """Detecta dos períodos en una frase de comparación ('X vs Y', 'X versus Y').

    Devuelve (period_a_str, period_b_str) crudos para que el caller los resuelva, o None.
    Útil para que el agente arme comparativas; igualmente puede llamar resolve_period dos veces.
    """
    if not text:
        return None
    parts = re.split(r"\bvs\.?\b|\bversus\b|\bcontra\b|\bcomparad[oa]\s+con\b", text, flags=re.I)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None


def _total_units(db: Session) -> int:
    """Total de habitaciones del hotel (suma de total_units de los tipos activos)."""
    total = db.query(func.coalesce(func.sum(Room.total_units), 0)).filter(
        (Room.status == "active") | (Room.status.is_(None))
    ).scalar()
    return int(total or 0)


def get_occupancy(db: Session, start: date, end: date, room_type: Optional[str] = None) -> Dict:
    """% de ocupación en [start, end): noches-habitación vendidas / (unidades × días).

    Para cada booking no cancelado que solapa el rango, suma las noches que caen DENTRO
    del rango. Devuelve el % global, por tipo, serie diaria (gráfico), y `guests_nights`
    (personas-noche, para responder "cuántos pasajeros"). `room_type` filtra por tipo.
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
    if room_type:
        rt_norm = room_type.strip().lower()
        bookings = [b for b in bookings if b.room and rt_norm in (b.room.room_type or "").lower()]

    sold_nights = 0
    guests_nights = 0
    by_type: Dict[str, int] = {}
    daily_counts = {start + timedelta(days=i): 0 for i in range(days)}

    for b in bookings:
        ci = max(b.check_in, start)
        co = min(b.check_out, end)
        nights = (co - ci).days
        if nights <= 0:
            continue
        sold_nights += nights
        guests_nights += nights * ((b.guests or 0) + (b.children or 0))
        rt = b.room.room_type if b.room else "—"
        by_type[rt] = by_type.get(rt, 0) + nights
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
        "guests_nights": guests_nights,
        "capacity_nights": capacity_nights,
        "total_units": total_units,
        "by_room_type": by_room_type,
        "daily": daily,
    }


def get_guests_in_house(db: Session, on: Optional[date] = None) -> Dict:
    """Pasajeros ALOJADOS en una fecha (default hoy): personas y habitaciones ocupadas.

    Cuenta los bookings no cancelados con check_in <= día < check_out. Esta es la
    respuesta a "¿cuántos pasajeros tenemos alojados?" (personas, no % de habitaciones).
    """
    day = on or now_business().date()
    bookings = (
        db.query(Booking)
        .filter(
            Booking.check_in <= day,
            Booking.check_out > day,
            ~Booking.status.in_(_NON_BLOCKING),
        )
        .all()
    )
    guests = sum(((b.guests or 0) + (b.children or 0)) for b in bookings)
    rooms = len(bookings)
    by_type: Dict[str, int] = {}
    for b in bookings:
        rt = b.room.room_type if b.room else "—"
        by_type[rt] = by_type.get(rt, 0) + 1
    return {"date": day.isoformat(), "guests": guests, "rooms_occupied": rooms,
            "by_room_type": by_type}


def get_room_ranking(db: Session, start: date, end: date, by: str = "bookings") -> List[Dict]:
    """Ranking de tipos de habitación en el rango, por `bookings` | `nights` | `revenue`.

    Cubre "¿cuál es la habitación más solicitada del trimestre?". Cuenta bookings que
    solapan el rango (no cancelados). Devuelve lista ordenada desc.
    """
    bookings = (
        db.query(Booking)
        .filter(
            Booking.check_in < end,
            Booking.check_out > start,
            ~Booking.status.in_(_NON_BLOCKING),
        )
        .all()
    )
    agg: Dict[str, Dict] = {}
    for b in bookings:
        rt = b.room.room_type if b.room else "—"
        slot = agg.setdefault(rt, {"bookings": 0, "nights": 0, "revenue": 0.0})
        slot["bookings"] += 1
        ci, co = max(b.check_in, start), min(b.check_out, end)
        slot["nights"] += max((co - ci).days, 0)
        slot["revenue"] += (b.total_price_usd or 0)
    key = by if by in ("bookings", "nights", "revenue") else "bookings"
    ranking = [
        {"room_type": rt, "bookings": v["bookings"], "nights": v["nights"],
         "revenue_usd": round(v["revenue"], 2)}
        for rt, v in agg.items()
    ]
    ranking.sort(key=lambda r: r["revenue_usd"] if key == "revenue" else r[key], reverse=True)
    return ranking


def _prorate_window(b, total, w_start: date, w_end: date) -> float:
    """Fracción del `total` de la reserva `b` que cae dentro de [w_start, w_end) (exclusivo).
    Genérico (rango arbitrario), para el split realizado/proyectado de get_revenue."""
    full_nights = (b.check_out - b.check_in).days
    if not full_nights or not total:
        return 0.0
    ci, co = max(b.check_in, w_start), min(b.check_out, w_end)
    in_range = max((co - ci).days, 0)
    return (total or 0) * in_range / full_nights


def get_revenue(
    db: Session,
    start: date,
    end: date,
    room_type: Optional[str] = None,
    group_by: Optional[str] = None,
) -> Dict:
    """Facturación de las ESTADÍAS que ocurren en el rango (no canceladas), en USD y ARS.

    Filtra por solapamiento de estadía (igual que ocupación y ranking) y PRORRATEA el
    ingreso por las noches que caen dentro del rango. Así "facturación de invierno" = lo
    que se factura por las estadías de invierno (mismo idioma que ocupación), no por la
    fecha en que se hizo la reserva.

    - `room_type`: si se indica, filtra por ese tipo de habitación (match flexible).
    - `group_by`: "room_type" → desglose por tipo; "month" → serie mensual (para evolución).
    - Devuelve además `adr` (USD por noche vendida) y `avg_per_booking` (USD por reserva).
    Estos crudos son la base del cálculo on-demand del agente (promedios/comparativas).
    """
    q = (
        db.query(Booking)
        .filter(
            Booking.check_in < end,
            Booking.check_out > start,
            ~Booking.status.in_(_NON_BLOCKING),
        )
    )
    bookings = q.all()
    if room_type:
        rt_norm = room_type.strip().lower()
        bookings = [
            b for b in bookings
            if b.room and rt_norm in (b.room.room_type or "").lower()
        ]

    # Prorrateo: fracción del ingreso de cada reserva = noches dentro del rango / noches totales.
    def _prorate(b, total):
        full_nights = (b.check_out - b.check_in).days
        if not full_nights or not total:
            return 0.0
        ci, co = max(b.check_in, start), min(b.check_out, end)
        in_range = max((co - ci).days, 0)
        return (total or 0) * in_range / full_nights

    usd = round(sum(_prorate(b, b.total_price_usd) for b in bookings), 2)
    ars = round(sum(_prorate(b, b.total_price_ars) for b in bookings), 2)
    count = len(bookings)
    nights = sum(max((min(b.check_out, end) - max(b.check_in, start)).days, 0) for b in bookings)
    adr = round(usd / nights, 2) if nights else 0.0
    avg_per_booking = round(usd / count, 2) if count else 0.0

    # Split REALIZADO vs PROYECTADO (on-the-books): partimos el rango por HOY. Realizado = lo
    # que ya ocurrió (estadías hasta hoy); proyectado = reservas confirmadas a futuro dentro del
    # rango. Reusa _prorate acotando el rango efectivo a cada lado de hoy.
    today = now_business().date()
    cut = today + timedelta(days=1)  # exclusivo: "hasta hoy" incluye hoy

    def _sum_window(w_start: date, w_end: date) -> Dict:
        if w_end <= w_start:
            return {"usd": 0.0, "ars": 0.0, "count": 0}
        bs = [b for b in bookings if b.check_in < w_end and b.check_out > w_start]
        u = round(sum(_prorate_window(b, b.total_price_usd, w_start, w_end) for b in bs), 2)
        a = round(sum(_prorate_window(b, b.total_price_ars, w_start, w_end) for b in bs), 2)
        return {"usd": u, "ars": a, "count": len(bs)}

    realized = _sum_window(start, min(end, cut))
    projected = _sum_window(max(start, cut), end)

    result: Dict = {
        "usd": usd, "ars": ars, "count": count,
        "nights": nights, "adr": adr, "avg_per_booking": avg_per_booking,
        "realized": realized, "projected": projected,
    }

    if group_by == "room_type":
        by: Dict[str, Dict] = {}
        for b in bookings:
            rt = (b.room.room_type if b.room else "—")
            slot = by.setdefault(rt, {"usd": 0.0, "count": 0})
            slot["usd"] += _prorate(b, b.total_price_usd)
            slot["count"] += 1
        result["by_room_type"] = {rt: {"usd": round(v["usd"], 2), "count": v["count"]}
                                  for rt, v in by.items()}
    elif group_by == "month":
        # Serie por mes de ESTADÍA (check_in), coherente con el filtro por estadía.
        series: Dict[str, float] = {}
        for b in bookings:
            key = b.check_in.strftime("%Y-%m") if b.check_in else "—"
            series[key] = series.get(key, 0.0) + _prorate(b, b.total_price_usd)
        result["by_month"] = [{"month": k, "usd": round(v, 2)}
                              for k, v in sorted(series.items())]

    return result


def get_leads_summary(db: Session, start: date, end: date) -> Dict:
    """Leads generados en el rango y cuántos se cerraron.

    Un lead se considera CERRADO si su contacto tiene una reserva (no cancelada) creada
    EN O DESPUÉS de la fecha del lead. Antes se contaba si el contacto tenía
    `purchases_made > 0` "alguna vez" — eso inflaba la conversión con compras viejas o
    de un huésped recurrente que generó un lead nuevo (no atribuibles a este lead).
    """
    leads = (
        db.query(Lead)
        .filter(Lead.created_at >= start, Lead.created_at < end)
        .all()
    )
    generated = len(leads)
    closed = 0
    for lead in leads:
        if not lead.contact_id:
            continue
        has_booking_after = (
            db.query(Booking.id)
            .filter(
                Booking.contact_id == lead.contact_id,
                ~Booking.status.in_(_NON_BLOCKING),
                Booking.created_at >= lead.created_at,
            )
            .first()
            is not None
        )
        if has_booking_after:
            closed += 1
    conversion_pct = round((closed / generated * 100), 1) if generated else 0.0
    # Desglose por canal de origen (web | whatsapp | …) para la torta "¿de dónde vienen mis leads?".
    by_channel: Dict[str, int] = {}
    for lead in leads:
        ch = (getattr(lead, "channel", None) or "web").strip().lower()
        by_channel[ch] = by_channel.get(ch, 0) + 1
    return {"generated": generated, "closed": closed, "conversion_pct": conversion_pct,
            "by_channel": by_channel}


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
            HotelTicket.status.in_(TICKET_OPEN_STATES),
        )
        .scalar()
        or 0
    )
    return {"total": total, "open": open_, "resolved": total - open_}


def get_tickets_by_category(db: Session, start: date, end: date) -> Dict[str, int]:
    """Distribución de tickets creados en el rango por categoría (complaint, service_request,
    change, info, general…). Para la torta '¿en qué se concentran los pedidos/quejas?'."""
    rows = (
        db.query(HotelTicket.category, func.count(HotelTicket.id))
        .filter(HotelTicket.created_at >= start, HotelTicket.created_at < end)
        .group_by(HotelTicket.category)
        .all()
    )
    return {(cat or "otros"): n for cat, n in rows}


def get_business_summary(db: Session, start: date, end: date) -> Dict:
    """Panorama combinado del negocio en el rango — para preguntas amplias del dueño."""
    return {
        "occupancy": get_occupancy(db, start, end),
        "revenue": get_revenue(db, start, end),
        "leads": get_leads_summary(db, start, end),
        "complaints": get_complaints(db, start, end),
    }


def _variation_pct(a: float, b: float) -> Optional[float]:
    """Variación porcentual de b→a respecto de b. None si b es 0 (evita división por cero)."""
    if not b:
        return None
    return round((a - b) / b * 100, 1)


def compare_periods(
    db: Session,
    metric: str,
    period_a: str,
    period_b: str,
    room_type: Optional[str] = None,
) -> Dict:
    """Compara una métrica entre dos períodos (ej. 'invierno 2026' vs 'invierno 2025').

    metric: "revenue" | "occupancy". Resuelve cada período con resolve_period, corre la
    métrica filtrada por room_type y devuelve ambos valores + variación %. El agente lo usa
    para comparativas y SIEMPRE debe explicitar el método (lo indica el prompt).
    """
    sa, ea, la = resolve_period(period_a)
    sb, eb, lb = resolve_period(period_b)

    if metric == "occupancy":
        a = get_occupancy(db, sa, ea, room_type=room_type)
        b = get_occupancy(db, sb, eb, room_type=room_type)
        va, vb = a["occupancy_pct"], b["occupancy_pct"]
        unit = "%"
    else:  # revenue (default)
        a = get_revenue(db, sa, ea, room_type=room_type)
        b = get_revenue(db, sb, eb, room_type=room_type)
        va, vb = a["usd"], b["usd"]
        unit = "USD"

    return {
        "metric": metric,
        "room_type": room_type,
        "unit": unit,
        "a": {"label": la, "value": va, "detail": a},
        "b": {"label": lb, "value": vb, "detail": b},
        "variation_pct": _variation_pct(va, vb),
    }
