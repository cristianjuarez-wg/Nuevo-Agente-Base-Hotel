#!/bin/bash
set -euo pipefail

# Seeds de configuración base (idempotentes; no tocan datos operativos). Son CRÍTICOS
# para el arranque: si alguno falla, el backend no debe levantar con datos corruptos o
# RAG desactualizado. Por eso el script es fail-fast (set -e).
python seed_hotel.py
python seed_room_units.py
python ingest_docs.py
python seed_knowledge.py
# Lugares y excursiones de Bariloche + comercios amigos (config del agente).
# Idempotente; re-ingesta al RAG para que el agente recomiende qué hacer en la zona.
python seed_places.py
# Promociones (config): la tabla debe coincidir con el doc RAG promociones.md, o el
# agente ofrece promos que la tool no puede confirmar. Idempotente; re-ingesta al RAG.
python seed_promotions.py

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
