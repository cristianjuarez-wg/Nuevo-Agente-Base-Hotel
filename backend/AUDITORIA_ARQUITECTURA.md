# Auditoría Arquitectónica — Demo Freeway Turismo
**Fecha:** Junio 2026  
**Revisado por:** Claude (sesión de auditoría profunda)  
**Alcance:** Diseño del agente, RAG/datos de viajes, post-venta, estructura e higiene

---

## Resumen ejecutivo

El proyecto es un agente conversacional de turismo construido en noviembre 2025 sobre FastAPI + GPT-4o + ChromaDB. Tiene una base sólida: el RAG está bien diseñado, el logging es estructurado, hay circuit breaker y retry implementados, y el modelo de datos cubre el ciclo completo pre-venta → post-venta. En esta auditoría se identificaron **14 hallazgos** distribuidos en 4 ejes. Se aplicaron **6 fixes de código** de alto impacto / bajo riesgo. El resto queda documentado como backlog priorizado.

### Puntuación por eje

| Eje | Puntuación | Estado |
|-----|-----------|--------|
| Diseño del agente | 6/10 | Funcional, con deuda técnica relevante |
| RAG y datos de viajes | 8/10 | Bien diseñado, optimizaciones menores |
| Post-venta | 7/10 | Robusto, acoplamiento mejorable |
| Estructura e higiene | 5/10 | Mejorado en esta sesión, falta Alembic y cobertura |

---

## Hallazgos detallados

### Eje 1 — Diseño del agente (`app/services/agent_service.py`)

#### H1 — Historial conversacional no sobrevivía reinicios del servidor 🔴 CORREGIDO
**Archivo:** `agent_service.py` — `_get_or_create_history()`  
**Problema:** El historial se almacenaba únicamente en memoria (`self.conversation_history[session_id]`). Al reiniciar el servidor, el contexto de todas las sesiones activas se perdía. El usuario preguntaba "¿y cuánto sale ese paquete?" y el agente no recordaba el destino discutido momentos antes — si el proceso había sido reiniciado.  
**Fix aplicado:** En cache-miss, la función ahora consulta la tabla `ConversationMessage` (que ya se persistía correctamente), reconstruye la lista de mensajes ordenados por `sequence_number` y los carga en memoria. Límite de 40 mensajes para no sobrecargar el contexto.  
**Resultado:** El agente mantiene contexto conversacional entre reinicios del servidor.

#### H2 — Modelos LLM hardcodeados, `gpt-3.5-turbo` deprecado 🔴 CORREGIDO
**Archivos:** `agent_service.py` (×5), `rating_service.py` (×3), `summary_service.py` (×1)  
**Problema:** `gpt-3.5-turbo` era el modelo en uso para clasificación post-venta, calificaciones de tickets y resúmenes. Este modelo está en proceso de deprecación por OpenAI. Adicionalmente, `gpt-4o-mini` estaba hardcodeado en 4 métodos de `agent_service`, lo que impedía cambiar el modelo de clasificación sin tocar el código.  
**Fix aplicado:** Se añadieron dos settings en `config.py`:
- `OPENAI_MODEL_CLASSIFIER = "gpt-4o-mini"` — para clasificaciones de intención
- `OPENAI_MODEL_FAST = "gpt-4o-mini"` — reemplaza `gpt-3.5-turbo` en tareas auxiliares

Todos los hardcodes en los 3 servicios fueron reemplazados por `settings.OPENAI_MODEL_CLASSIFIER` o `settings.OPENAI_MODEL_FAST` según corresponda. El modelo ahora es configurable desde `.env`.

#### H3 — 3-4 llamadas LLM por mensaje de usuario 🟠 BACKLOG
**Archivo:** `agent_service.py` — flujo principal `chat()`  
**Problema:** Cada mensaje del usuario puede disparar hasta 4 llamadas LLM en secuencia:
1. `_detect_postsale_context()` — ¿es post-venta?
2. `_is_casual_conversation()` — ¿es charla casual?
3. `_classify_message_intent()` — ¿qué tipo de consulta?
4. `_call_openai()` — la respuesta final

