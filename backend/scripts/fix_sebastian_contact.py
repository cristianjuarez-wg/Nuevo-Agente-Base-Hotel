"""
One-off: desvincula la reserva de Sebastian Usberti del contacto de Roberto Parkinso.

Causa: la reserva HTL-FKPX se cargó con el teléfono `3417207787`, que normaliza al
mismo E.164 (`+543417207787`) que el contacto 31 (Roberto). El dedup por teléfono
—correcto por diseño— pegó la reserva de Sebastian al contacto de Roberto, así que
clickear "Sebastian Usberti" en Reservas abría el perfil de Roberto.

Este script NO toca el código de matching. Solo corrige los datos:
  1. Le da a HTL-FKPX un teléfono distinto que no colisiona.
  2. Crea/obtiene el contacto propio de Sebastian (reusa get_or_create_contact).
  3. Re-vincula la reserva a ese contacto.
  4. Recalcula métricas de ambos contactos.

Ejecutar una sola vez desde backend/:  python scripts/fix_sebastian_contact.py
"""
import sys
from pathlib import Path

# Permitir `import app.*` cuando se corre como script desde backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.database import SessionLocal
# Importar TODOS los módulos de modelos para que SQLAlchemy resuelva los mappers
# (relaciones cross-módulo referidas por nombre: ExtraCharge, StaffMember, etc.).
import importlib
import pkgutil
import app.models as _models_pkg
for _m in pkgutil.iter_modules(_models_pkg.__path__):
    if _m.name not in ("database", "schemas"):
        importlib.import_module(f"app.models.{_m.name}")

from app.models.hotel import Booking
from app.models.contact import Contact
from app.services.contact_service import contact_service

BOOKING_CODE = "HTL-FKPX"
GUEST_NAME = "Sebastian Usberti"
NEW_PHONE = "+543417207788"  # distinto del de Roberto (+543417207787)


def main():
    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.code == BOOKING_CODE).first()
        if not booking:
            print(f"❌ No se encontró la reserva {BOOKING_CODE}. Nada que hacer.")
            return

        old_contact_id = booking.contact_id
        print(f"Reserva {BOOKING_CODE}: contact_id actual = {old_contact_id}, "
              f"guest_phone = {booking.guest_phone!r}")

        # 1) Teléfono distinto en la reserva.
        booking.guest_phone = NEW_PHONE

        # 2) Contacto propio de Sebastian (reusa la lógica de la app).
        contact = contact_service.get_or_create_contact(
            phone=NEW_PHONE, name=GUEST_NAME, db=db
        )
        if not contact:
            print("❌ No se pudo crear/obtener el contacto de Sebastian.")
            db.rollback()
            return
        print(f"Contacto de Sebastian = id {contact.id} ({contact.full_name})")

        # 3) Re-vincular la reserva.
        booking.contact_id = contact.id
        db.commit()

        # 4) Recalcular métricas de ambos contactos.
        contact_service.update_contact_metrics(contact.id, db)
        if old_contact_id and old_contact_id != contact.id:
            contact_service.update_contact_metrics(old_contact_id, db)
        db.commit()

        # Reporte final.
        for cid in {old_contact_id, contact.id}:
            if not cid:
                continue
            c = db.query(Contact).filter(Contact.id == cid).first()
            if c:
                print(f"  contacto {c.id}: {c.full_name!r} · purchases_made={c.purchases_made} "
                      f"· type={c.contact_type}")
        print(f"OK: {BOOKING_CODE} ahora apunta a contact_id={booking.contact_id}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
