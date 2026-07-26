"""
Anti doble-booking: la invariante que protege plata real.

`create_booking` valida disponibilidad y ASIGNA una unidad física en la misma transacción,
con un lock pesimista (FOR UPDATE) para serializar requests concurrentes. Ese camino no
tenía tests (hallazgo I7 de la auditoría): un refactor podía romperlo en silencio y el
síntoma sería cobrarle la misma habitación a dos huéspedes.

Qué se verifica acá (todo determinístico, sin OpenAI):
  - Nunca se asigna la misma unidad física dos veces en fechas solapadas.
  - Al agotarse el inventario, la reserva siguiente se RECHAZA (no se sobrevende).
  - Los rangos que NO se solapan sí pueden reusar la unidad.
  - El lock pesimista se invoca en el camino de creación.

Nota sobre concurrencia real: el `FOR UPDATE` solo aplica en PostgreSQL
(`_lock_overlapping_bookings`); en SQLite es no-op porque el motor ya serializa las
escrituras. Por eso acá no se simulan hilos (daría falsa confianza sobre un lock que en
SQLite no corre): se verifica la invariante de negocio y que el lock se pida.
"""
from datetime import date, timedelta

import pytest

from app.services import reservation_service


CI = date.today() + timedelta(days=30)
CO = CI + timedelta(days=3)


def _room_con_unidades(db, n_units: int, room_type: str = "TestDouble"):
    """Crea un tipo de habitación con N unidades físicas disponibles."""
    from app.models.hotel import Room, RoomUnit

    room = Room(room_type=room_type, base_price_usd=100, base_price_ars=100000,
                capacity=2, total_units=n_units)
    db.add(room)
    db.commit()
    for i in range(n_units):
        db.add(RoomUnit(room_id=room.id, number=f"{room_type[:3]}{i+1}", status="available"))
    db.commit()
    return room


def _reservar(db, room, *, check_in=CI, check_out=CO, nombre="Huésped"):
    return reservation_service.create_booking(
        db, room_id=room.id, check_in=check_in, check_out=check_out,
        guest_name=nombre, guests=1,
    )


class TestNoSobreventa:
    def test_dos_reservas_mismas_fechas_toman_unidades_DISTINTAS(self, db):
        """Con 2 unidades, dos reservas solapadas deben ir a unidades físicas distintas."""
        room = _room_con_unidades(db, 2, "DosUnid")

        r1 = _reservar(db, room, nombre="Ana")
        r2 = _reservar(db, room, nombre="Beto")

        assert "error" not in r1, r1
        assert "error" not in r2, r2

        from app.models.hotel import Booking
        u1 = db.query(Booking).filter(Booking.code == r1["code"]).first().room_unit_id
        u2 = db.query(Booking).filter(Booking.code == r2["code"]).first().room_unit_id
        assert u1 is not None and u2 is not None, "cada reserva debe tener unidad asignada"
        assert u1 != u2, "DOBLE-BOOKING: dos reservas solapadas comparten la misma unidad"

    def test_agotado_el_inventario_la_siguiente_se_rechaza(self, db):
        """Con 1 sola unidad, la segunda reserva solapada NO puede crearse."""
        room = _room_con_unidades(db, 1, "UnaUnid")

        r1 = _reservar(db, room, nombre="Ana")
        r2 = _reservar(db, room, nombre="Beto")

        assert "error" not in r1, r1
        assert "error" in r2, f"SOBREVENTA: se creó una 2ª reserva sin unidades libres ({r2})"
        assert "disponibilidad" in r2["error"].lower()

    def test_fechas_que_no_solapan_reusan_la_unidad(self, db):
        """La invariante es por SOLAPE: liberada la fecha, la unidad se puede volver a vender."""
        room = _room_con_unidades(db, 1, "SinSolape")

        r1 = _reservar(db, room, check_in=CI, check_out=CO, nombre="Ana")
        # Empieza justo cuando termina la anterior: [a_in, a_out) y [b_in, b_out) NO se solapan.
        r2 = _reservar(db, room, check_in=CO, check_out=CO + timedelta(days=2), nombre="Beto")

        assert "error" not in r1, r1
        assert "error" not in r2, f"no hay solape, debería poder reservarse ({r2})"

    def test_una_reserva_cancelada_libera_la_unidad(self, db):
        """Una reserva cancelada no bloquea el inventario."""
        from app.models.hotel import Booking

        room = _room_con_unidades(db, 1, "Cancelada")
        r1 = _reservar(db, room, nombre="Ana")
        assert "error" not in r1

        b = db.query(Booking).filter(Booking.code == r1["code"]).first()
        b.status = "cancelled"
        db.commit()

        r2 = _reservar(db, room, nombre="Beto")
        assert "error" not in r2, f"la unidad quedó bloqueada por una reserva cancelada ({r2})"


class TestLockPesimista:
    def test_create_booking_pide_el_lock_de_solapadas(self, db, monkeypatch):
        """El lock anti-concurrencia debe invocarse ANTES de validar/asignar la unidad.

        En SQLite el lock es no-op, así que verificamos que el camino de creación lo pida:
        si un refactor lo saltea, en PostgreSQL volvería el riesgo de doble-booking.
        """
        room = _room_con_unidades(db, 1, "ConLock")
        llamadas = []

        original = reservation_service._lock_overlapping_bookings

        def _spy(db_, room_id, check_in, check_out):
            llamadas.append((room_id, check_in, check_out))
            return original(db_, room_id, check_in, check_out)

        monkeypatch.setattr(reservation_service, "_lock_overlapping_bookings", _spy)
        r = _reservar(db, room, nombre="Ana")

        assert "error" not in r, r
        assert llamadas, "create_booking no tomó el lock de reservas solapadas"
        assert llamadas[0] == (room.id, CI, CO)

    def test_el_lock_usa_for_update_solo_en_postgres(self, db):
        """En SQLite no debe intentar FOR UPDATE (lo tolera sin romper la reserva)."""
        room = _room_con_unidades(db, 1, "PgLock")
        # No debe lanzar en SQLite (dialecto != postgresql → no-op).
        reservation_service._lock_overlapping_bookings(db, room.id, CI, CO)
