from typing import List, Dict, Optional
from app.services.vector_store import get_vector_store
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.retry_config import vector_store_retry
from app.core.circuit_breaker import vector_store_circuit_breaker
from app.config import settings
import time

logger = get_logger(__name__)

class RAGService:
    def __init__(self):
        self.vector_store = get_vector_store()
        logger.info("RAG service initialized")
    
    @vector_store_retry
    async def retrieve_context(self, query: str, n_results: int = None, 
                              only_active: bool = True, conversation_history: list = None) -> str:
        """
        Recupera contexto relevante SOLO de documentos activos.

        Devuelve un STRING: el contexto formateado, o la sentinela "NO_CONTEXT_FOUND".
        Es la variante simple (sin fuentes). El agente NO la usa: el path de producción
        usa retrieve_context_with_sources() (devuelve dict con context + sources).
        Esta versión queda para scripts/auditoría que solo necesitan el texto.

        Args:
            query: Consulta del usuario
            n_results: Número de resultados
            only_active: Si True, solo busca en docs activos (default)
            conversation_history: Historial de conversación para contexto (NUEVO)

        Returns:
            str: contexto formateado, o "NO_CONTEXT_FOUND" si no hay match relevante.
        """
        try:
            start_time = time.time()
            
            if not query.strip():
                logger.warning("Empty query provided to RAG service")
                return "NO_CONTEXT_FOUND"
            
            logger.info("Starting context retrieval", 
                       query_length=len(query),
                       n_results=n_results or settings.TOP_K_RESULTS,
                       has_history=bool(conversation_history))
            
            # 1. Enriquecer query con historial conversacional
            query_with_history = query
            if conversation_history and len(conversation_history) > 0:
                # Extraer últimas queries del usuario (últimos 4 mensajes del usuario)
                recent_user_messages = [
                    msg["content"] for msg in conversation_history[-8:]
                    if msg.get("role") == "user"
                ]
                
                if recent_user_messages:
                    # Tomar las últimas 2 queries del usuario (además de la actual)
                    previous_queries = recent_user_messages[-2:]
                    
                    # Combinar: dar más peso a la query actual poniéndola primero
                    query_with_history = f"{query} {' '.join(previous_queries)}"
                    
                    logger.info("Query enriched with conversation history",
                               current_query=query[:50],
                               previous_queries_count=len(previous_queries),
                               combined_length=len(query_with_history))
            
            # 2. Buscar en vector store (SOLO ACTIVOS por default). Sin enriquecimiento
            # geográfico: la KB del hotel no tiene metadata de países y search() trabaja
            # con el texto crudo de la query.
            results = await vector_store_circuit_breaker.acall(
                self.vector_store.search,
                query_with_history,
                n_results,
                only_active
            )
            
            # 3. Verificar si hay resultados
            if not results:
                logger.info("No context found for query", query_length=len(query))
                return "NO_CONTEXT_FOUND"
            
            # 3.5. Deduplicar resultados por documento (mantener el más relevante por doc_id)
            deduplicated_results = self._deduplicate_by_document(results)
            
            logger.debug("Results deduplicated", 
                        original_count=len(results),
                        deduplicated_count=len(deduplicated_results))
            
            # 4. Formatear contexto con información de relevancia
            context_parts = []
            total_similarity = 0
            
            for i, result in enumerate(deduplicated_results, 1):
                similarity = result.get('similarity', 0)
                total_similarity += similarity
                
                # Solo incluir resultados con similitud razonable (>0.25)
                if similarity > 0.25:
                    source = result['metadata'].get('source', 'Unknown')
                    context_parts.append(
                        f"[Fuente {i} - {source} (Relevancia: {similarity:.2f})]\n{result['text']}\n"
                    )
            
            if not context_parts:
                logger.info("No relevant context found", 
                           results_count=len(deduplicated_results),
                           avg_similarity=total_similarity/len(deduplicated_results) if deduplicated_results else 0)
                return "NO_CONTEXT_FOUND"
            
            context = "\n---\n".join(context_parts)
            
            duration = time.time() - start_time
            
            logger.info("Context retrieval completed",
                       results_found=len(context_parts),
                       context_length=len(context),
                       avg_similarity=total_similarity/len(deduplicated_results),
                       duration=f"{duration:.2f}s")
            
            return context
            
        except Exception as e:
            logger.error("Error retrieving context", 
                        query_length=len(query) if query else 0,
                        error=str(e))
            raise
    
    async def retrieve_context_with_sources(self, query: str, n_results: int = None, 
                                           only_active: bool = True, conversation_history: list = None) -> Dict:
        """
        Recupera contexto relevante CON información de fuentes para tracking.

        Es la variante de PRODUCCIÓN (la que usa el agente vía agent_tools). A
        diferencia de retrieve_context() —que devuelve un string— ésta devuelve un
        dict con context + sources + relevance_mode. La sentinela "NO_CONTEXT_FOUND"
        viaja dentro del campo 'context' del dict (no como string suelto).

        Args:
            query: Consulta del usuario
            n_results: Número de resultados
            only_active: Si True, solo busca en docs activos (default)
            conversation_history: Historial de conversación para contexto (NUEVO)

        Returns:
            Dict con 'context' (str | "NO_CONTEXT_FOUND"), 'sources' (lista de
            documentos consultados) y 'relevance_mode' (high/medium/low | None).
        """
        try:
            start_time = time.time()
            
            if not query.strip():
                logger.warning("Empty query provided to RAG service")
                return {"context": "NO_CONTEXT_FOUND", "sources": []}
            
            logger.info("Starting context retrieval with sources", 
                       query_length=len(query),
                       has_history=bool(conversation_history))
            
            # 1. Enriquecer query con historial conversacional
            query_with_history = query
            if conversation_history and len(conversation_history) > 0:
                # Extraer últimas queries del usuario
                recent_user_messages = [
                    msg["content"] for msg in conversation_history[-8:]
                    if msg.get("role") == "user"
                ]
                
                if recent_user_messages:
                    # Tomar las últimas 2 queries del usuario
                    previous_queries = recent_user_messages[-2:]
                    
                    # Combinar: dar más peso a la query actual
                    query_with_history = f"{query} {' '.join(previous_queries)}"
                    
                    logger.info("Query enriched with conversation history (with_sources)",
                               current_query=query[:50],
                               previous_queries_count=len(previous_queries))
            
            # 2. Buscar en el vector store con la query (enriquecida con el historial).
            # Sin geografía: la KB del hotel no tiene metadata de países y search() trabaja
            # con el texto crudo. La similitud del embedding ordena bien una KB chica y curada.
            results = await vector_store_circuit_breaker.acall(
                self.vector_store.search,
                query_with_history,
                n_results,
                only_active
            )

            # 3. Sin resultados → sentinela.
            if not results:
                logger.info("No context found for query")
                return {"context": "NO_CONTEXT_FOUND", "sources": []}

            # 4. Deduplicar por documento.
            deduplicated_results = self._deduplicate_by_document(results)

            # 5. Umbral de similitud (permisivo: KB curada, confiamos en el embedding).
            SIMILARITY_THRESHOLD = 0.25
            max_similarity = max((r.get('similarity', 0) for r in deduplicated_results), default=0)
            if max_similarity < SIMILARITY_THRESHOLD:
                logger.info("Context found but similarity too low",
                           max_similarity=max_similarity, threshold=SIMILARITY_THRESHOLD,
                           returning="NO_CONTEXT_FOUND")
                return {"context": "NO_CONTEXT_FOUND", "sources": []}

            # 6. Fuentes (para tracking) + contexto formateado.
            document_sources = []
            seen_sources = set()
            context_parts = []
            for i, result in enumerate(deduplicated_results, 1):
                source = result['metadata'].get('source', 'Unknown')
                similarity = result.get('similarity', 0)
                if source not in seen_sources:
                    document_sources.append({"document": source, "similarity": similarity})
                    seen_sources.add(source)
                if similarity > 0.25:
                    header = f"[Fuente {i} - {source} (Relevancia: {similarity:.2f})]\n"
                    context_parts.append(f"{header}{result['text']}\n")

            context = "\n---\n".join(context_parts) if context_parts else "NO_CONTEXT_FOUND"
            duration = time.time() - start_time
            logger.info("Context retrieved with sources",
                       sources_count=len(document_sources),
                       context_length=len(context),
                       duration=f"{duration:.2f}s")
            return {"context": context, "sources": document_sources}

        except Exception as e:
            logger.error("Error retrieving context with sources", error=str(e))
            return {"context": "NO_CONTEXT_FOUND", "sources": []}

    def format_no_context_response(self, geo_analysis: Dict = None) -> Dict:
        """Respuesta cuando no hay contexto. Stub neutro (sin geografía de turismo):
        devuelve el mensaje genérico del perfil. Se conserva por compatibilidad con el
        state-machine de eventos (inactivo en el hotel) y el test de smoke."""
        return {
            "response": profile_manager.get_no_info_response(),
            "mode": "no_context_generic",
            "is_final": True,
        }

    async def get_available_destinations(self) -> Dict:
        """Resumen del contenido del vector store. Stub sin geografía: el endpoint
        /destinations (residuo de turismo) sigue respondiendo con los stats de la KB."""
        try:
            stats = self.vector_store.get_collection_stats()
            return {
                "documents_loaded": stats.get("total_documents", 0),
                "sources": stats.get("sources", []),
            }
        except Exception as e:
            logger.error("Error getting available destinations", error=str(e))
            return {"error": str(e)}

    def get_service_health(self) -> Dict:
        """Obtiene estado de salud del servicio RAG"""
        try:
            # Vector store health
            vs_healthy, vs_msg = self.vector_store.health_check()
            
            # Circuit breaker states
            vs_cb_state = vector_store_circuit_breaker.get_state()
            
            return {
                "status": "healthy" if vs_healthy else "unhealthy",
                "vector_store": {
                    "healthy": vs_healthy,
                    "message": vs_msg,
                    "circuit_breaker": vs_cb_state
                }
            }
            
        except Exception as e:
            logger.error("Error checking RAG service health", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
    
    # Cuántos chunks como máximo conservar por documento. >1 para que un documento
    # multi-sección (ej. un calendario con una fecha por provincia) devuelva la sección
    # que matchea la consulta y no solo su encabezado. Acotado para no inundar el contexto
    # con casi-duplicados de un mismo doc.
    MAX_CHUNKS_PER_DOC = 3

    def _deduplicate_by_document(self, results: List[Dict]) -> List[Dict]:
        """
        Acota la cantidad de chunks por documento conservando los más relevantes.

        Para documentos cortos (un tema = un chunk) el comportamiento es el de siempre:
        se conserva ese chunk. Para documentos LARGOS multi-sección (ej. un calendario
        con una fecha por provincia), conservar solo el mejor chunk descarta justo la
        sección que responde la pregunta (quedaba el encabezado genérico). Por eso
        mantenemos hasta `MAX_CHUNKS_PER_DOC` chunks por documento, ordenados por
        similitud, en lugar de uno solo.

        Args:
            results: Lista de resultados de búsqueda vectorial

        Returns:
            Lista acotada por documento, conservando los chunks más relevantes.
        """
        try:
            if not results:
                return results

            # Agrupar resultados por doc_id
            docs_groups = {}
            for result in results:
                doc_id = result['metadata'].get('doc_id', 'unknown')
                source = result['metadata'].get('source', 'unknown')

                # Usar source como fallback si no hay doc_id
                key = doc_id if doc_id != 'unknown' else source

                if key not in docs_groups:
                    docs_groups[key] = []
                docs_groups[key].append(result)

            # Procesar cada documento
            deduplicated = []
            removed_count = 0

            for doc_key, doc_results in docs_groups.items():
                if len(doc_results) == 1:
                    # Solo un chunk, mantenerlo
                    deduplicated.append(doc_results[0])
                    continue

                # Conservar los chunks más relevantes del documento (hasta el tope), para
                # que un doc multi-sección no quede reducido a su encabezado.
                ranked = sorted(doc_results, key=lambda x: x.get('similarity', 0), reverse=True)
                kept = ranked[: self.MAX_CHUNKS_PER_DOC]
                deduplicated.extend(kept)
                removed_count += len(doc_results) - len(kept)

                logger.debug("Document deduplicated",
                           source=kept[0]['metadata'].get('source'),
                           total_chunks=len(doc_results),
                           kept_chunks=len(kept),
                           top_similarity=f"{kept[0].get('similarity', 0):.3f}")
            
            # Ordenar por similitud descendente para mantener el orden de relevancia
            deduplicated.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            if removed_count > 0:
                logger.info("Deduplication completed",
                           original_count=len(results),
                           deduplicated_count=len(deduplicated),
                           removed_duplicates=removed_count)
            
            return deduplicated
            
        except Exception as e:
            logger.error("Error deduplicating results", error=str(e))
            # En caso de error, retornar resultados originales
            return results

# Instancia global del servicio RAG
rag_service = RAGService()
