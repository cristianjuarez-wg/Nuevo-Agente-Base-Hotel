"""
Seed de temas visuales estacionales para el chat widget (Fase 4).

Ejecutar UNA sola vez con el backend corriendo:
  python seed_themes.py

Si el tema ya existe (mismo nombre), lo omite.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.models.database import SessionLocal, run_light_migrations
from app.models.chat_theme import ChatTheme

THEMES = [
    {
        "name": "Navidad & Año Nuevo",
        "emoji": "🎄",
        "description": "Tema festivo de fin de año: rojo y verde navideño.",
        "active_from_month": 12, "active_from_day": 1,
        "active_until_month": 1,  "active_until_day": 8,
        "header_bg":    "#8b0000",   # rojo oscuro navideño
        "header_text":  "#ffffff",
        "accent_color": "#c41e3a",   # rojo brillante
        "bubble_bg":    "#fff8f8",
        "fab_bg":       "#8b0000",
        "fab_text":     "#ffffff",
        "effect": "snow_gold",
        "status": "active",
    },
    {
        "name": "Ski & Nieve",
        "emoji": "⛷️",
        "description": "Temporada alta de invierno: azules fríos y blancos nevados.",
        "active_from_month": 6, "active_from_day": 15,
        "active_until_month": 9, "active_until_day": 15,
        "header_bg":    "#0d2d5e",   # azul noche nevada
        "header_text":  "#e8f4fd",
        "accent_color": "#1565c0",   # azul ski
        "bubble_bg":    "#f0f6ff",
        "fab_bg":       "#0d2d5e",
        "fab_text":     "#ffffff",
        "effect": "snow",
        "status": "active",
    },
    {
        "name": "Verano Patagónico",
        "emoji": "🏔️",
        "description": "Temporada de verano: verde lago y turquesa patagónico.",
        "active_from_month": 12, "active_from_day": 21,
        "active_until_month": 3,  "active_until_day": 20,
        # Nota: Navidad tiene prioridad en dic — este entra cuando se desactiva Navidad (8 ene)
        "header_bg":    "#1b5e4a",   # verde lago
        "header_text":  "#ffffff",
        "accent_color": "#00796b",   # turquesa lago
        "bubble_bg":    "#f0faf7",
        "fab_bg":       "#1b5e4a",
        "fab_text":     "#ffffff",
        "effect": "leaves",
        "status": "active",
    },
    {
        "name": "Semana Santa",
        "emoji": "🐣",
        "description": "Feriado de Semana Santa: dorados y tierra cálida.",
        "active_from_month": 4, "active_from_day": 1,
        "active_until_month": 4, "active_until_day": 20,
        "header_bg":    "#6d4c1f",   # tierra cálida
        "header_text":  "#fdf6e3",
        "accent_color": "#c68b2b",   # dorado
        "bubble_bg":    "#fdf6e3",
        "fab_bg":       "#6d4c1f",
        "fab_text":     "#fdf6e3",
        "effect": "bunny",
        "status": "active",
    },
]


def seed():
    # Asegura que la columna 'effect' exista en la tabla ya creada.
    run_light_migrations()
    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for t in THEMES:
            exists = db.query(ChatTheme).filter(ChatTheme.name == t["name"]).first()
            if exists:
                # El tema ya existe: solo asignamos el efecto si todavía no tiene uno,
                # para no pisar ajustes manuales hechos desde el backoffice.
                if not exists.effect or exists.effect == "none":
                    exists.effect = t["effect"]
                    db.commit()
                    print(f"  ~~  Efecto asignado a existente: {t['name']} -> {t['effect']}")
                    updated += 1
                else:
                    print(f"  --  Ya existe con efecto: {t['name']} ({exists.effect})")
                continue
            theme = ChatTheme(**t)
            db.add(theme)
            db.commit()
            db.refresh(theme)
            print(f"  OK  Creado: {theme.name} (id={theme.id})")
            created += 1
        print(f"\nSeed completo: {created} creados, {updated} actualizados.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
