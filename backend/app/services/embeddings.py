from langchain_openai import OpenAIEmbeddings
from typing import List, Optional
from collections import OrderedDict
import hashlib
from app.config import settings
from app.core.logging_config import get_logger
import asyncio
import time

logger = get_logger(__name__)

# Tamaño del caché LRU de embeddings de queries. Las consultas se repiten mucho
# ("paquetes a Japón", "playa", etc.); cachear evita re-embeber y reduce costo/latencia.
_EMBED_CACHE_MAX = 512

class EmbeddingService:
    def __init__(self):
        try:
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_EMBEDDING_MODEL
            )
            # Caché LRU simple {hash(text) -> embedding}. OrderedDict para evicción FIFO/LRU.
            self._cache: "OrderedDict[str, List[float]]" = OrderedDict()
            logger.info("Embedding service initialized",
                       model=settings.OPENAI_EMBEDDING_MODEL)
        except Exception as e:
            logger.error("Error initializing embedding service", error=str(e))
            raise

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def embed_text(self, text: str) -> List[float]:
        """Genera embedding para un texto (con caché LRU por hash)."""
        try:
            start_time = time.time()

            if not text.strip():
                raise ValueError("Texto vacío para generar embedding")

            # Cache hit: devolver sin llamar a OpenAI
            key = self._cache_key(text)
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)  # marcar como recién usado (LRU)
                logger.info("Embedding cache hit", text_length=len(text))
                return cached

            logger.debug("Generating embedding",
                        text_length=len(text))

            # Usar el método asíncrono
            embedding = await self.embeddings.aembed_query(text)

            duration = time.time() - start_time

            # Guardar en caché y evictar el más viejo si excede el límite
            self._cache[key] = embedding
            self._cache.move_to_end(key)
            if len(self._cache) > _EMBED_CACHE_MAX:
                self._cache.popitem(last=False)

            logger.info("Embedding generated",
                       text_length=len(text),
                       embedding_dimensions=len(embedding),
                       duration=f"{duration:.2f}s")

            return embedding

        except Exception as e:
            logger.error("Error generating embedding",
                        text_length=len(text) if text else 0,
                        error=str(e))
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings para múltiples documentos"""
        try:
            start_time = time.time()
            
            if not texts:
                raise ValueError("Lista de textos vacía")
            
            # Filtrar textos vacíos
            valid_texts = [text for text in texts if text.strip()]
            
            if not valid_texts:
                raise ValueError("Todos los textos están vacíos")
            
            logger.info("Generating embeddings for documents", 
                       total_documents=len(valid_texts),
                       total_characters=sum(len(text) for text in valid_texts))
            
            # Usar el método asíncrono para múltiples documentos
            embeddings = await self.embeddings.aembed_documents(valid_texts)
            
            duration = time.time() - start_time
            
            logger.info("Embeddings generated", 
                       documents_processed=len(embeddings),
                       duration=f"{duration:.2f}s",
                       avg_time_per_doc=f"{duration/len(embeddings):.2f}s")
            
            return embeddings
            
        except Exception as e:
            logger.error("Error generating embeddings for documents", 
                        documents_count=len(texts) if texts else 0,
                        error=str(e))
            raise
    
    def embed_text_sync(self, text: str) -> List[float]:
        """Versión síncrona para generar embedding de un texto"""
        try:
            return asyncio.run(self.embed_text(text))
        except Exception as e:
            logger.error("Error in sync embedding", error=str(e))
            raise
    
    def embed_documents_sync(self, texts: List[str]) -> List[List[float]]:
        """Versión síncrona para generar embeddings de múltiples textos"""
        try:
            return asyncio.run(self.embed_documents(texts))
        except Exception as e:
            logger.error("Error in sync embeddings", error=str(e))
            raise
    
    async def test_connection(self) -> tuple[bool, str]:
        """Prueba la conexión con OpenAI"""
        try:
            test_text = "test connection"
            embedding = await self.embed_text(test_text)
            
            if embedding and len(embedding) > 0:
                logger.info("OpenAI connection test successful", 
                           embedding_dimensions=len(embedding))
                return True, f"Conexión exitosa. Dimensiones: {len(embedding)}"
            else:
                return False, "Embedding vacío recibido"
                
        except Exception as e:
            logger.error("OpenAI connection test failed", error=str(e))
            return False, f"Error de conexión: {str(e)}"

# Instancia global del servicio (se inicializará cuando se importe)
embedding_service = None

def get_embedding_service() -> EmbeddingService:
    """Obtiene la instancia del servicio de embeddings"""
    global embedding_service
    if embedding_service is None:
        embedding_service = EmbeddingService()
    return embedding_service
