"""
Servicio del repositorio de conocimiento: re-ingesta automática al vector store.

Cada vez que una KnowledgeEntry o un Place se crea/edita/borra/cambia de estado desde
el backoffice, este servicio sincroniza ChromaDB en caliente (sin redeploy):

  1. Borra los chunks viejos de esa entidad por su `doc_source` (delete_by_source).
  2. Si la entidad queda activa, chunkea su `to_ingest_text()` y los re-agrega.

Reutiliza el mismo splitter/metadata que ingest_docs.py para que el agente (vía la tool
info_hotel → rag_service) la encuentre igual que a los documentos base.
"""
import hashlib
from typing import Union

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.core.rag.vector_store import get_vector_store
from app.core.observability.logging_config import get_logger
from app.models.knowledge import KnowledgeEntry, Place

logger = get_logger(__name__)

Ingestable = Union[KnowledgeEntry, Place]


def _build_chunks(doc_source: str, text: str):
    """Chunkea texto con el mismo criterio que ingest_docs.py."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(text)
    doc_id = hashlib.md5(doc_source.encode()).hexdigest()[:12]
    chunks = []
    for i, piece in enumerate(pieces):
        chunks.append({
            "text": piece,
            "metadata": {
                "doc_id": doc_id,
                "chunk_index": i,
                "status": "active",
                "source": doc_source,
                "filename": doc_source,
            },
        })
    return chunks


async def reingest(entity: Ingestable) -> dict:
    """Re-ingesta una entidad del repositorio. Idempotente: borra y vuelve a agregar.

    - Siempre borra los chunks previos de `entity.doc_source`.
    - Si la entidad está activa y tiene texto, agrega los chunks nuevos.
    Devuelve {deleted, added}.
    """
    vs = get_vector_store()
    source = entity.doc_source

    # 1. Borrar chunks previos de esta entidad (si los hay).
    deleted = 0
    try:
        result = vs.delete_by_source(source)
        deleted = result.get("deleted", 0)
    except Exception as e:
        logger.warning("reingest: delete_by_source falló", source=source, error=str(e))

    # 2. Re-agregar si está activa.
    added = 0
    if getattr(entity, "status", "active") == "active":
        text = entity.to_ingest_text().strip()
        if text:
            chunks = _build_chunks(source, text)
            try:
                add_result = await vs.add_documents(chunks)
                added = add_result.get("added", 0)
            except Exception as e:
                logger.error("reingest: add_documents falló", source=source, error=str(e))

    logger.info("Knowledge re-ingested", source=source, deleted=deleted, added=added)
    return {"deleted": deleted, "added": added}


async def remove_from_index(entity: Ingestable) -> dict:
    """Quita por completo una entidad del vector store (al borrarla del repositorio)."""
    vs = get_vector_store()
    source = entity.doc_source
    try:
        result = vs.delete_by_source(source)
        deleted = result.get("deleted", 0)
    except Exception as e:
        logger.warning("remove_from_index falló", source=source, error=str(e))
        deleted = 0
    logger.info("Knowledge removed from index", source=source, deleted=deleted)
    return {"deleted": deleted}
