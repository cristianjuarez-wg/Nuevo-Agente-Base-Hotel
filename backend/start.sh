#!/bin/bash
set -euo pipefail

# Arranque RUBRO-AGNÓSTICO: migraciones + servidor. Nada de datos de un cliente acá.
#
# Los seeds del Hampton (seed_hotel, seed_room_units, seed_knowledge, seed_places,
# seed_promotions) salieron de este script (hallazgo C4 de la auditoría): eran datos
# hardcodeados de UN cliente ejecutándose en CADA boot, con `set -e`, así que un seed roto
# tumbaba producción. Además re-ingestaban el RAG en cada restart sin necesidad.
#
# La provisión de una instancia es ONE-SHOT y se hace con el mecanismo que ya existe:
#     python -m instance.bootstrap_instance instance/<cliente>.yaml
#     python ingest_docs.py          # solo si cambiaron los docs de docsbase/
# Ver docs/RUNBOOK_NUEVA_INSTANCIA.md. El RAG persiste en disco
# (CHROMA_PERSIST_DIRECTORY=/data/chroma_db en Render), así que no hace falta re-ingestar
# en cada arranque: se corre cuando se editan los documentos.

# `python -m uvicorn` en vez de `uvicorn` a secas: funciona igual en Render y en un entorno
# local donde el binario no esté en el PATH (Windows/venv).
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