Esto multiplica latencia (cada llamada agrega ~500-1500ms) y costo. El 80% de los mensajes son consultas directas de viajes donde las 3 primeras clasificaciones son innecesarias.  
**Recomendación:** Unificar las 3 clasificaciones en una sola llamada GPT-4o-mini con output JSON estructurado (`{"is_postsale": bool, "is_casual": bool, "intent": "...}`). Reducción esperada: 60-70% en latencia de clasificación.  
**Prioridad:** P1 para producción con usuarios reales.

#### H4 — Clasificador de intención duplicado sin uso 🟡 BACKLOG
**Archivos:** `app/services/intent_classifier.py` (438 líneas) vs. clasificación LLM en `agent_service.py`  
**Problema:** Existe un clasificador híbrido sofisticado (dataset + regex + GPT) que **no se usa** en el flujo conversacional principal. `agent_service.py` reimplementa su propia clasificación vía LLM. Dos sistemas paralelos a mantener.  
**Recomendación:** Una vez resuelto H3 (clasificación unificada), evaluar si `intent_classifier.py` se integra formalmente o se retira. No tocar hasta resolver H3.

#### H5 — Estado multi-paso solo en memoria 🟠 BACKLOG
**Archivo:** `app/services/conversation_state_manager.py`  
**Problema:** El estado de captura de datos (flujo nombre → teléfono) vive únicamente en memoria. Un reinicio en medio de la captura pierde el progreso. A diferencia del historial (H1), este estado no tiene tabla de persistencia.  
**Recomendación:** Agregar tabla `ConversationState` (session_id, state_name, data_json, updated_at) y persistir/recuperar el estado al igual que el historial en H1. Bajo riesgo, mediano esfuerzo.

---

### Eje 2 — RAG y datos de viajes (`app/services/rag_service.py`)

El RAG está **bien diseñado** para un MVP. Los puntos fuertes son: chunking sensato (1000/200), embeddings `text-embedding-3-small`, deduplicación inteligente para paquetes multi-país, umbral de relevancia dinámico (high/medium/low), extracción de metadata vía LLM (no hardcodeada), y manejo de "no encontrado" con sugerencias de alternativas. Los hallazgos son optimizaciones, no defectos.

#### H6 — Verificación de relevancia GPT sin caché 🟡 BACKLOG
**Archivo:** `rag_service.py` — verificación top-3 resultados  
**Problema:** Para queries sin contexto geográfico claro, el servicio hace una llamada GPT adicional para verificar relevancia. Sin caché, preguntas similares repiten el trabajo.  
**Recomendación:** Caché LRU en memoria (TTL 10 minutos) con la query normalizada como clave. Para MVP con volumen bajo, impacto menor.

#### H7 — Sin caché de interpretación semántica 🟡 BACKLOG
**Archivo:** `rag_service.py` + `semantic_query_enhancer.py`  
**Problema:** Cada mensaje re-ejecuta búsqueda vectorial y, en queries ambiguas, una llamada GPT de interpretación semántica. Preguntas idénticas = trabajo duplicado.  
**Recomendación:** Mismo patrón que H6 — caché con TTL corto. Bajo esfuerzo de implementación.

---

### Eje 3 — Post-venta (`app/services/postsale_service.py`)

#### H8 — `AgentProfileManager` instanciado por request 🟠 CORREGIDO
**Archivo:** `agent_service.py` líneas 739-742 (antes del fix)  
**Problema:** En cada mensaje detectado como post-venta, se creaba un nuevo `AgentProfileManager()` y se llamaba `switch_profile()`, cargando el archivo JSON desde disco y parseándolo nuevamente. Con tráfico concurrente esto suma I/O innecesario.  
**Fix aplicado:** Se inicializa `self._postsale_profile_manager` en `AgentService.__init__()` — una sola vez al arrancar el servidor. El import inline fue eliminado.

