#!/bin/bash
set -e

# Crea tablas e ingesta documentos base solo si la DB está vacía.
python seed_hotel.py
python ingest_docs.py

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
