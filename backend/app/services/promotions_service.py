"""
Servicio de PROMOCIONES: re-ingesta automática al vector store + query de vigentes.

Sigue el mismo patrón que knowledge_service.py:
  - reingest(promo): borra chunks viejos y re-agrega si la promo está activa.
  - remove_from_index(promo): borra completamente del vector store al eliminar.
  - get_vigentes(db): query determinística de promos activas y dentro de rango de fechas.
    La usa el handler de la tool `promos_vigentes`.
"""
import hashlib
from datetime import datetime
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.config import settings
from app.services.vector_store import get_vector_store
from app.core.logging_config import get_logger
from app.models.promotions import Promotion

logger = get_logger(__name__)


def _build_chunks(doc_source: str, text: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(text)
    doc_id = hashlib.md5(doc_source.encode()).hexdigest()[:12]
    return [
        {
            "text": piece,
            "metadata": {
                "doc_id": doc_id,
                "chunk_index": i,
                "status": "active",
                "source": doc_source,
                "filename": doc_source,
            },
        }
        for i, piece in enumerate(pieces)
    ]


async def reingest(promo: Promotion) -> dict:
    """Re-ingesta una promoción. Idempotente: borra y vuelve a agregar."""
    vs = get_vector_store()
    source = promo.doc_source

    deleted = 0
    try:
        result = vs.delete_by_source(source)
        deleted = result.get("deleted", 0)
    except Exception as e:
        logger.warning("promotions reingest: delete_by_source falló", source=source, error=str(e))

    added = 0
    if promo.status == "active":
        text = promo.to_ingest_text().strip()
        if text:
            chunks = _build_chunks(source, text)
            try:
                add_result = await vs.add_documents(chunks)
                added = add_result.get("added", 0)
            except Exception as e:
                logger.error("promotions reingest: add_documents falló", source=source, error=str(e))

    logger.info("Promotion re-ingested", source=source, deleted=deleted, added=added)
    return {"deleted": deleted, "added": added}


async def remove_from_index(promo: Promotion) -> dict:
    """Quita la promoción del vector store al eliminarla."""
    vs = get_vector_store()
    source = promo.doc_source
    deleted = 0
    try:
        result = vs.delete_by_source(source)
        deleted = result.get("deleted", 0)
    except Exception as e:
        logger.warning("promotions remove_from_index falló", source=source, error=str(e))
    logger.info("Promotion removed from index", source=source, deleted=deleted)
    return {"deleted": deleted}


def get_vigentes(db: Session) -> List[Promotion]:
    """Devuelve las promociones activas y dentro de su rango de fechas (si tienen)."""
    now = datetime.now()
    promos = db.query(Promotion).filter(Promotion.status == "active").all()
    vigentes = []
    for p in promos:
        if p.valid_from and p.valid_from > now:
            continue
        if p.valid_until and p.valid_until < now:
            continue
        vigentes.append(p)
    return vigentes
