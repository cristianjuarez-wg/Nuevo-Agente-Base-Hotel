from typing import List, Dict, Optional
from app.services.vector_store import get_vector_store
from app.core.geography import geography_service
from app.core.intelligent_geography import intelligent_extractor
from app.core.agent_profile import profile_manager
from app.core.logging_config import get_logger
from app.core.retry_config import vector_store_retry
from app.core.circuit_breaker import vector_store_circuit_breaker
from app.config import settings
import time

# 🆕 FASE 2: Importar servicio de interpretación semántica
from app.services.semantic_query_enhancer import semantic_enhancer

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
            
            # 2. Enriquecer consulta con información geográfica
            enriched_query = geography_service.enrich_query(query_with_history)
            
            logger.debug("Query enriched", 
                        original_length=len(query),
                        enriched_length=len(enriched_query))
            
            # 2. Buscar en vector store (SOLO ACTIVOS por default)
            results = await vector_store_circuit_breaker.acall(
                self.vector_store.search,
                enriched_query,
                n_results,
                only_active  # ← NUEVO PARÁMETRO
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
            
            # 🆕 2. INTERPRETACIÓN SEMÁNTICA (Fase 2)
            # Detectar si es consulta geográfica obvia
            geo_analysis_pre = geography_service.get_geographic_analysis(query)
            geo_entities = intelligent_extractor.extract_all_geographic_entities(query, "")
            
            is_obvious_geographic = (
                geo_analysis_pre.get('continent') is not None or 
                len(geo_analysis_pre.get('countries', [])) > 0 or
                len(geo_entities.get('countries', [])) > 0 or
                len(geo_entities.get('special_regions', [])) > 0
            )
            
            # Variable para tracking
            used_semantic_interpretation = False
            semantic_interpretation = None
            
            if not is_obvious_geographic:
                # NO es consulta geográfica obvia → Usar interpretación semántica
                logger.info("Query is not obviously geographic, using semantic interpretation",
                           query=query[:50])
                
                try:
                    # Interpretar con GPT
                    semantic_interpretation = await semantic_enhancer.interpret_query(query)
                    
                    # Solo usar si la confianza es razonable
                    if semantic_interpretation.get('confianza', 0) >= 0.3:
                        # Construir query enriquecido semánticamente
                        semantically_enriched = semantic_enhancer.build_enriched_query(
                            query_with_history, semantic_interpretation
                        )
                        
                        # Aplicar también enriquecimiento geográfico por si detecta algo
                        enriched_query = intelligent_extractor.enrich_query(semantically_enriched)
                        used_semantic_interpretation = True
                        
                        logger.info("Semantic interpretation applied",
                                   temas=semantic_interpretation.get('temas'),
                                   tipo_destino=semantic_interpretation.get('tipo_destino'),
                                   confianza=semantic_interpretation.get('confianza'))
                    else:
                        # Confianza baja, usar solo enriquecimiento geográfico
                        enriched_query = intelligent_extractor.enrich_query(query_with_history)
                        logger.info("Semantic interpretation confidence too low, using geographic only",
                                   confianza=semantic_interpretation.get('confianza'))
                        
                except Exception as e:
                    logger.error("Error in semantic interpretation, falling back to geographic",
                                error=str(e))
                    enriched_query = intelligent_extractor.enrich_query(query_with_history)
            else:
                # Es consulta geográfica obvia → Usar solo enriquecimiento geográfico
                enriched_query = intelligent_extractor.enrich_query(query_with_history)
                logger.info("Using geographic enrichment only",
                           is_obvious_geographic=is_obvious_geographic)
            
            # 🆕 2.5. PORTERO: Verificar si país mencionado está disponible (ANTES de buscar)
            # Solo para queries geográficas obvias que mencionan países específicos
            if is_obvious_geographic:
                countries_mentioned = geo_analysis_pre.get('countries', [])
                
                if countries_mentioned:
                    # Obtener países realmente disponibles en el sistema
                    available_countries = self.vector_store.get_available_countries()
                    
                    # Verificar si TODOS los países mencionados NO están disponibles
                    all_unavailable = all(
                        country not in available_countries 
                        for country in countries_mentioned
                    )
                    
                    if all_unavailable:
                        # INTERCEPTAR: No tiene sentido buscar en ChromaDB
                        # Ir directo a NO_CONTEXT_FOUND para que use format_no_context_response()
                        logger.info("Query for unavailable countries only - skipping ChromaDB search",
                                   countries_mentioned=countries_mentioned,
                                   available_countries_count=len(available_countries))
                        
                        return {
                            "context": "NO_CONTEXT_FOUND",
                            "sources": [],
                            "relevance_mode": None
                        }
                    else:
                        # Al menos un país SÍ está disponible → continuar búsqueda normal
                        available_mentioned = [c for c in countries_mentioned if c in available_countries]
                        logger.info("Query includes available countries - continuing search",
                                   available_countries=available_mentioned,
                                   total_mentioned=len(countries_mentioned))
            
            # 2. Buscar en vector store
            results = await vector_store_circuit_breaker.acall(
                self.vector_store.search,
                enriched_query,
                n_results,
                only_active
            )
            
            # 3. Verificar resultados
            if not results:
                logger.info("No context found for query")
                return {"context": "NO_CONTEXT_FOUND", "sources": []}
            
            # 4. Deduplicar
            deduplicated_results = self._deduplicate_by_document(results)
            
            # 🆕 4.5. Verificar umbral de similitud (LÓGICA HÍBRIDA)
            # Para consultas geográficas con países disponibles, confiar en el enriquecimiento
            geo_analysis = geography_service.get_geographic_analysis(query)
            is_geographic_query = (
                geo_analysis.get('continent') is not None or
                len(geo_analysis.get('countries', [])) > 0 or
                len(geo_analysis.get('cities', [])) > 0  # 🆕 ciudades (París, Roma, Tokio) también son geográficas
            )
            
            # Verificar si hay países disponibles en el sistema
            available_countries = self.vector_store.get_available_countries()
            has_available_countries = len(available_countries) > 0
            
            # 🆕 LÓGICA HÍBRIDA MEJORADA (Fase 2):
            # - Consulta geográfica + países disponibles → Sin umbral (confiar en enriquecimiento)
            # - Consulta semántica con interpretación → Umbral bajo (0.25)
            # - Otras consultas → Umbral normal (0.4)
            if is_geographic_query and has_available_countries:
                # No aplicar umbral para consultas geográficas
                # El enriquecimiento ya garantiza relevancia
                SIMILARITY_THRESHOLD = 0.0
                logger.info("Geographic query with available countries - no threshold applied",
                           continent=geo_analysis.get('continent'),
                           countries=geo_analysis.get('countries'),
                           available_countries_count=len(available_countries))
            elif used_semantic_interpretation and semantic_interpretation:
                # Consulta semántica → umbral más bajo porque GPT ya filtró
                SIMILARITY_THRESHOLD = 0.25
                logger.info("Semantic query - lower threshold applied",
                           threshold=SIMILARITY_THRESHOLD,
                           confianza=semantic_interpretation.get('confianza'))
            else:
                # Umbral normal para consultas no geográficas sin interpretación
                SIMILARITY_THRESHOLD = 0.4
            
            max_similarity = max([r.get('similarity', 0) for r in deduplicated_results]) if deduplicated_results else 0
            
            if max_similarity < SIMILARITY_THRESHOLD:
                logger.info("Context found but similarity too low",
                           max_similarity=max_similarity,
                           threshold=SIMILARITY_THRESHOLD,
                           is_geographic=is_geographic_query,
                           has_available_countries=has_available_countries,
                           returning="NO_CONTEXT_FOUND")
                return {"context": "NO_CONTEXT_FOUND", "sources": []}
            
            # 🆕 4.7. VERIFICAR RELEVANCIA con GPT (Fase 2 - solo para queries semánticas)
            # Sistema de 3 niveles: HIGH (>=0.7), MEDIUM (0.4-0.7), LOW (<0.4)
            relevance_mode = None
            
            if used_semantic_interpretation and deduplicated_results and len(deduplicated_results) >= 1:
                logger.info("Verifying semantic relevance of results with GPT",
                           query=query[:50],
                           results_count=len(deduplicated_results))
                
                verification_tasks = []
                
                # Verificar solo los top 3 resultados para no gastar muchos tokens
                top_results = deduplicated_results[:3]
                
                for result in top_results:
                    destination_name = result['metadata'].get('source', 'Unknown')
                    destination_context = result['text']
                    
                    # Llamar a verificación de relevancia
                    verification_tasks.append(
                        semantic_enhancer.verify_relevance(query, destination_context, destination_name)
                    )
                
                # Ejecutar verificaciones en paralelo
                try:
                    import asyncio
                    verification_results = await asyncio.gather(*verification_tasks, return_exceptions=True)
                    
                    # Agregar scores de relevancia a los resultados
                    for idx, verification in enumerate(verification_results):
                        if isinstance(verification, dict):
                            relevance_score = verification.get('score', 0.5)
                            top_results[idx]['semantic_relevance'] = relevance_score
                            top_results[idx]['relevance_reason'] = verification.get('razon', '')
                    
                    # 🆕 CLASIFICAR EN 3 NIVELES
                    high_relevance = [r for r in top_results if r.get('semantic_relevance', 0) >= 0.7]
                    medium_relevance = [r for r in top_results if 0.4 <= r.get('semantic_relevance', 0) < 0.7]
                    low_relevance = [r for r in top_results if r.get('semantic_relevance', 0) < 0.4]
                    
                    if high_relevance:
                        # ALTA RELEVANCIA: Ofrecer directamente
                        deduplicated_results = high_relevance + deduplicated_results[3:]
                        relevance_mode = "high"
                        logger.info("High relevance results found",
                                   count=len(high_relevance),
                                   scores=[r.get('semantic_relevance') for r in high_relevance])
                    
                    elif medium_relevance:
                        # RELEVANCIA MEDIA: Ofrecer como alternativa relacionada
                        deduplicated_results = medium_relevance + deduplicated_results[3:]
                        relevance_mode = "medium"
                        logger.info("Medium relevance results found - offer as alternatives",
                                   count=len(medium_relevance),
                                   scores=[r.get('semantic_relevance') for r in medium_relevance])
                    
                    else:
                        # BAJA RELEVANCIA: Decir que no tiene nada relacionado
                        relevance_mode = "low"
                        logger.warning("Low relevance results - no suitable alternatives",
                                     query=query[:50],
                                     max_score=max([r.get('semantic_relevance', 0) for r in top_results]))
                        # Mantener resultados pero marcar como baja relevancia
                        deduplicated_results = top_results + deduplicated_results[3:]
                        
                except Exception as e:
                    logger.error("Error in semantic verification, continuing with original results",
                                error=str(e))
                    relevance_mode = None
            
            # 5. Extraer fuentes de documentos
            document_sources = []
            seen_sources = set()
            
            for result in deduplicated_results:
                source = result['metadata'].get('source', 'Unknown')
                if source not in seen_sources:
                    document_sources.append({
                        "document": source,
                        "similarity": result.get('similarity', 0)
                    })
                    seen_sources.add(source)
            
            # 6. Formatear contexto con información de paquetes multi-país
            context_parts = []
            total_similarity = 0
            
            for i, result in enumerate(deduplicated_results, 1):
                similarity = result.get('similarity', 0)
                total_similarity += similarity
                
                if similarity > 0.25:
                    source = result['metadata'].get('source', 'Unknown')
                    
                    # 🆕 Extraer nombre del paquete del source (sin extensión)
                    package_name = source.replace('.pdf', '').replace('.PDF', '').replace('_', ' ')
                    
                    # 🆕 Detectar si es paquete multi-país
                    countries_str = result['metadata'].get('countries', '')
                    is_multi_country = ',' in countries_str
                    
                    # 🆕 Formatear header con énfasis en paquetes multi-país
                    if is_multi_country:
                        countries_list = [c.strip().title() for c in countries_str.split(',')]
                        # Crear nombre completo del paquete a partir de los países
                        full_package_name = f"{' y '.join(countries_list)}"
                        
                        header = f"[Fuente {i} - 📦 PAQUETE MULTI-PAÍS]\n"
                        header += f"🎫 NOMBRE COMPLETO: {full_package_name}\n"
                        header += f"🌍 Países incluidos: {full_package_name}\n"
                        header += f"(Relevancia: {similarity:.2f})\n"
                        header += f"\n⚠️ IMPORTANTE: Este paquete incluye TODOS estos países: {full_package_name}\n"
                        header += f"Cuando menciones este paquete, usa el nombre completo: '{full_package_name}'\n\n"
                    else:
                        header = f"[Fuente {i} - {source} (Relevancia: {similarity:.2f})]\n"
                    
                    context_parts.append(f"{header}{result['text']}\n")
            
            context = "\n---\n".join(context_parts) if context_parts else "NO_CONTEXT_FOUND"
            
            duration = time.time() - start_time
            
            logger.info("Context retrieved with sources",
                       sources_count=len(document_sources),
                       context_length=len(context),
                       relevance_mode=relevance_mode,
                       duration=f"{duration:.2f}s")
            
            return {
                "context": context,
                "sources": document_sources,
                "relevance_mode": relevance_mode  # 🆕 Pasar modo de relevancia al agente
            }
            
        except Exception as e:
            logger.error("Error retrieving context with sources", error=str(e))
            return {"context": "NO_CONTEXT_FOUND", "sources": []}
    
    def analyze_query_geography(self, query: str) -> Dict:
        """Analiza componentes geográficos de la consulta"""
        try:
            logger.debug("Analyzing query geography", query_length=len(query))
            
            # Usar el análisis geográfico completo
            analysis = geography_service.get_geographic_analysis(query)
            
            # Agregar información adicional para el contexto
            continent = analysis.get('continent')
            countries = analysis.get('countries', [])
            
            enhanced_analysis = {
                "continent": continent,
                "countries": countries,
                "cities": analysis.get('cities', []),
                "requires_mapping": continent is not None,
                "enriched_query": analysis.get('enriched_query', query)
            }
            
            # Si menciona continente pero no países específicos, sugerir países
            if continent and not countries:
                suggested_countries = geography_service.get_countries_by_continent(continent)
                enhanced_analysis["suggested_countries"] = suggested_countries[:10]  # Limitar a 10
                
                logger.info("Geographic analysis with suggestions",
                           continent=continent,
                           suggested_count=len(suggested_countries))
            
            # Si menciona países, agregar información del continente y sugerir alternativas
            if countries:
                continents_mentioned = []
                for country in countries:
                    cont = geography_service.get_continent_by_country(country)
                    if cont and cont not in continents_mentioned:
                        continents_mentioned.append(cont)
                
                enhanced_analysis["continents_mentioned"] = continents_mentioned
                
                # Si el país mencionado tiene un continente, sugerir otros países del mismo continente
                if continents_mentioned:
                    # Usar el primer continente detectado
                    main_continent = continents_mentioned[0]
                    suggested_countries = geography_service.get_countries_by_continent(main_continent)
                    enhanced_analysis["suggested_countries"] = suggested_countries
                    # También agregar el continente al análisis principal
                    if not enhanced_analysis["continent"]:
                        enhanced_analysis["continent"] = main_continent
            
            logger.debug("Geographic analysis completed", **enhanced_analysis)
            
            return enhanced_analysis
            
        except Exception as e:
            logger.error("Error analyzing query geography", 
                        query_length=len(query) if query else 0,
                        error=str(e))
            return {
                "continent": None,
                "countries": [],
                "cities": [],
                "requires_mapping": False,
                "error": str(e)
            }
    
    def format_no_context_response(self, geo_analysis: Dict) -> str:
        """Formatea respuesta cuando no hay contexto disponible"""
        base_response = profile_manager.get_no_info_response()
        
        continent = geo_analysis.get("continent")
        countries = geo_analysis.get("countries", [])
        suggested_countries = geo_analysis.get("suggested_countries", [])
        
        # 🆕 Obtener países que realmente tienen documentación
        available_countries = self.vector_store.get_available_countries()
        
        logger.info("Formatting no context response",
                   continent=continent,
                   countries_mentioned=countries,
                   suggested_count=len(suggested_countries),
                   available_count=len(available_countries))
        
        # CASO 1: Preguntó por país específico
        if countries:
            country_name = countries[0]  # Primer país mencionado
            
            # Buscar países alternativos del mismo continente que tengan documentación
            if continent and suggested_countries:
                valid_suggestions = [
                    c for c in suggested_countries 
                    if c in available_countries and c != country_name
                ]
                
                if valid_suggestions:
                    # 🆕 SOLUCIÓN HÍBRIDA: Construir lista en formato bullet (sin ciudades)
                    countries_list = "\n".join([f"• {c.title()}" for c in valid_suggestions[:5]])
                    
                    # Construir respuesta final completa (no modificable por GPT)
                    alternatives_section = f"\n\nSin embargo, tengo excelentes opciones en {continent}:\n{countries_list}"
                    alternatives_section += "\n\n¿Te gustaría conocer más sobre alguno de estos destinos?"
                    
                    final_response = base_response + alternatives_section
                    
                    logger.info("Suggested alternative countries (hybrid solution)",
                               original_country=country_name,
                               alternatives=valid_suggestions[:5],
                               mode="no_context_with_alternatives")
                    
                    # 🆕 Retornar dict con respuesta final y metadata
                    return {
                        "response": final_response,
                        "mode": "no_context_with_alternatives",
                        "countries_list": valid_suggestions[:5],
                        "continent": continent,
                        "is_final": True  # Indica que NO debe ser modificada por GPT
                    }
                else:
                    # No hay países del continente con documentación
                    logger.info("No alternatives available",
                               continent=continent,
                               country=country_name)
                    return {
                        "response": f"Por el momento no contamos con paquetes para {country_name.title()}. ¿Te gustaría explorar destinos en Europa, Asia u Oceanía? ¡Tenemos opciones increíbles!",
                        "mode": "no_context_no_alternatives",
                        "is_final": True
                    }
            else:
                # No sabemos el continente — mencionar el país igualmente
                return {
                    "response": f"Por el momento no tengo información sobre paquetes para {country_name.title()}. ¿Te gustaría que te muestre otros destinos disponibles?",
                    "mode": "no_context_unknown",
                    "is_final": True
                }

        # CASO 2: Preguntó por continente (sin país específico)
        elif continent and suggested_countries:
            valid_suggestions = [
                c for c in suggested_countries
                if c in available_countries
            ]

            if valid_suggestions:
                countries_list = "\n".join([f"• {c.title()}" for c in valid_suggestions[:5]])
                if len(valid_suggestions) > 5:
                    countries_list += f"\n• Y {len(valid_suggestions) - 5} destinos más"

                alternatives_section = f"\n\nOperamos en {continent}. Tenemos destinos disponibles en:\n{countries_list}"
                alternatives_section += "\n\n¿Te gustaría información sobre alguno de estos países específicos?"

                final_response = base_response + alternatives_section

                logger.info("Suggested countries for continent (hybrid solution)",
                           continent=continent,
                           suggestions=valid_suggestions[:5],
                           mode="no_context_with_alternatives")

                return {
                    "response": final_response,
                    "mode": "no_context_with_alternatives",
                    "countries_list": valid_suggestions[:5],
                    "continent": continent,
                    "is_final": True
                }
            else:
                # No hay países del continente con documentación
                logger.info("No countries available for continent",
                           continent=continent)
                return {
                    "response": f"Por el momento no contamos con paquetes para {continent}. ¿Te gustaría explorar otros destinos? ¡Tenemos opciones en Europa, Asia, América y más!",
                    "mode": "no_context_no_alternatives",
                    "is_final": True
                }

        return {
            "response": base_response,
            "mode": "no_context_generic",
            "is_final": True
        }
    
    async def get_available_destinations(self) -> Dict:
        """Obtiene resumen de destinos disponibles en el sistema"""
        try:
            # Obtener estadísticas del vector store
            stats = self.vector_store.get_collection_stats()
            
            # Información geográfica disponible
            all_continents = geography_service.get_all_continents()
            all_countries = geography_service.get_all_countries()
            
            return {
                "documents_loaded": stats.get("total_documents", 0),
                "sources": stats.get("sources", []),
                "continents_available": all_continents,
                "countries_available": len(all_countries),
                "sample_countries": all_countries[:20]  # Muestra de países
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
                },
                "geography_service": {
                    "continents": len(geography_service.get_all_continents()),
                    "countries": len(geography_service.get_all_countries())
                }
            }
            
        except Exception as e:
            logger.error("Error checking RAG service health", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _deduplicate_by_document(self, results: List[Dict]) -> List[Dict]:
        """
        Deduplicación inteligente que respeta paquetes multi-país.
        
        Para documentos con múltiples países:
        - Mantiene al menos 1 chunk representativo por país mencionado
        - Asegura que GPT reciba información completa del paquete
        
        Para documentos de un solo país:
        - Mantiene solo el chunk más relevante (lógica original)
        
        Args:
            results: Lista de resultados de búsqueda vectorial
            
        Returns:
            Lista deduplicada con representación completa de paquetes multi-país
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
                
                # Verificar si es paquete multi-país
                countries_str = doc_results[0]['metadata'].get('countries', '')
                
                if ',' in countries_str:
                    # 🆕 PAQUETE MULTI-PAÍS: Mantener chunks representativos de cada país
                    countries_list = [c.strip() for c in countries_str.split(',')]
                    
                    # Agrupar chunks por país mencionado en el texto
                    chunks_by_country = {country: [] for country in countries_list}
                    chunks_general = []
                    
                    for chunk in doc_results:
                        chunk_text_lower = chunk['text'].lower()
                        assigned = False
                        
                        # Asignar chunk al país que menciona
                        for country in countries_list:
                            if country.lower() in chunk_text_lower:
                                chunks_by_country[country].append(chunk)
                                assigned = True
                                break
                        
                        if not assigned:
                            # Chunk general (intro, precios, etc.)
                            chunks_general.append(chunk)
                    
                    # Seleccionar mejor chunk por país
                    selected_chunks = []
                    for country, chunks in chunks_by_country.items():
                        if chunks:
                            best_chunk = max(chunks, key=lambda x: x.get('similarity', 0))
                            selected_chunks.append(best_chunk)
                            logger.debug("Country chunk selected",
                                       country=country,
                                       chunk_index=best_chunk['metadata'].get('chunk_index'),
                                       similarity=f"{best_chunk.get('similarity', 0):.3f}")
                    
                    # Agregar 1 chunk general si existe (intro o info general del paquete)
                    if chunks_general:
                        best_general = max(chunks_general, key=lambda x: x.get('similarity', 0))
                        selected_chunks.append(best_general)
                        logger.debug("General chunk selected",
                                   chunk_index=best_general['metadata'].get('chunk_index'),
                                   similarity=f"{best_general.get('similarity', 0):.3f}")
                    
                    deduplicated.extend(selected_chunks)
                    removed_count += len(doc_results) - len(selected_chunks)
                    
                    logger.info("Multi-country package processed",
                               source=doc_results[0]['metadata'].get('source'),
                               countries=countries_list,
                               total_chunks=len(doc_results),
                               selected_chunks=len(selected_chunks),
                               chunks_per_country={c: len(chunks_by_country[c]) for c in countries_list})
                else:
                    # PAQUETE SINGLE-PAÍS: Lógica original
                    best_result = max(doc_results, key=lambda x: x.get('similarity', 0))
                    deduplicated.append(best_result)
                    removed_count += len(doc_results) - 1
                    
                    logger.debug("Single-country document deduplicated",
                               source=best_result['metadata'].get('source'),
                               total_chunks=len(doc_results),
                               selected_chunk=best_result['metadata'].get('chunk_index'),
                               selected_similarity=f"{best_result.get('similarity', 0):.3f}")
            
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
