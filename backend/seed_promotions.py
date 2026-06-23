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
            "Tarifa preferencial exclusiva para residentes argentinos: 15% de descuento sobre la "
            "tarifa vigente. Presentando DNI argentino al momento del check-in, accedés a este "
            "beneficio diseñado para que los argentinos disfruten de la Patagonia."
        ),
        "conditions": "Válida solo para residentes argentinos con DNI argentino, presentado al check-in. 15% de descuento sobre la tarifa vigente. Sujeta a disponibilidad.",
        "discount_type": "percentage",
        "discount_value": 15,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
    {
        "name": "Stay & Park",
        "description": (
            "Combiná tu estadía con el estacionamiento privado cubierto del hotel sin costo adicional "
            "(un ahorro de ARS 8.000 por noche). Ideal para quienes viajan en auto y quieren tener su "
            "vehículo seguro durante toda la visita."
        ),
        "conditions": "Incluye una plaza de estacionamiento cubierto por noche de estadía, sin cargo (valor habitual ARS 8.000/noche). Sujeto a disponibilidad de plazas.",
        "discount_type": "other",
        "discount_value": None,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
    {
        "name": "Hampton en Familia",
        "description": (
            "Promoción especial para familias que eligen las habitaciones Family Plan: los menores "
            "de hasta 12 años no abonan cargo adicional (sin ocupar plaza) y el desayuno buffet está "
            "incluido para toda la familia. Pensada para que padres e hijos tengan todo el espacio y "
            "la comodidad que necesitan en Bariloche."
        ),
        "conditions": "Válida para habitaciones Family Plan. Menores hasta 12 años sin cargo adicional (sin ocupar plaza). Desayuno buffet incluido para toda la familia. Sujeta a disponibilidad.",
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
        "min_nights": 4,
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
        "min_nights": 7,
        "status": "active",
        "valid_from": None,
        "valid_until": None,
    },
]


async def seed():
    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for p in PROMOS:
            min_nights = p.get("min_nights")
            exists = db.query(Promotion).filter(Promotion.name == p["name"]).first()
            if exists:
                # Idempotente: actualiza TODOS los campos editables si alguno cambió y
                # re-ingesta al RAG. Antes solo miraba min_nights, así que editar precio o
                # condiciones de una promo existente no se aplicaba al re-correr el seed.
                campos = {
                    "description": p["description"],
                    "conditions": p["conditions"],
                    "discount_type": p["discount_type"],
                    "discount_value": p["discount_value"],
                    "min_nights": min_nights,
                    "status": p["status"],
                }
                cambios = {k: v for k, v in campos.items() if getattr(exists, k) != v}
                if cambios:
                    for k, v in cambios.items():
                        setattr(exists, k, v)
                    db.commit()
                    await promotions_service.reingest(exists)
                    print(f"  ~~  Actualizada ({', '.join(cambios)}): {p['name']}")
                    updated += 1
                else:
                    print(f"  --  Ya existe (sin cambios): {p['name']}")
                continue

            promo = Promotion(
                name=p["name"],
                description=p["description"],
                conditions=p["conditions"],
                discount_type=p["discount_type"],
                discount_value=p["discount_value"],
                min_nights=min_nights,
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

        print(f"\nSeed completo: {created} creadas, {updated} actualizadas.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(seed())
