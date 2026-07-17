import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Optional  # noqa: F401
from app.config import settings
from app.core.rag.embeddings import get_embedding_service
from app.core.observability.logging_config import get_logger
import os
import time

logger = get_logger(__name__)

class VectorStoreService:
    def __init__(self, collection_name: Optional[str] = None):
        """Vector store sobre ChromaDB.

        `collection_name` permite COLECCIONES SEPARADAS en el mismo Chroma: por defecto la
        de huéspedes (Aura); el agente de gerencia usa otra (conocimiento de consultoría),
        de modo que un huésped jamás recibe contenido de los libros de gestión.
        """
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        try:
            # Crear directorio si no existe
            os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)

            # Inicializar cliente ChromaDB
            self.client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIRECTORY,
                settings=ChromaSettings(anonymized_telemetry=False)
            )

            # Crear o obtener colección
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

            logger.info("Vector store initialized",
                       persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
                       collection_name=self.collection_name,
                       existing_documents=self.collection.count())

        except Exception as e:
            logger.error("Error initializing vector store", error=str(e))
            raise
    
    async def add_documents(self, chunks: List[Dict]) -> Dict:
        """Agrega documentos a la base vectorial"""
        try:
            start_time = time.time()
            
            if not chunks:
                raise ValueError("Lista de chunks vacía")
            
            texts = [chunk["text"] for chunk in chunks]
            metadatas = [chunk["metadata"] for chunk in chunks]
            
            logger.info("Adding documents to vector store", 
                       chunks_count=len(chunks),
                       total_characters=sum(len(text) for text in texts))
            
            # Generar embeddings
            embedding_service = get_embedding_service()
            embeddings = await embedding_service.embed_documents(texts)
            
            # Generar IDs únicos
            ids = [f"{chunk['metadata']['doc_id']}_{chunk['metadata']['chunk_index']}" 
                   for chunk in chunks]
            
            # Verificar si algunos documentos ya existen
            existing_ids = set()
            try:
                existing_docs = self.collection.get(ids=ids)
                existing_ids = set(existing_docs['ids'])
                if existing_ids:
                    logger.warning("Some documents already exist", 
                                 existing_count=len(existing_ids))
            except Exception:
                pass  # Colección vacía o error menor
            
            # Filtrar documentos nuevos
            new_chunks = []
            new_embeddings = []
            new_metadatas = []
            new_ids = []
            
            for i, chunk_id in enumerate(ids):
                if chunk_id not in existing_ids:
                    new_chunks.append(texts[i])
                    new_embeddings.append(embeddings[i])
                    new_metadatas.append(metadatas[i])
                    new_ids.append(chunk_id)
            
            if new_chunks:
                # Agregar a ChromaDB
                self.collection.add(
                    embeddings=new_embeddings,
                    documents=new_chunks,
                    metadatas=new_metadatas,
                    ids=new_ids
                )
                
                duration = time.time() - start_time
                
                logger.info("Documents added to vector store", 
                           new_documents=len(new_chunks),
                           skipped_existing=len(existing_ids),
                           total_in_collection=self.collection.count(),
                           duration=f"{duration:.2f}s")
                
                return {
                    "added": len(new_chunks),
                    "skipped": len(existing_ids),
                    "total": len(chunks),
                    "collection_size": self.collection.count()
                }
            else:
                logger.info("No new documents to add", 
                           all_existing=len(existing_ids))
                return {
                    "added": 0,
                    "skipped": len(existing_ids),
                    "total": len(chunks),
                    "collection_size": self.collection.count()
                }
                
        except Exception as e:
            logger.error("Error adding documents to vector store", 
                        chunks_count=len(chunks) if chunks else 0,
                        error=str(e))
            raise
    
    async def search(self, query: str, n_results: int = None, 
                     only_active: bool = True) -> List[Dict]:
        """
        Busca documentos similares
        
        Args:
            query: Consulta del usuario
            n_results: Número de resultados
            only_active: Si True, solo busca en documentos activos
        """
        try:
            start_time = time.time()
            
            if n_results is None:
                n_results = settings.TOP_K_RESULTS
            
            if not query.strip():
                raise ValueError("Query vacío")
            
            logger.debug("Searching in vector store", 
                        query_length=len(query),
                        n_results=n_results,
                        only_active=only_active)
            
            # Generar embedding de la consulta
            embedding_service = get_embedding_service()
            query_embedding = await embedding_service.embed_text(query)
            
            # Construir filtro
            where_filter = {"status": "active"} if only_active else None
            
            # Buscar en ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self.collection.count()),
                where=where_filter
            )
            
            # Formatear resultados
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        "text": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "distance": results['distances'][0][i],
                        "similarity": 1 - results['distances'][0][i]  # Convertir distancia a similitud
                    })
            
            duration = time.time() - start_time
            
            logger.info("Vector search completed", 
                       query_length=len(query),
                       results_found=len(formatted_results),
                       duration=f"{duration:.2f}s")
            
            return formatted_results
            
        except Exception as e:
            logger.error("Error searching in vector store", 
                        query_length=len(query) if query else 0,
                        error=str(e))
            raise
    
    def delete_by_source(self, filename: str) -> Dict:
        """Elimina documentos por nombre de archivo"""
        try:
            logger.info("Deleting documents by source", source=filename)
            
            # Obtener documentos existentes para contar
            existing_docs = self.collection.get(
                where={"source": filename}
            )
            
            deleted_count = len(existing_docs['ids']) if existing_docs['ids'] else 0
            
            if deleted_count > 0:
                # Eliminar documentos
                self.collection.delete(
                    where={"source": filename}
                )
                
                logger.info("Documents deleted", 
                           source=filename,
                           deleted_count=deleted_count,
                           remaining_in_collection=self.collection.count())
            else:
                logger.info("No documents found to delete", source=filename)
            
            return {
                "deleted": deleted_count,
                "source": filename,
                "collection_size": self.collection.count()
            }
            
        except Exception as e:
            logger.error("Error deleting documents", 
                        source=filename,
                        error=str(e))
            raise
    
    def update_document_status(self, doc_id: str, new_status: str):
        """Actualiza el estado de un documento en ChromaDB"""
        try:
            # Obtener todos los chunks del documento
            results = self.collection.get(
                where={"doc_id": doc_id}
            )
            
            if not results['ids']:
                logger.warning("No chunks found for document", doc_id=doc_id)
                return
            
            # Actualizar metadata de cada chunk
            for i, chunk_id in enumerate(results['ids']):
                # Obtener metadata actual
                current_metadata = results['metadatas'][i]
                # Actualizar status
                current_metadata['status'] = new_status
                
                self.collection.update(
                    ids=[chunk_id],
                    metadatas=[current_metadata]
                )
            
            logger.info("Document status updated", 
                       doc_id=doc_id, 
                       new_status=new_status,
                       chunks_updated=len(results['ids']))
                       
        except Exception as e:
            logger.error("Error updating document status", 
                        doc_id=doc_id, 
                        new_status=new_status,
                        error=str(e))
            raise

    def get_document_content(self, filename: str) -> Dict:
        """Reconstruye el texto completo de un documento desde sus chunks en Chroma.

        Sirve para el viewer del backoffice: une los chunks en orden (chunk_index) sin
        depender de que el archivo siga en disco. Funciona igual para PDF, Markdown y texto
        pegado (todos se guardan como chunks con la misma metadata).
        """
        try:
            results = self.collection.get(where={"source": filename})
            docs = results.get("documents") or []
            metas = results.get("metadatas") or []
            if not docs:
                return {"filename": filename, "content": "", "chunks": 0, "status": None}
            # Ordenar por chunk_index para reconstruir el orden original del documento.
            pairs = sorted(
                zip(docs, metas),
                key=lambda p: (p[1] or {}).get("chunk_index", 0),
            )
            content = "\n\n".join(text for text, _ in pairs if text)
            status = (metas[0] or {}).get("status", "active") if metas else "active"
            return {
                "filename": filename,
                "content": content,
                "chunks": len(docs),
                "status": status,
            }
        except Exception as e:
            logger.error("Error getting document content", source=filename, error=str(e))
            return {"filename": filename, "content": "", "chunks": 0, "status": None}

    def get_all_sources_with_status(self) -> List[Dict]:
        """Obtiene lista de documentos con su estado"""
        try:
            results = self.collection.get()
            
            # Agrupar por source y obtener estado
            sources = {}
            for metadata in results['metadatas']:
                source = metadata['source']
                if source not in sources:
                    sources[source] = {
                        "filename": source,
                        "status": metadata.get('status', 'active'),
                        "uploaded_at": metadata.get('uploaded_at', 'unknown')
                    }
            
            return list(sources.values())
            
        except Exception as e:
            logger.error("Error getting sources with status", error=str(e))
            return []

    def get_all_sources(self) -> List[str]:
        """Obtiene lista de todos los documentos cargados"""
        try:
            results = self.collection.get()
            sources = set()
            
            if results['metadatas']:
                for metadata in results['metadatas']:
                    if 'source' in metadata:
                        sources.add(metadata['source'])
            
            source_list = sorted(list(sources))
            
            logger.debug("Retrieved all sources", 
                        sources_count=len(source_list))
            
            return source_list
            
        except Exception as e:
            logger.error("Error getting all sources", error=str(e))
            return []
    
    def get_collection_stats(self) -> Dict:
        """Obtiene estadísticas de la colección"""
        try:
            count = self.collection.count()
            sources = self.get_all_sources()
            
            stats = {
                "total_documents": count,
                "unique_sources": len(sources),
                "sources": sources,
                "collection_name": self.collection_name,
                "persist_directory": settings.CHROMA_PERSIST_DIRECTORY
            }
            
            logger.debug("Collection stats retrieved", **stats)
            
            return stats
            
        except Exception as e:
            logger.error("Error getting collection stats", error=str(e))
            return {"error": str(e)}
    
    def health_check(self) -> tuple[bool, str]:
        """Verifica el estado de salud del vector store"""
        try:
            count = self.collection.count()
            return True, f"Vector store healthy. Documents: {count}"
        except Exception as e:
            return False, f"Vector store error: {str(e)}"

# Instancia global del vector store (conocimiento de HUÉSPEDES / Aura)
vector_store = None

def get_vector_store() -> VectorStoreService:
    """Obtiene la instancia del vector store de huéspedes (colección por defecto)."""
    global vector_store
    if vector_store is None:
        vector_store = VectorStoreService()
    return vector_store


# Colección SEPARADA para el conocimiento de gerencia (libros de gestión, revenue, etc.).
MANAGEMENT_COLLECTION = "management_knowledge"
_management_vector_store = None

def get_management_vector_store() -> VectorStoreService:
    """Vector store del conocimiento de CONSULTORÍA (agente de gerencia), aislado del de Aura."""
    global _management_vector_store
    if _management_vector_store is None:
        _management_vector_store = VectorStoreService(collection_name=MANAGEMENT_COLLECTION)
    return _management_vector_store
