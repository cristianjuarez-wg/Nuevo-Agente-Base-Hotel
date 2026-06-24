"""
Listas de tablas para el RESET de datos operativos + helper de borrado.

Fuente ÚNICA de la verdad sobre qué tablas son DATOS DE USUARIO (se vacían al resetear)
y cuáles son CONFIGURACIÓN/CATÁLOGO del cliente (se preservan). Tanto el script CLI
`reset_data.py` como el endpoint del backoffice (`POST /api/demo/reset-all`) importan de
acá, para que agregar una tabla nueva se haga en un solo lugar.

El reset borra TODO lo operativo SIN filtrar por is_demo (a diferencia del "Limpiar demo"
que solo borra is_demo=True). Es decir, también borra lo que generaron usuarios reales.
"""
from sqlalchemy import text


# Tablas de DATOS operativos a vaciar, en orden hijos → padres (respeta FKs; clave en
# Postgres/Render donde las FKs SÍ se aplican).
DATA_TABLES_IN_ORDER = [
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

# Tablas de CONFIG que se PRESERVAN (NO se tocan). Incluye la carta del restaurante
# (menu_items) y el catálogo de paquetes (tour_packages).
CONFIG_TABLES = [
    "rooms", "room_units", "chat_themes", "knowledge_entries", "places",
    "documents", "exchange_rate_config", "agent_budget_config", "promotions",
    "menu_items", "alert_settings", "geographic_mappings", "airport_terminals",
]


def count_table(conn, table: str):
    """COUNT de una tabla por SQL crudo. None si la tabla no existe."""
    try:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    except Exception:  # noqa: BLE001 — tabla inexistente en esta DB
        return None


def reset_all(conn) -> dict:
    """Borra TODOS los datos operativos sobre la conexión dada. Devuelve {tabla: filas}.

    Cada DELETE va aislado: si una tabla no existe o falla, no aborta el resto. El caller
    debe pasar una conexión en AUTOCOMMIT (o commitear) para que los DELETE persistan.
    Solo borra tablas que existen y tienen filas (para reportar conteos reales).
    """
    before = {t: count_table(conn, t) for t in DATA_TABLES_IN_ORDER}
    deleted = {}
    for t in DATA_TABLES_IN_ORDER:
        n = before.get(t)
        if n:  # existe y tiene filas
            try:
                conn.execute(text(f"DELETE FROM {t}"))
                deleted[t] = n
            except Exception:  # noqa: BLE001 — no abortar el resto
                pass
    return deleted
