#!/bin/bash

# Solo CONFIG base (idempotente; no toca datos operativos). Los datos demo
# (equipo, tickets, pasajeros) NO se siembran en el deploy: se cargan a mano o
# con seed_demo_data desde el backoffice, para que la base se mantenga limpia.
python seed_hotel.py || echo "[warn] seed_hotel.py falló, continuando..."
python seed_room_units.py || echo "[warn] seed_room_units.py falló, continuando..."
python ingest_docs.py || echo "[warn] ingest_docs.py falló, continuando..."
python seed_knowledge.py || echo "[warn] seed_knowledge.py falló, continuando..."
# Promociones (config): la tabla debe coincidir con el doc RAG promociones.md, o el
# agente ofrece promos que la tool no puede confirmar. Idempotente; re-ingesta al RAG.
python seed_promotions.py || echo "[warn] seed_promotions.py falló, continuando..."

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