#### H9 — Lógica de clasificación fragmentada en post-venta 🟡 BACKLOG
**Archivo:** `postsale_service.py` — `classify_intent()` + `escalation_analyzer` + `can_auto_resolve()`  
**Problema:** Tres fuentes de clasificación coexisten: keywords hardcodeadas, análisis GPT de escalación, y `can_auto_resolve()` (marcado como deprecated). Dificulta el mantenimiento y puede generar clasificaciones contradictorias.  
**Recomendación:** Consolidar en un único clasificador de intención post-venta con output estructurado. Involucra refactor del flujo principal de post-venta — alcance mediano.

#### H10 — `lead_id` sin Foreign Key en `SoldPackage` 🟡 DOCUMENTADO
**Archivo:** `app/models/postsale.py:97` — `lead_id = Column(Integer, nullable=True)`  
**Estado:** Comentario en el código dice "sin FK por ahora". Decisión consciente para flexibilidad, pero implica que pueden existir `SoldPackage` con `lead_id` apuntando a leads inexistentes.  
**Recomendación:** Verificar integridad de datos existentes, luego agregar FK con `nullable=True` para mantener la flexibilidad sin perder integridad referencial.

#### H11 — PostSaleSession sin cleanup de inactivas 🟡 CORREGIDO
**Archivo:** `postsale_service.py`  
**Problema:** Las sesiones de post-venta se marcaban como activas indefinidamente. Acumulación en BD sin expiración.  
**Fix aplicado:** Se agregó `cleanup_inactive_sessions(days=7)` que marca `is_active=False` en sesiones sin `last_interaction` en el período indicado. Disponible para llamar desde un endpoint admin o cron job.

---

### Eje 4 — Estructura e higiene

#### H12 — 294 scripts ad-hoc en la raíz del backend 🔴 CORREGIDO
**Directorio:** `backend/` (raíz)  
**Problema:** 294 archivos `.py` sueltos (scripts de seed, debug, análisis, migrations one-off, tests manuales) convivían con el código de la app. Dificultaban encontrar qué es código de producción vs. utilidades descartables. El proyecto parecía más grande y complejo de lo que es.  
**Fix aplicado:** Todos movidos a `backend/scripts_archive/`. No se eliminó ninguno — están disponibles si se necesitan. La raíz ahora contiene solo lo que la app necesita para correr.

#### H13 — Sin testing real ni configuración de pytest 🔴 CORREGIDO
**Estado previo:** No existía `pytest.ini`, `conftest.py` ni suites pytest. Los `test_*.py` de la raíz eran scripts manuales, no tests automáticos.  
**Fix aplicado:**
- `backend/pytest.ini` — configuración mínima (testpaths, asyncio_mode)
- `backend/tests/conftest.py` — fixtures de BD en memoria y TestClient de FastAPI
- `backend/tests/test_smoke.py` — 5 smoke tests cubriendo: greeting endpoint, validación de entrada, no-duplicación de respuestas, método cleanup

**Resultado:** `python -m pytest` → **5/5 passed** desde cero.  
**Nota:** Los warnings de Pydantic V1 son deprecation warnings del código existente (no del test bootstrap) — documentados en H14.

#### H14 — Warnings de compatibilidad Pydantic V2 🟡 BACKLOG
**Archivo:** `app/models/schemas.py` — uso de `@validator` (V1 style)  
**Problema:** Tres validadores usan la API de Pydantic V1 (`@validator`). Funcionan correctamente hoy, pero serán removidos en Pydantic V3. Generan warnings en cada ejecución de tests.  
**Recomendación:** Migrar a `@field_validator` (Pydantic V2). Cambio mecánico, bajo riesgo.

