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
        "description": "Habitación con amplia cama Hampton bed®, ideal para parejas o "
                       "viajeros que buscan confort. Disponible con vista al lago o a la ciudad.",
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
        "description": "Habitación para no fumadores con dos camas singles. Perfecta para "
                       "amigos o viajeros de negocios. Vista al lago o a la ciudad.",
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
        "description": "Habitación espaciosa para grupos familiares, con dos camas queen "
                       "size Hampton bed®. Vista al lago o a la ciudad.",
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
        "description": "Habitación accesible para personas con movilidad reducida, con dos "
                       "camas Hampton bed®, ducha a ras de suelo y accesorios adaptados.",
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


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Room).count()
        if existing > 0:
            print(f"[seed] Ya hay {existing} habitaciones. No se hace nada (idempotente).")
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


if __name__ == "__main__":
    seed()
