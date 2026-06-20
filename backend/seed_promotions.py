"""
Seed inicial de promociones del Hampton by Hilton Bariloche.

Ejecutar UNA sola vez con el backend corriendo:
  python seed_promotions.py

Si la promo ya existe (mismo nombre), la omite.
"""
import asyncio
import sys
import os

# Asegurar que el package app sea importable desde backend/
sys.path.insert(0, os.path.dirname(__file__))

from app.models.database import SessionLocal
from app.models.promotions import Promotion
from app.services import promotions_service

PROMOS = [
    {
        "name": "Promo Residentes",
        "description": (
            "Tarifa preferencial exclusiva para residentes argentinos. "
            "Presentando DNI válido al momento del check-in, accedés a una tarifa especial "
            "diseñada para que los argentinos disfruten de la Patagonia con un beneficio concreto."
        ),
        "conditions": "Válida solo para residentes argentinos con DNI. Tarifa sujeta a disponibilidad.",
        "discount_type": "other",
        "discount_value": None,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
    {
        "name": "Stay & Park",
        "description": (
            "Combiná tu estadía con el estacionamiento privado cubierto del hotel sin costo adicional. "
            "Ideal para quienes viajan en auto y quieren tener su vehículo seguro durante toda la visita."
        ),
        "conditions": "Incluye una plaza de estacionamiento cubierto por noche de estadía. Sujeto a disponibilidad.",
        "discount_type": "other",
        "discount_value": None,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
    {
        "name": "Hampton en Familia",
        "description": (
            "Promoción especial para familias que eligen las habitaciones Family Plan. "
            "Disfrutá de una tarifa con beneficios pensados para que padres e hijos tengan "
            "todo el espacio y la comodidad que necesitan en Bariloche."
        ),
        "conditions": "Válida para habitaciones Family Plan. Menores hasta 12 años sin cargo adicional (sin ocupar plaza).",
        "discount_type": "other",
        "discount_value": None,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
    {
        "name": "Promoción 4x3",
        "description": (
            "Pagás 3 noches y disfrutás 4. Una noche completamente bonificada para que puedas "
            "aprovechar más tiempo en la Patagonia sin pagar extra. Ideal para escapadas de fin de semana largo."
        ),
        "conditions": "Mínimo 4 noches de estadía. La noche bonificada es la de menor valor. Sujeta a disponibilidad.",
        "discount_type": "free_night",
        "discount_value": 1,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
    {
        "name": "Promoción 7x5",
        "description": (
            "Pagás 5 noches y disfrutás 7. Dos noches completamente gratuitas para quienes eligen "
            "unas vacaciones completas en Bariloche. La mejor relación precio-estadía del hotel."
        ),
        "conditions": "Mínimo 7 noches de estadía. Las 2 noches bonificadas son las de menor valor. Sujeta a disponibilidad.",
        "discount_type": "free_night",
        "discount_value": 2,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
]


async def seed():
    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for p in PROMOS:
            exists = db.query(Promotion).filter(Promotion.name == p["name"]).first()
            if exists:
                print(f"  --  Ya existe: {p['name']}")
                skipped += 1
                continue

            promo = Promotion(
                name=p["name"],
                description=p["description"],
                conditions=p["conditions"],
                discount_type=p["discount_type"],
                discount_value=p["discount_value"],
                status=p["status"],
                valid_from=p["valid_from"],
                valid_until=p["valid_until"],
            )
            db.add(promo)
            db.commit()
            db.refresh(promo)
            await promotions_service.reingest(promo)
            print(f"  OK  Creada: {promo.name} (id={promo.id})")
            created += 1

        print(f"\nSeed completo: {created} creadas, {skipped} omitidas.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(seed())
