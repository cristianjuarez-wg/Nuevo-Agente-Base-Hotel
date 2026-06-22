#!/bin/bash

# Crea tablas e ingesta documentos base solo si la DB está vacía.
python seed_hotel.py || echo "[warn] seed_hotel.py falló, continuando..."
python seed_room_units.py || echo "[warn] seed_room_units.py falló, continuando..."
# Equipo de demo con áreas (empleado digital — Fase 4). Idempotente; teléfonos ficticios.
python seed_staff.py || echo "[warn] seed_staff.py falló, continuando..."
# Ejemplos operativos con bitácora (tickets en cada estado del ciclo). Depende de seed_staff.
python seed_operations.py || echo "[warn] seed_operations.py falló, continuando..."
python ingest_docs.py || echo "[warn] ingest_docs.py falló, continuando..."
python seed_knowledge.py || echo "[warn] seed_knowledge.py falló, continuando..."

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
