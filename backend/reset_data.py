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


def _engine():
    """Engine directo a la DB destino (DATABASE_URL), SIN importar los modelos.

    Importar los modelos dispara migraciones a nivel de módulo (ALTER TABLE) que
    en Postgres abortan la transacción si una columna ya existe. Para borrar datos
    solo necesitamos SQL crudo por nombre de tabla, así que evitamos todo el ORM.
    """
    import os
    from sqlalchemy import create_engine
    url = os.environ.get("DATABASE_URL") or "sqlite:///./hotel.db"
    return create_engine(url)


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


def _count_table(conn, t):
    """COUNT de una tabla por SQL crudo. None si la tabla no existe."""
    from sqlalchemy import text
    try:
        return conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    except Exception:
        return None


def _counts(conn) -> dict:
    return {t: _count_table(conn, t) for t in _DATA_TABLES_IN_ORDER}


def reset(conn) -> dict:
    """Borra todos los datos operativos. Devuelve cuántas filas había por tabla.

    Cada DELETE va en su propia transacción autocommit: si una tabla no existe en
    esta DB, no aborta el resto (clave en Postgres).
    """
    from sqlalchemy import text
    before = _counts(conn)
    for t in _DATA_TABLES_IN_ORDER:
        if before.get(t):  # solo si la tabla existe y tiene filas
            conn.execute(text(f"DELETE FROM {t}"))
    return {t: n for t, n in before.items() if n}


def _which_db() -> str:
    import os
    url = os.environ.get("DATABASE_URL") or "sqlite:///./hotel.db"
    # Ocultar credenciales al imprimir.
    if "@" in url:
        return "postgres @ " + url.split("@", 1)[1]
    return url


def main():
    from sqlalchemy import text

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    engine = _engine()
    print(f"DB destino: {_which_db()}\n")

    # autocommit por sentencia: un DELETE que falle no invalida los demás.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if arg == "--status":
            print("Datos operativos actuales:")
            any_data = False
            for t, n in _counts(conn).items():
                if n:
                    print(f"  {t:>26}: {n}"); any_data = True
            if not any_data:
                print("  (sin datos operativos — base en cero)")
            print("\nConfig preservada:")
            for t in _CONFIG_TABLES:
                n = _count_table(conn, t)
                if n is not None:
                    print(f"  {t:>26}: {n}")
            return

        if arg not in ("--yes", "-y"):
            print("⚠️  Esto BORRA todos los datos operativos (pasajeros, reservas, leads,")
            print("    conversaciones, tickets, pedidos, equipo…). La config se conserva.")
            print("    Volvé a correr con --yes para confirmar.")
            return

        print("Borrando datos operativos…")
        deleted = reset(conn)
        if deleted:
            print("\nFilas eliminadas por tabla:")
            for t, n in deleted.items():
                print(f"  {t:>26}: {n}")
        else:
            print("  (no había datos que borrar)")
        print("\n✅ Base en cero. La configuración (habitaciones, temas, conocimiento, "
              "carta, promos) quedó intacta.")


if __name__ == "__main__":
    main()
