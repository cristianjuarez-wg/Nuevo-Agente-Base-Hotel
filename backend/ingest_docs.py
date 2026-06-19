"""
Ingesta de los documentos del hotel (docsbase/*.md) al vector store (ChromaDB).

Chunkea cada archivo y lo agrega con la metadata que espera el vector store:
doc_id, chunk_index, status="active", source. Idempotente a nivel de chunk (el
add_documents salta los IDs ya existentes).

Ejecutar:  python ingest_docs.py
"""
import asyncio
import hashlib
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.services.vector_store import get_vector_store
from app.models.database import SessionLocal
from app.models.database import Document

DOCSBASE = Path(__file__).parent / "docsbase"


def _build_chunks(filename: str, text: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(text)
    doc_id = hashlib.md5(filename.encode()).hexdigest()[:12]
    chunks = []
    for i, piece in enumerate(pieces):
        chunks.append({
            "text": piece,
            "metadata": {
                "doc_id": doc_id,
                "chunk_index": i,
                "status": "active",
                "source": filename,
                "filename": filename,
            },
        })
    return doc_id, chunks


async def main():
    files = sorted(DOCSBASE.glob("*.md"))
    if not files:
        print(f"[ingest] No hay .md en {DOCSBASE}")
        return

    vs = get_vector_store()
    db = SessionLocal()
    total_added = 0
    try:
        for f in files:
            text = f.read_text(encoding="utf-8")
            doc_id, chunks = _build_chunks(f.name, text)
            result = await vs.add_documents(chunks)
            total_added += result.get("added", 0)
            print(f"[ingest] {f.name}: +{result.get('added',0)} chunks "
                  f"(skip {result.get('skipped',0)})")

            # Registrar en la tabla documents (para que el filtro de activos y el
            # gestor de documentos lo reconozcan) si no existe.
            existing = db.query(Document).filter(Document.doc_id == doc_id).first()
            if not existing:
                db.add(Document(
                    doc_id=doc_id,
                    filename=f.name,
                    status="active",
                    chunks_count=len(chunks),
                    file_size=len(text),
                ))
                db.commit()

        print(f"[ingest] LISTO. Total chunks agregados: {total_added}. "
              f"Colección: {settings.CHROMA_COLLECTION_NAME}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