#### H15 — Sin migraciones Alembic 🟠 BACKLOG
**Estado:** El schema evoluciona mediante scripts manuales (los `migrate_*.py` ahora archivados). Los modelos tienen comentarios `🆕` para marcar campos nuevos.  
**Riesgo:** Cualquier cambio de schema en producción requiere ejecutar scripts manualmente sin rollback automatizado.  
**Recomendación:** Inicializar Alembic con un baseline del schema actual, luego usar `alembic revision --autogenerate` para cambios futuros. **Requiere validación cuidadosa** antes de ejecutar en una BD con datos de demo — no implementar sin backup.

---

## Resumen de fixes aplicados en esta sesión

| Fix | Archivo(s) | Impacto |
|-----|-----------|---------|
| B1 — Rehidratar historial desde BD | `agent_service.py` | 🔴 Alta — contexto persiste entre reinicios |
| B2 — Parametrizar modelos + reemplazar `gpt-3.5-turbo` | `agent_service.py`, `rating_service.py`, `summary_service.py`, `config.py` | 🔴 Alta — elimina modelo deprecado, hace configurables los modelos |
| B3 — Cachear `postsale_profile_manager` | `agent_service.py` | 🟠 Media — reduce I/O por request post-venta |
| B4 — `cleanup_inactive_sessions()` | `postsale_service.py` | 🟡 Media — previene acumulación en BD |
| B5 — Archivar 294 scripts raíz | `backend/scripts_archive/` | 🔴 Alta — higiene, claridad del proyecto |
| B6 — Bootstrap de testing | `pytest.ini`, `tests/conftest.py`, `tests/test_smoke.py` | 🔴 Alta — base para cobertura futura |

**También aplicados en sesiones previas (esta auditoría):**
- Fix fluidez conversacional: regex fallback en clasificación, bypass social phrases, detección farewell mid-conversation
- Fix doble mensaje Cuba: `format_no_context_response` devuelve `is_final=True` en todos los paths
- Rules 9 y 10 en `turismo.json`: manejo de presupuesto + estilo prosa conversacional

---

## Backlog priorizado

| Prioridad | Hallazgo | Esfuerzo | Riesgo |
|-----------|---------|---------|--------|
| P1 | H3 — Fusionar 3-4 LLM calls en una (latencia) | Alto | Medio |
| P1 | H15 — Alembic (migraciones) | Medio | Alto (requiere backup) |
| P2 | H5 — Persistir estado multi-paso | Medio | Bajo |
| P2 | H14 — Migrar `@validator` → `@field_validator` | Bajo | Bajo |
| P3 | H10 — FK `lead_id` en `SoldPackage` | Bajo | Bajo |
| P3 | H4 — Unificar/retirar `intent_classifier.py` | Medio | Bajo |
| P3 | H6/H7 — Caché RAG (LRU, TTL corto) | Bajo | Bajo |
| P4 | H9 — Unificar clasificación post-venta | Alto | Medio |

---

## Buenas prácticas ya presentes (puntos fuertes)

- **Circuit breaker + tenacity retry** (`app/core/circuit_breaker.py`, `retry_config.py`) — protección ante fallos de OpenAI
- **Logging estructurado** con structlog (JSON en prod, console en dev) — observable desde el arranque
- **Pydantic v2 Settings** con `.env` — configuración centralizada y validada
- **RAG bien diseñado** — chunking, deduplicación multi-país, umbral dinámico, extracción de metadata por LLM
- **Perfil del agente externalizado** en JSON — prompt configurable sin tocar código
- **Prompts externalizados** en `app/prompts/` — separación de concerns entre lógica y contenido
- **Modelo de datos completo** — `Conversation`, `ConversationMessage`, `Lead`, `SoldPackage`, `SupportTicket`, `TicketInteraction`, `PostSaleSession` cubren el ciclo completo
- **Post-venta robusto** — manejo de tickets, escalación, vouchers, análisis de severidad
