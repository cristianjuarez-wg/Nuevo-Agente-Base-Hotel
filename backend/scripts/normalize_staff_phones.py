"""
One-off: re-normaliza los teléfonos de los StaffMember a E.164 con el "9" móvil argentino.

Motivo: WhatsApp Argentina necesita el "9" (+549...). Si una fila de staff quedó guardada
sin el 9 (ej. +543417207797), la notificación de Twilio no se entrega. Este script recorre
todos los StaffMember y vuelve a pasar `phone` por normalize_phone (que convierte
+543417207797 → +5493417207797), commiteando solo los que cambian.

A partir de ahora el envío también normaliza en caliente (whatsapp_service._normalized_to),
así que este script es para dejar la DB consistente.

Ejecutar una sola vez desde backend/:  python scripts/normalize_staff_phones.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Importar TODOS los módulos de modelos para que SQLAlchemy resuelva los mappers
# (relaciones cross-módulo referidas por nombre).
import importlib
import pkgutil
import app.models as _models_pkg
for _m in pkgutil.iter_modules(_models_pkg.__path__):
    if _m.name not in ("database", "schemas"):
        importlib.import_module(f"app.models.{_m.name}")

from app.models.database import SessionLocal
from app.models.staff import StaffMember
from app.utils.phone_normalizer import to_ar_whatsapp


def main():
    db = SessionLocal()
    try:
        miembros = db.query(StaffMember).all()
        cambios = 0
        for m in miembros:
            if not m.phone:
                continue
            nuevo = to_ar_whatsapp(m.phone)
            if nuevo and nuevo != m.phone:
                print(f"  {m.name}: {m.phone!r} -> {nuevo!r}")
                m.phone = nuevo
                cambios += 1
        if cambios:
            db.commit()
        print(f"OK: {cambios} teléfono(s) de staff normalizado(s) sobre {len(miembros)} miembro(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
