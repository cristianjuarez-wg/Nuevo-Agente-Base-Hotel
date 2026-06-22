"""
Seed del EQUIPO del hotel para la demo del "empleado digital" (Fase 4).

Crea miembros de staff con su ÁREA, para que el agente de operaciones pueda asignarles
los pedidos de servicio del huésped (mantenimiento/recepción/housekeeping) y notificarlos
por WhatsApp. También el dueño (para el agente de gerencia).

⚠️ Los TELÉFONOS son PLACEHOLDERS de demostración (números ficticios). Para probar el flujo
real por WhatsApp hay que reemplazarlos por los WhatsApp REALES de cada persona desde
Backoffice → Equipo (o editando este archivo). El agente reconoce a cada uno por su número:
un número NO cargado acá se trata como huésped.

Idempotente y marcado is_demo=True (se puede limpiar solo lo de demo). No pisa miembros
existentes con el mismo teléfono (tolerante al "9" móvil argentino).
Ejecutar:  python seed_staff.py
"""
from app.models.database import SessionLocal
from app.models.staff import StaffMember
from app.utils.phone_normalizer import normalize_phone, phones_match

# Equipo de demostración. Teléfonos FICTICIOS (reemplazar por los reales para la demo).
TEAM = [
    {
        "name": "Diego (Dueño)",
        "phone": "+54 9 294 400 0001",
        "role": "owner",
        "area": "general",
        "note": "Dueño/gerente — accede al agente de gerencia (BI).",
    },
    {
        "name": "Carlos (Mantenimiento)",
        "phone": "+54 9 294 400 0002",
        "role": "staff",
        "area": "mantenimiento",
        "note": "Recibe los pedidos de algo que no funciona (aire, agua, luz, etc.).",
    },
    {
        "name": "Sofía (Recepción)",
        "phone": "+54 9 294 400 0003",
        "role": "staff",
        "area": "recepcion",
        "note": "Llaves, late checkout, wake-up calls, equipaje, info.",
    },
    {
        "name": "Marta (Housekeeping)",
        "phone": "+54 9 294 400 0004",
        "role": "staff",
        "area": "housekeeping",
        "note": "Toallas, limpieza, amenities, blancos.",
    },
]


def _find_existing(db, phone: str):
    """Devuelve un StaffMember cuyo teléfono coincide (tolerante al '9'), o None."""
    for m in db.query(StaffMember).all():
        if phones_match(m.phone, phone):
            return m
    return None


def seed():
    db = SessionLocal()
    try:
        created, updated = 0, 0
        for member in TEAM:
            phone = normalize_phone(member["phone"]) or member["phone"]
            existing = _find_existing(db, phone)
            if existing:
                # No pisamos el teléfono (puede haberlo cambiado el cliente por el real),
                # pero sí mantenemos el área/rol sincronizados con la demo.
                changed = False
                if existing.area != member["area"]:
                    existing.area = member["area"]; changed = True
                if existing.role != member["role"]:
                    existing.role = member["role"]; changed = True
                if changed:
                    updated += 1
                continue
            db.add(StaffMember(
                name=member["name"], phone=phone, role=member["role"],
                area=member["area"], active=True, is_demo=True,
            ))
            created += 1
        db.commit()

        print(f"[seed] Equipo de demo: {created} creados, {updated} actualizados.")
        print("[seed] Miembros del equipo:")
        for m in db.query(StaffMember).order_by(StaffMember.role.desc(), StaffMember.name).all():
            tag = " (demo)" if m.is_demo else ""
            print(f"   • {m.name} — {m.role}/{m.area} — {m.phone}{tag}")
        print("\n[!] Telefonos de DEMO (ficticios). Reemplazalos por los WhatsApp reales")
        print("    desde Backoffice > Equipo para probar el flujo por WhatsApp.")
    finally:
        db.close()


if __name__ == "__main__":
    import app.main  # noqa: F401 — registra todos los modelos antes de tocar la DB
    seed()
