"""
Seed del hotel para la demo: Hampton by Hilton Bariloche.

Datos basados en el sitio real (https://www.hamptonbariloche.com/). El dueño de este
hotel verá la presentación. Precios MULTIMONEDA (USD y ARS) estimados de demostración
(el sitio real no publica tarifas) — editables.

Crea los tipos de habitación si la tabla está vacía. Idempotente.
Ejecutar:  python seed_hotel.py
"""
from app.models.database import SessionLocal
from app.models.hotel import Room

HOTEL_NAME = "Hampton by Hilton Bariloche"

# URLs de imágenes reales del sitio del hotel.
ROOMS = [
    {
        "room_type": "King",
        "description": "Amplia cama Hampton bed®, ideal para parejas o viajeros que "
                       "buscan confort.",
        "capacity": 3,  # 2 adultos + 1 (menor o cama extra)
        "base_price_usd": 120.0,
        "base_price_ars": 126000.0,
        "total_units": 20,
        "bed_config": "1 cama king (Hampton bed®)",
        "view": "Lago o ciudad",
        "images": [
            "https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_02-0b2b9eb8-1920w.jpg"
        ],
        "amenities": ["WiFi gratis", "Hampton bed®", "Minibar", "Smart TV",
                      "Despertador Bluetooth", "Escritorio", "Caja fuerte"],
    },
    {
        "room_type": "Twin",
        "description": "Dos camas singles, para no fumadores. Perfecta para amigos o "
                       "viajeros de negocios.",
        "capacity": 3,
        "base_price_usd": 110.0,
        "base_price_ars": 115500.0,
        "total_units": 18,
        "bed_config": "2 camas twin (singles)",
        "view": "Lago o ciudad",
        "images": [
            "https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_11-8766d766-1920w.jpg"
        ],
        "amenities": ["WiFi gratis", "Minibar", "Smart TV 40\"", "Escritorio",
                      "Vajilla para té/café", "Plancha y tabla", "Caja fuerte"],
    },
    {
        "room_type": "Family Plan",
        "description": "Espaciosa para familias, con dos camas queen size Hampton bed®.",
        "capacity": 4,  # 2 adultos + 2 menores
        "base_price_usd": 165.0,
        "base_price_ars": 173250.0,
        "total_units": 8,
        "bed_config": "2 camas queen (Hampton bed®)",
        "view": "Lago o ciudad",
        "images": [
            "https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_02-0b2b9eb8-1920w.jpg"
        ],
        "amenities": ["WiFi gratis", "Hampton bed®", "Minibar", "Smart TV",
                      "Escritorio", "Apta familias"],
    },
    {
        "room_type": "Doble Twin Accesible",
        "description": "Accesible para movilidad reducida: dos camas Hampton bed®, ducha "
                       "a ras de suelo y accesorios adaptados.",
        "capacity": 3,
        "base_price_usd": 110.0,
        "base_price_ars": 115500.0,
        "total_units": 2,
        "bed_config": "2 camas Hampton bed®",
        "view": "Lago o ciudad",
        "images": [
            "https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_30-1920w.jpg"
        ],
        "amenities": ["WiFi gratis", "Accesible (movilidad reducida)",
                      "Ducha a ras de suelo", "Despertador accesible", "Minibar",
                      "TV alta definición", "Accesorios de baño adaptados"],
    },
]


# Campos de catálogo que el seed mantiene sincronizados en habitaciones ya existentes
# (no tocan reservas). Permite actualizar descripciones/precios/imágenes editando este
# archivo y volviendo a correr el seed, sin borrar datos.
_SYNC_FIELDS = ("description", "base_price_usd", "base_price_ars", "bed_config",
                "view", "images", "amenities", "capacity", "total_units")


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Room).count()
        if existing > 0:
            # Idempotente para altas, pero SÍ sincroniza campos de catálogo editables.
            updated = 0
            for r in ROOMS:
                room = db.query(Room).filter(Room.room_type == r["room_type"]).first()
                if not room:
                    db.add(Room(**r))
                    updated += 1
                    continue
                changed = False
                for f in _SYNC_FIELDS:
                    if getattr(room, f) != r.get(f):
                        setattr(room, f, r.get(f))
                        changed = True
                if changed:
                    updated += 1
            db.commit()
            print(f"[seed] {existing} habitaciones ya existían; sincronizadas/creadas: {updated}.")
            return
        for r in ROOMS:
            db.add(Room(**r))
        db.commit()
        print(f"[seed] {len(ROOMS)} tipos de habitacion creados para '{HOTEL_NAME}'.")
        for r in db.query(Room).order_by(Room.base_price_usd).all():
            print(f"   - {r.room_type}: USD {r.base_price_usd:.0f} / ARS {r.base_price_ars:.0f} "
                  f"x{r.total_units} (cap {r.capacity})")
    finally:
        db.close()


def _prepare_db():
    """Crea tablas y aplica migraciones livianas ANTES de sembrar.

    En Render la DB de PostgreSQL es nueva/incompleta y los seeds corren antes de que
    arranque la app (donde normalmente corre run_light_migrations en el lifespan). Sin
    esto, el seed consulta columnas que aún no existen (ej. rooms.status) y falla.
    Importa todos los modelos para que create_all genere todas las tablas y FKs.
    """
    import importlib
    import pkgutil
    import app.models as models_pkg
    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    from app.models.database import Base, engine, run_light_migrations
    Base.metadata.create_all(bind=engine)
    run_light_migrations()


if __name__ == "__main__":
    _prepare_db()
    seed()
