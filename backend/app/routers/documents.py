from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from app.models.database import Document, get_db, engine, Base
from app.models.schemas import (
    DocumentUploadResponse, 
    DocumentListResponse, 
    DocumentDeleteResponse,
    FileValidation,
    ErrorResponse,
    DocumentListWithStatusResponse, 
    DocumentWithStatus,
    DocumentStatusUpdate
)
from app.core.rag.pdf_processor import pdf_processor
from app.core.rag.vector_store import get_vector_store
from app.core.observability.logging_config import get_logger
from app.config import settings
import os
import shutil
import time
import hashlib
from typing import List
from datetime import datetime
from app.utils.timezone_utils import utcnow_naive

logger = get_logger(__name__)
router = APIRouter(prefix="/api/documents", tags=["Documents"])

# Configuración de archivos
UPLOAD_DIR = "./uploads"
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024  # Convertir a bytes
ALLOWED_EXTENSIONS = ['.pdf']

# Crear directorio de uploads si no existe
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Crear tablas al inicio
Base.metadata.create_all(bind=engine)

def validate_file(file: UploadFile) -> FileValidation:
    """Valida archivo subido"""
    
    # Validar extensión
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return FileValidation(
            is_valid=False,
            message=f"Solo se permiten archivos: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Validar nombre de archivo
    if len(file.filename) > 255:
        return FileValidation(
            is_valid=False,
            message="Nombre de archivo demasiado largo (máximo 255 caracteres)"
        )
    
    # Validar caracteres en nombre de archivo (permitir Unicode, ñ, acentos, etc.)
    import re
    # Permitir letras Unicode, números, espacios, guiones, puntos y guiones bajos
    # Excluir solo caracteres problemáticos para sistemas de archivos: < > : " | ? * /
    forbidden_chars = r'[<>:"|?*/\\]'
    if re.search(forbidden_chars, file.filename):
        return FileValidation(
            is_valid=False,
            message="Nombre de archivo contiene caracteres no permitidos (< > : \" | ? * / \\)"
        )
    
    return FileValidation(
        is_valid=True,
        message="Archivo válido",
        file_type=file.content_type
    )

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Sube y procesa un PDF con gestión de estado"""
    start_time = time.time()
    
    logger.info("Document upload started", 
               filename=file.filename,
               content_type=file.content_type)
    
    try:
        # Validar archivo
        validation = validate_file(file)
        if not validation.is_valid:
            logger.warning("File validation failed",
                          filename=file.filename,
                          reason=validation.message)
            raise HTTPException(status_code=400, detail=validation.message)
        
        # Verificar tamaño del archivo
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > MAX_FILE_SIZE:
            logger.warning("File too large",
                          filename=file.filename,
                          size_mb=file_size / (1024*1024),
                          max_mb=settings.MAX_FILE_SIZE_MB)
            raise HTTPException(
                status_code=413,
                detail=f"Archivo demasiado grande: {file_size/(1024*1024):.1f}MB > {settings.MAX_FILE_SIZE_MB}MB"
            )
        
        # Guardar archivo temporalmente
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        logger.info("File saved temporarily",
                   filename=file.filename,
                   path=file_path,
                   size_bytes=file_size)
        
        # Procesar PDF
        chunks = pdf_processor.process_pdf(file_path, file.filename)
        
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No se pudieron extraer chunks del PDF. Verifica que contenga texto."
            )
        
        # Guardar en base de datos
        doc_hash = hashlib.md5(file.filename.encode()).hexdigest()
        
        # Verificar si ya existe
        existing_doc = db.query(Document).filter_by(doc_id=doc_hash).first()
        
        if existing_doc:
            # Actualizar
            existing_doc.status = "active"
            existing_doc.chunks_count = len(chunks)
            existing_doc.uploaded_at = utcnow_naive()
            existing_doc.file_size = file_size
        else:
            # Crear nuevo
            new_doc = Document(
                doc_id=doc_hash,
                filename=file.filename,
                status="active",
                chunks_count=len(chunks),
                file_size=file_size
            )
            db.add(new_doc)
        
        db.commit()
        
        # Obtener vector store y agregar documentos
        vector_store = get_vector_store()
        
        # Eliminar versión anterior si existe
        delete_result = vector_store.delete_by_source(file.filename)
        if delete_result["deleted"] > 0:
            logger.info("Previous version deleted",
                       filename=file.filename,
                       deleted_chunks=delete_result["deleted"])
        
        # Agregar nuevos documentos
        add_result = await vector_store.add_documents(chunks)
        
        processing_time = time.time() - start_time
        
        logger.info("Document processing completed",
                   filename=file.filename,
                   chunks_created=add_result["added"],
                   processing_time=f"{processing_time:.2f}s")
        
        # Limpiar archivo temporal (opcional, mantenerlo para debug)
        # os.remove(file_path)
        
        return DocumentUploadResponse(
            filename=file.filename,
            chunks_created=add_result["added"],
            status="success",
            message=f"Documento procesado exitosamente: {add_result['added']} chunks creados",
            file_size=file_size,
            processing_time=f"{processing_time:.2f}s"
        )
    
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        processing_time = time.time() - start_time
        
        logger.error("Document processing error",
                    filename=file.filename,
                    error=str(e),
                    processing_time=f"{processing_time:.2f}s")
        
        # Limpiar archivo temporal si existe
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando documento: {str(e)}"
        )

@router.get("/list", response_model=DocumentListResponse)
async def list_documents():
    """Lista todos los documentos cargados"""
    try:
        logger.debug("Listing documents")
        
        vector_store = get_vector_store()
        sources = vector_store.get_all_sources()
        
        logger.info("Documents listed", count=len(sources))
        
        return DocumentListResponse(
            documents=sorted(sources),
            total=len(sources)
        )
    
    except Exception as e:
        logger.error("Error listing documents", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error listando documentos: {str(e)}"
        )

@router.get("/{filename}/download")
async def download_document(filename: str):
    """Descarga un documento"""
    try:
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
        from fastapi.responses import FileResponse
        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("download_error", filename=filename, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(
    filename: str,
    db: Session = Depends(get_db)
):
    """Elimina un documento del sistema (SQLite + ChromaDB + archivo físico)"""
    try:
        logger.info("Deleting document", filename=filename)
        
        # Validar nombre de archivo
        if not filename or len(filename) > 255:
            raise HTTPException(
                status_code=400,
                detail="Nombre de archivo inválido"
            )
        
        # 1. NUEVO: Verificar que el documento existe en SQLite
        document = db.query(Document).filter(Document.filename == filename).first()
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Documento '{filename}' no encontrado"
            )
        
        # 2. Eliminar de ChromaDB (código existente)
        vector_store = get_vector_store()
        result = vector_store.delete_by_source(filename)
        
        if result["deleted"] == 0:
            logger.warning("Document not found for deletion", filename=filename)
            raise HTTPException(
                status_code=404,
                detail=f"Documento '{filename}' no encontrado en vector store"
            )
        
        # 3. NUEVO: Eliminar de SQLite
        db.delete(document)
        db.commit()
        logger.info("Document deleted from database", filename=filename)
        
        # 4. NUEVO: Eliminar archivo físico
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Physical file deleted", filename=filename)
        
        logger.info("Document deleted successfully",
                   filename=filename,
                   chunks_deleted=result["deleted"])
        
        return DocumentDeleteResponse(
            filename=filename,
            deleted_count=result["deleted"],
            message=f"Documento '{filename}' eliminado exitosamente ({result['deleted']} chunks)",
            collection_size=result["collection_size"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()  # NUEVO: Rollback si falla
        logger.error("Error deleting document",
                    filename=filename,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando documento: {str(e)}"
        )

@router.get("/stats")
async def get_document_stats():
    """Obtiene estadísticas de documentos"""
    try:
        vector_store = get_vector_store()
        stats = vector_store.get_collection_stats()
        
        # Información adicional sobre archivos en uploads
        upload_files = []
        if os.path.exists(UPLOAD_DIR):
            upload_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith('.pdf')]
        
        return {
            "vector_store": stats,
            "upload_directory": {
                "path": UPLOAD_DIR,
                "files": upload_files,
                "count": len(upload_files)
            },
            "config": {
                "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
                "allowed_extensions": ALLOWED_EXTENSIONS
            }
        }
    
    except Exception as e:
        logger.error("Error getting document stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )

@router.get("/list-with-status", response_model=DocumentListWithStatusResponse)
async def list_documents_with_status(
    db: Session = Depends(get_db)
):
    """Lista todos los documentos con su estado"""
    try:
        documents = db.query(Document).order_by(Document.uploaded_at.desc()).all()
        
        docs_list = [DocumentWithStatus(**doc.to_dict()) for doc in documents]
        active_count = sum(1 for d in documents if d.status == "active")
        
        return DocumentListWithStatusResponse(
            documents=docs_list,
            total=len(documents),
            active_count=active_count,
            inactive_count=len(documents) - active_count
        )
    except Exception as e:
        logger.error("list_documents_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{filename}/activate")
async def activate_document(
    filename: str,
    db: Session = Depends(get_db)
):
    """Activa un documento"""
    try:
        doc = db.query(Document).filter_by(filename=filename).first()
        
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        
        doc.status = "active"
        db.commit()
        
        # Actualizar en ChromaDB
        vector_store = get_vector_store()
        vector_store.update_document_status(doc.doc_id, "active")
        
        logger.info("document_activated", filename=filename)
        
        return {
            "message": f"Documento '{filename}' activado exitosamente",
            "filename": filename,
            "status": "active"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("activate_document_error", filename=filename, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{filename}/deactivate")
async def deactivate_document(
    filename: str,
    db: Session = Depends(get_db)
):
    """Desactiva un documento"""
    try:
        doc = db.query(Document).filter_by(filename=filename).first()
        
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        
        doc.status = "inactive"
        db.commit()
        
        # Actualizar en ChromaDB
        vector_store = get_vector_store()
        vector_store.update_document_status(doc.doc_id, "inactive")
        
        logger.info("document_deactivated", filename=filename)
        
        return {
            "message": f"Documento '{filename}' desactivado exitosamente",
            "filename": filename,
            "status": "inactive"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("deactivate_document_error", filename=filename, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active")
async def get_active_documents(
    db: Session = Depends(get_db)
):
    """Obtiene solo los documentos activos"""
    try:
        active_docs = db.query(Document).filter_by(status="active").all()
        
        return {
            "documents": [doc.filename for doc in active_docs],
            "count": len(active_docs)
        }
    except Exception as e:
        logger.error("get_active_documents_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

