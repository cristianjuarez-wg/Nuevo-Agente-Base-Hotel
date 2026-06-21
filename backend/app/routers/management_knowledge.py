"""
Repositorio de conocimiento del AGENTE DE GERENCIA (consultoría) — SEPARADO de Aura.

El dueño sube acá documentos de entrenamiento (libros de gestión hotelera, revenue
management, finanzas, etc.) que alimentan SOLO al consultor de gerencia. Usan una
colección vectorial propia (`management_knowledge`), aislada del conocimiento de
huéspedes: un huésped jamás recibe este contenido.

Reutiliza el pipeline existente (pdf_processor + VectorStoreService) apuntando a la
colección de gerencia. El listado se deriva de la metadata en Chroma (sin tabla nueva).
"""
import os
import time
import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services.pdf_processor import pdf_processor
from app.services.vector_store import get_management_vector_store
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/management-knowledge", tags=["ManagementKnowledge"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "management")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024


class TextDocPayload(BaseModel):
    title: str
    text: str


class StatusPayload(BaseModel):
    status: str  # "active" | "inactive"


def _chunks_from_text(title: str, text: str):
    """Chunkea texto pegado con el mismo formato que pdf_processor (doc_id, chunk_index…)."""
    doc_id = hashlib.md5(title.encode()).hexdigest()
    # Reutilizamos el splitter del pdf_processor para mantener consistencia.
    pieces = pdf_processor.text_splitter.split_text(text) if hasattr(pdf_processor, "text_splitter") else [text]
    now = datetime.now().isoformat()
    return [
        {
            "text": piece,
            "metadata": {
                "doc_id": doc_id, "chunk_index": i, "source": title,
                "status": "active", "uploaded_at": now,
            },
        }
        for i, piece in enumerate(pieces)
    ]


@router.get("/documents")
async def list_documents():
    """Lista los documentos de conocimiento de gerencia con su estado."""
    vs = get_management_vector_store()
    return {"documents": vs.get_all_sources_with_status()}


# Formatos de texto plano que se ingieren DIRECTO (sin parsear): el Markdown ya viene
# estructurado (encabezados, listas) — ideal para el chunking y la recuperación del agente.
_TEXT_EXTS = (".md", ".markdown", ".txt")


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Sube un documento de entrenamiento del consultor: PDF, Markdown (.md) o texto (.txt).

    El PDF se parsea (extracción de texto); el Markdown/TXT entra directo como texto limpio,
    que suele venir mejor estructurado para el agente. Ambos terminan en la misma colección.
    """
    start = time.time()
    name = (file.filename or "").lower()
    is_pdf = name.endswith(".pdf")
    is_text = name.endswith(_TEXT_EXTS)
    if not (is_pdf or is_text):
        raise HTTPException(status_code=400, detail="Formatos aceptados: PDF, Markdown (.md) o texto (.txt).")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Archivo > {settings.MAX_FILE_SIZE_MB}MB.")

    try:
        if is_pdf:
            path = os.path.join(UPLOAD_DIR, file.filename)
            with open(path, "wb") as f:
                f.write(content)
            chunks = pdf_processor.process_pdf(path, file.filename)
        else:
            text = content.decode("utf-8", errors="replace").strip()
            if not text:
                raise HTTPException(status_code=422, detail="El archivo está vacío.")
            chunks = _chunks_from_text(file.filename, text)

        if not chunks:
            raise HTTPException(status_code=422, detail="No se pudo extraer contenido del documento.")
        vs = get_management_vector_store()
        vs.delete_by_source(file.filename)  # reemplazar versión previa
        result = await vs.add_documents(chunks)
        logger.info("Mgmt knowledge ingested", filename=file.filename,
                    kind="pdf" if is_pdf else "text", added=result.get("added"))
        return {
            "success": True, "filename": file.filename,
            "chunks_created": result.get("added", 0),
            "processing_time": f"{time.time() - start:.2f}s",
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("Mgmt knowledge ingest error", filename=file.filename, error=str(e))
        raise HTTPException(status_code=500, detail="No se pudo procesar el documento.")


@router.post("/documents/text")
async def upload_text_document(payload: TextDocPayload):
    """Carga conocimiento a partir de texto pegado (sin PDF)."""
    title = payload.title.strip()
    text = payload.text.strip()
    if not title or not text:
        raise HTTPException(status_code=400, detail="Título y texto son obligatorios.")
    vs = get_management_vector_store()
    vs.delete_by_source(title)
    result = await vs.add_documents(_chunks_from_text(title, text))
    return {"success": True, "filename": title, "chunks_created": result.get("added", 0)}


@router.patch("/documents/{filename}/status")
async def set_document_status(filename: str, payload: StatusPayload):
    """Activa/desactiva un documento (inactivo = excluido de las búsquedas del consultor)."""
    status = payload.status if payload.status in ("active", "inactive") else "active"
    vs = get_management_vector_store()
    doc_id = hashlib.md5(filename.encode()).hexdigest()
    vs.update_document_status(doc_id, status)
    return {"success": True, "filename": filename, "status": status}


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    """Elimina un documento de conocimiento de gerencia."""
    vs = get_management_vector_store()
    result = vs.delete_by_source(filename)
    return {"success": True, "deleted": result.get("deleted", 0)}
