"""
Reset de DATOS operativos del prototipo — deja la base "en cero" pero conserva la
CONFIGURACIÓN (habitaciones, unidades, temas, conocimiento, docs, carta, promos,
cotización, topes del agente).

Borra TODO lo operativo sin filtrar por is_demo: pasajeros, reservas, leads,
conversaciones, mensajes, tickets, pedidos, reservas de mesa, vouchers, equipo,
snapshots y la data legacy de turismo. Así no quedan huérfanos ni residuos que
hagan desconfiar de los datos (que era el problema: contactos fantasma, vouchers
con is_demo=False referenciando demo, etc.).

El orden es hijos → padres para respetar las FKs (clave en Postgres/Render, donde
las FKs SÍ se aplican; en SQLite están apagadas pero igual respetamos el orden).

Uso:
  python reset_data.py            # pide confirmación
  python reset_data.py --yes      # sin preguntar (para correr contra Render)
  python reset_data.py --status   # solo muestra conteos, no borra

Para Render: setear DATABASE_URL a la "External Database URL" de Render y correr
con --yes. La config se vuelve a sembrar sola en el próximo deploy (start.sh).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def _prepare():
    """Importa todos los modelos y asegura el esquema (como hace seed_demo_data)."""
    import importlib
    import pkgutil
    import app.models.staff  # noqa: F401 — staff antes que hotel (FK staff_members)
    import app.models as models_pkg
    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    from app.models.database import Base, engine, run_light_migrations
    Base.metadata.create_all(bind=engine)
    run_light_migrations()


# Tablas de DATOS operativos a vaciar, en orden hijos → padres.
# (Nombres de __tablename__; se truncan con DELETE para no tocar el esquema.)
_DATA_TABLES_IN_ORDER = [
    # Restaurante (hijos primero)
    "voucher_items",
    "vouchers",
    "table_reservations",
    "order_items",
    "extra_charges",
    "restaurant_orders",
    # Tickets / soporte del hotel
    "ticket_events",
    "hotel_tickets",
    # Conversaciones y leads
    "conversation_messages",
    "lead_messages",
    "leads",
    "conversations",
    # Reservas
    "bookings",
    # Contactos y equipo
    "contacts",
    "staff_members",
    # Inteligencia / snapshots (datos, no config)
    "agent_snapshots",
    "metrics_snapshots",
    "action_plans",
    "learning_opportunities",
    # Legacy turismo (datos)
    "package_documents",
    "package_itinerary",
    "package_activities",
    "package_transfers",
    "package_accommodations",
    "package_flights",
    "shared_flights",
    "package_passengers",
    "ticket_interactions",
    "support_tickets",
    "postsale_sessions",
    "sold_packages",
    "tour_packages",
    "provider_interactions_log",
    "provider_contacts",
    "providers",
    "flight_status_tracking",
    "terminal_discovery_log",
]

# Tablas de CONFIG que se PRESERVAN (solo para mostrar en el status; no se tocan):
_CONFIG_TABLES = [
    "rooms", "room_units", "chat_themes", "knowledge_entries", "places",
    "documents", "exchange_rate_config", "agent_budget_config", "promotions",
    "menu_items", "alert_settings", "geographic_mappings", "airport_terminals",
]


def _counts(db) -> dict:
    from sqlalchemy import text
    out = {}
    for t in _DATA_TABLES_IN_ORDER:
        try:
            out[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        except Exception:
            out[t] = None  # tabla inexistente en esta DB
    return out


def reset(db) -> dict:
    """Borra todos los datos operativos. Devuelve cuántas filas había por tabla."""
    from sqlalchemy import text
    before = _counts(db)
    for t in _DATA_TABLES_IN_ORDER:
        if before.get(t):  # solo si la tabla existe y tiene filas
            db.execute(text(f"DELETE FROM {t}"))
    db.commit()
    return {t: n for t, n in before.items() if n}


def main():
    _prepare()
    from app.models.database import SessionLocal
    from sqlalchemy import text

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    db = SessionLocal()
    try:
        if arg == "--status":
            print("Datos operativos actuales:")
            for t, n in _counts(db).items():
                if n:
                    print(f"  {t:>26}: {n}")
            print("\nConfig preservada:")
            for t in _CONFIG_TABLES:
                try:
                    n = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    print(f"  {t:>26}: {n}")
                except Exception:
                    pass
            return

        if arg not in ("--yes", "-y"):
            print("⚠️  Esto BORRA todos los datos operativos (pasajeros, reservas, leads,")
            print("    conversaciones, tickets, pedidos, equipo…). La config se conserva.")
            print("    Volvé a correr con --yes para confirmar.")
            return

        print("Borrando datos operativos…")
        deleted = reset(db)
        if deleted:
            print("\nFilas eliminadas por tabla:")
            for t, n in deleted.items():
                print(f"  {t:>26}: {n}")
        else:
            print("  (no había datos que borrar)")
        print("\n✅ Base en cero. La configuración (habitaciones, temas, conocimiento, "
              "carta, promos) quedó intacta.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
