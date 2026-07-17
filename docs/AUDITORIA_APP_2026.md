# Auditoría integral de la aplicación — Estructura, arquitectura y modelo de agentes

**Fecha:** julio 2026
**Alcance:** backend (`backend/`), landing (`landing/`), despliegue (`render.yaml`, `start.sh`), con foco en el modelo de agentes (definición, tools, flujos) y readiness para pre-producción.
**Método:** revisión estática del código con verificación de cada hallazgo en `archivo:línea`. Los documentos vivos del equipo (`backend/DEUDA_TECNICA.md`, `backend/AUDITORIA_ARQUITECTURA.md`, `backend/AGENT_REUSE.md`, `backend/RUNBOOK_ALEMBIC.md`) fueron tenidos en cuenta y se referencian donde siguen vigentes.

---

## 1. Resumen ejecutivo

**Veredicto:** la arquitectura del modelo de agentes está **bien encaminada y por encima del promedio** de una app en su etapa — diseño declarativo de agentes (`AgentSpec` + runtime único + tool registry), convergencia de canales en un solo punto de entrada, routing con clasificador liviano, cortocircuitos determinísticos, y una suite de tests real (282/290 verdes). Sin embargo, **no está lista para pre-producción** por **3 hallazgos críticos de seguridad** (secreto JWT en default, backoffice mayormente sin autenticación, webhook de Instagram sin validación de firma) y varios altos. Todos son de esfuerzo bajo/medio y están detallados en el roadmap (§7).

### Semáforo por dimensión

| Dimensión | Estado | Comentario |
|---|---|---|
| Diseño del modelo de agentes | 🟢 | Declarativo, con runtime único y registry; migración a completar |
| Routing / triage | 🟢 | Clasificador liviano temp 0 + fallback conservador + atajos 0-LLM |
| Diseño de tools | 🟢/🟡 | Muy buena deduplicación pre/post; validación defensiva; 1 agujero de privacidad |
| RAG / conocimiento | 🟢/🟡 | Fail-closed con retry + circuit breaker; scripts de ingesta rotos |
| Prompts | 🟢/🟡 | Composición por bloques sólida; composers del registry muertos |
| Seguridad | 🔴 | 3 críticos que bloquean pre-producción |
| Persistencia / esquema | 🟠 | Dos sistemas de migración; stamp de Alembic pendiente en Render |
| Concurrencia / escala | 🟡 | Correcto para 1 instancia / 1 worker; sin escalado horizontal |
| Observabilidad | 🟡 | Buen logging + audit; sin trazas LLM en prod ni evals en CI |
| Testing / evals | 🟢 | 282 tests verdes + evals con LLM-as-judge (manuales) |

---

## 2. Arquitectura y estructura

### 2.1 Mapa de capas

```
HTTP/WS (routers/) ──► services/ + domains/hotel/services/ ──► domains/hotel + core/ ──► models/ (SQLAlchemy)
```

- `backend/app/main.py` — FastAPI, lifespan con seeds idempotentes, ~30 routers, CORS, rate limit (slowapi), static `/vouchers` y `/media`.
- `routers/` (~30) — HTTP: entrada de mensajes (`chat.py`, `whatsapp.py`, `instagram.py`) y backoffice (bandeja en vivo, leads, kanban, tickets, reservas, etc.).
- `services/` (~45) — lógica de aplicación; piezas centrales: `agent_service.py`, `hotel_sdk_orchestrator.py`, `triage_sdk_orchestrator.py`, `hotel_postsale*.py`, `owner_orchestrator.py`, `staff_orchestrator.py`.
- `core/` — framework transversal reutilizable: `agents/` (spec + runtime + registry), `llm/` (cliente OpenAI singleton + circuit breaker), `rag/` (ChromaDB), `channels/` (WhatsApp/Instagram/WS), `security/`, `observability/`.
- `domains/hotel/` — el vertical: `agent_specs.py`, `agent_router.py`, `prompts/` (10 módulos de bloques), `services/`, `seeds/`.
- `models/` — SQLAlchemy: SQLite local / PostgreSQL en Render (`models/database.py:35-49`).

### 2.2 Tenancy

**Instancia-por-cliente, no multi-tenant** — decisión explícita y documentada (`docs/ARQUITECTURA_TENANCY.md`): cada hotel tiene deploy + DB + Chroma propios; no hay `tenant_id` en ningún modelo ni query. Es una decisión correcta para el stage actual (aislamiento total, operación simple vía `docs/RUNBOOK_NUEVA_INSTANCIA.md`), con la consecuencia de que el escalado comercial es "1 deploy por cliente".

### 2.3 Fortalezas estructurales

- **Convergencia de canales:** los 3 canales (web, WhatsApp, Instagram) desembocan en un único `agent_service.chat(db, message, session_id)` (`services/agent_service.py:528`). Los webhooks son delgados (validan firma donde aplica, responden 200, procesan en background).
- **Serialización por sesión:** lock `asyncio` por `session_id` (`agent_service.py:217-243`) que evita turnos concurrentes descolgados.
- **Gates determinísticos en el camino caliente:** control humano (HITL), freno de gasto (`usage_service.is_budget_exceeded`), gate de canal, gate de acceso post-venta — todos antes de gastar tokens.
- **Timeout duro de 60s** en el turno del agente en los 3 canales, con background tasks que loguean excepciones (`routers/whatsapp.py:376-384`).

### 2.4 Debilidades estructurales

1. **Dios-router `routers/chat.py` (~1100 líneas):** ~450 líneas de lógica de negocio determinística (heurísticas de intención con regex, construcción de cards, acceso directo a modelos) que pertenece a services/domains (`chat.py:102-398`, `679-782`).
2. **Canal derivado del prefijo de `session_id` en ≥6 lugares** (`agent_service.py:351`, `conversation_control_service.py:99`, `agent_service.py:509`, `conversations.py:32,85`, `guest_context_service.py:36`, `lead_service.py`, `casual_agent`). Falta un helper central `channel_from_session()`. Ya produjo inconsistencia: Instagram usa prefijo `ig_` en algunos puntos pero `agent_directory.session_prefixes_for_role` no lo incluye para guest.
3. **4 caches en RAM con reglas propias:** historial guest (`agent_service.conversation_history`), historiales owner/staff (`agent_router._role_histories`), `_control_cache` de takeover, `ws_hub`. Rehidratación desde DB mitiga reinicios, pero obliga a single-instance y pierde estado multi-paso en redeploys (deuda H5 ya documentada).
4. **Cross-imports entre routers:** `instagram.py:125` importa `to_whatsapp_text` de `routers/whatsapp.py`; `conversations.py:279` importa `_clear_agent_ram_cache` de `routers/contacts.py`; `whatsapp.py:115` importa el privado `checkin._get_booking_by_session`.
5. **Dos sistemas de migración conviviendo:** Alembic (preparado, no aplicado en Render) + `run_light_migrations()` con ~50 `ensure_column` (`models/database.py:77-154`).
6. **Residuos del dominio anterior (turismo/paquetes) en el camino caliente:** fix de "nombres de paquetes truncados" con regex de países (`chat.py:623-667`), métricas `travel_agent_*` (`main.py:412`, `chat.py:849-886`), `Conversation.destinations_mentioned/packages_viewed`, `notification_service.py` simulado, `core/rag/pdf_processor.py` con metadata de países/vuelos y stubs muertos (`vector_store.get_available_countries`).
7. **`extra_metadata` JSON como mecanismo universal de estado** (takeover, needs_human, availability_shown, ig_username): requiere reasignar el dict a mano para que SQLAlchemy persista — patrón frágil repetido en varios puntos.
8. **Mezcla de datetimes aware/naive:** `_save_message_to_db` usa `datetime.now(timezone.utc)` para `last_message_at` (`agent_service.py:398`) mientras el resto del modelo usa `utcnow_naive()`.
9. **Directorios/paquetes fantasma:** `domains/hotel/orchestrators/` y `domains/hotel/tools/` (solo `__init__.py` vacíos), `app/prompts/__init__.py` vacío, `chroma_db_postsale/` sin referencias, `routers/alerts.py` sin montar.

---

## 3. Modelo de agentes

### 3.1 Stack

- **OpenAI Agents SDK 0.17.5** (`openai==2.43.0`); langchain/langgraph podados explícitamente. Uso de `Agent`, `Runner.run`, `@function_tool`, `@input_guardrail`, `ModelSettings`, con cliente async singleton (`core/llm/openai_client.py`).
- Modelos por settings: `OPENAI_MODEL` (agentes principales), `OPENAI_MODEL_CLASSIFIER` (triage y clasificadores, gpt-4o-mini), temperatura por spec.
- **Sin streaming** (`Runner.run`, no `run_streamed`) — la UX espera respuesta completa hasta 60s.

### 3.2 Definición declarativa: `AgentSpec` + runtime único + registry

`core/agents/` implementa el patrón correcto de **configuración declarativa de agentes**:

- `agent_spec.py:17-37` — `AgentSpec` (dataclass frozen): key, engine (`sdk|completions`), model_setting por indirección, temperatura, `max_turns`, `max_history`, tools por key, guardrails, canales, flags.
- `sdk_runtime.py:42` — `run_agent()`: **un solo loop de ejecución** para todos los agentes SDK. Devuelve contrato común `{response, tools_used, usage, agent_key, error}`. Filtrado de tools por sesión vía `tools_override` (skills del backoffice).
- `tool_registry.py` — registro global tools/composers/guardrails, resolución por key fail-fast.

Catálogo (`domains/hotel/agent_specs.py:16-123`): `hotel_staff`, `hotel_owner`, `hotel_postsale`, `hotel_presale`, `casual` (completions), `triage` (declarado, no corre por el runtime).

La **identidad** (nombre, rol, canal, reportes) vive en DB (tabla `agents`, `models/agent.py`) para backoffice/métricas; el **comportamiento** vive 100% en código. Separación razonable.

### 3.3 Routing

**Nivel 0 — por rol** (`domains/hotel/services/agent_router.py:38`): el teléfono resuelve rol → owner/staff/guest, cada uno con su orquestador y su política de memoria.

**Nivel 1 — dentro de guest** (`agent_service._chat_impl`):

1. **Cortocircuitos determinísticos 0-LLM** (`agent_service.py:591-630`): validación de ticket, acuse `MESA-XXXX`, código `HTL-XXXX`, ticket abierto, reserva reciente, despedida → casual. *Buena práctica de costo/latencia.*
2. **Triage SDK** (`triage_sdk_orchestrator.py:149-223`): agente clasificador con **handoffs a agentes-marcador**; la ruta se lee de `result.last_agent.name`. Modelo chico, temp 0, `max_turns=3`, historial 6, **fallback conservador a preventa** ante error. *Alineado con la práctica de mercado de clasificador liviano dedicado.*
3. Casual → completion directo; post-venta → gate de acceso + orquestador; preventa → orquestador SDK.

### 3.4 Contexto y estado

- Triple capa de historial: RAM por sesión (50 msgs / 24h) → rehidratación desde DB → ventana de la spec al modelo (8-20 msgs según rol).
- **Context objects por turno** (`HotelContext`, `HotelPostventaContext`, `StaffContext`, `OwnerContext`): patrón uniforme que recolecta outputs de tools (cards, sources, booking_code) por side-channel, con contrato `Protocol HotelToolCtx` (`hotel_tools_pkg/agent_tools.py:27-41`) para tools compartidas. *Buen patrón.*
- Estado conversacional extra en `Conversation.extra_metadata` y en tickets (`pre_resuelto` → validación por el huésped).

### 3.5 Prompts

- Composición por **bloques con placeholders**: plantilla maestra `TOOL_AGENT_SYSTEM` (`domains/hotel/prompts/tool_agent_prompts.py:51`) + bloques compartidos (`base_blocks.py`: honestidad, anti-inyección, datos bancarios, alergias, límite de dominio, multi-intent) + identidad desde `BusinessProfile` (`identity_blocks.py`) + contexto (`context_blocks.py`) + naturalidad (`generation_prompts.py`, solo customer-facing).
- El **entrenamiento del cliente sustituye** tono/política con fallback logueado a defaults (`hotel_sdk_orchestrator.py:693-702`).
- Versionado de config de prompts en DB (`prompt_config_version_service.py`).
- Bug conocido: ejemplos con voseo en `NATURALIDAD_BLOCK` pisan la instrucción de dialecto para clientes no rioplatenses (ya en `DEUDA_TECNICA.md`).

### 3.6 Guardrails y handoffs

- **Input guardrail anti-jailbreak por substring** (`_JAILBREAK_MARKERS`, duplicado en `hotel_sdk_orchestrator.py:429-450` y `hotel_postsale_orchestrator.py:444-462`): frágil (evadible, falsos positivos con "actúa como").
- **Guardrails determinísticos fuera del SDK** (los más efectivos): validación XSS/SQL, freno de gasto, gates de canal/HITL/acceso, anti-inyección en docs RAG (`wrap_untrusted_docs`, con test), reglas anti-alucinación en prompts (precios solo de tools).
- **Handoff a humano:** tool `derivar_a_humano` + `human_attention_service` (live vs deferred por horario) + **backstop determinístico** si el LLM no llamó la tool (`hotel_postsale_orchestrator.py:639-680`) — excelente patrón de defensa en profundidad.
- Entre agentes de dominio no hay handoffs del SDK: el routing es procedural (decisión válida; ver §3.7).

### 3.7 Desviaciones del propio diseño (deuda del modelo de agentes)

1. **Composers muertos:** `AgentSpec.prompt_composer` y `register_composer/resolve_composer` (`tool_registry.py:54-62`) **nunca se usan**; los prompts se arman con `_build_instructions` ad-hoc reimplementado 4 veces. La abstracción quedó a mitad de camino.
2. **Specs huérfanas:** `triage` y `casual` figuran en el catálogo pero no corren por el runtime; el triage duplica su propio loop fuera del sistema de specs.
3. **Constantes y helpers muertos** en orquestadores (admitido en comentarios, ej. `hotel_sdk_orchestrator.py:66-70`); `set_default_openai_client`/tracing repetidos en 4 módulos.
4. **Hardcoding del hotel** en respuestas de guardrail ("Hampton by Hilton Bariloche", `hotel_sdk_orchestrator.py:750`, `hotel_postsale_orchestrator.py:619`), saludos (`chat.py:51-55`), defaults en staff/owner — en tensión con el `BusinessProfile` multi-instancia.
5. **El cerebro procedural:** `agent_service._chat_impl` (952 líneas) + los backstops del router concentran de facto buena parte de la lógica de decisión. Funciona y está testeado, pero es el punto de mayor acoplamiento.
6. **Atribución sesión→agente por prefijo de `session_id`** (`agent_directory.py:86-94`), sin FK — frágil ante canales nuevos (ya ocurrió con `ig_`).

---

## 4. Tools y RAG

### 4.1 Arquitectura de tools

Tres capas bien separadas:

1. **Wrappers `@function_tool`** — lo que ve el LLM (`hotel_sdk_orchestrator.py:154-418`, 17 tools pre-venta; `hotel_postsale_orchestrator.py:131-433`, 13 post-venta). El docstring es el contrato; el SDK deriva el schema de los type hints.
2. **Dispatcher** `execute_tool()` → `_DISPATCH` (`hotel_tools_pkg/__init__.py:42-82`) → handlers por dominio (`info/booking/promos/restaurant/misc` + `_shared`).
3. **Registro declarativo** por key (`presale.*` / `postsale.*`) referenciado desde las specs, con resolución fail-fast.

**Deduplicación pre/post (Fase 6):** tools idénticas declaradas una sola vez en `agent_tools.py` bajo `Protocol HotelToolCtx`; las divergentes comparten cuerpo (`derivar_a_humano_body`, `reservar_mesa_body`). Documentado como fix de "bugs reincidentes" — buena lección aplicada.

### 4.2 Validación, errores y side effects

**Fortalezas:**

- Validación manual defensiva en handlers: fechas ISO con errores amables (`booking.py:32-42`), blindaje de rangos >30 noches contra errores del LLM, teléfono auto-completado desde `wa_`, normalización de hora a slots reales sin inventar turnos (`_shared.py:282-310`).
- **El dinero no lo toca el LLM:** `crear_reserva` revalida la promo server-side (`reservation_service.py:308-319`); `registrar_pedido` solo confirma pedidos creados por UI.
- Handlers chequean `db is None`; postsale envuelve todo con fallback amable.
- `info_pago` (CBU) es **determinístico** a propósito (`booking.py:290-296`).
- RAG fail-closed ante excepciones + retry + circuit breaker (`rag_service.py:131-233`, `vector_store_retry`).

**Hallazgos:**

| # | Hallazgo | Ubicación | Severidad |
|---|---|---|---|
| T1 | `consultar_reserva` sin verificación de identidad: cualquiera con el código `HTL-XXXX` ve huésped, fechas y precio | `booking.py:243-287` | 🟠 privacidad |
| T2 | El texto de la excepción viaja al LLM (`f"Error ejecutando {name}: {e}"`) | `hotel_tools_pkg/__init__.py:70-82` | 🟡 fuga acotada |
| T3 | `ingest_docs.py`, `seed_knowledge.py`, `seed_places.py` **rotos** por imports movidos (`app.services.vector_store`/`knowledge_service` ya no existen ahí); además `ingest_docs.py` importa `langchain_text_splitters`, podado | `backend/ingest_docs.py`, `seed_knowledge.py`, `seed_places.py` | 🟠 operativo |
| T4 | `chroma_db_postsale/` directorio fantasma sin referencias | raíz backend | 🟡 limpieza |
| T5 | `_match_menu_items` devuelve `unmatched: []` siempre — feature documentada y no implementada | `_shared.py:239` | 🟡 |
| T6 | `retrieve_context()` duplica ~100 líneas de `retrieve_context_with_sources`; según su docstring no la usa producción | `rag_service.py:18-129` | 🟡 |
| T7 | Default mutable `room_types: List[str] = []` en firma pública (benigno hoy) | `hotel_sdk_orchestrator.py:174` | 🟢 |

### 4.3 RAG / conocimiento

- Pipeline: `.md` de `docsbase/` + entradas del backoffice → splitter propio (port 1:1 de langchain, con **test de paridad**) → embeddings `text-embedding-3-small` con caché LRU → ChromaDB persistente (coseno). Colección separada `management_knowledge` para gerencia.
- **Ingesta en caliente** idempotente en cada CRUD del backoffice (`knowledge_service.reingest`), con degradación silenciosa del índice ante errores (solo queda en logs).
- Recuperación con enriquecimiento de query (últimas 2 del usuario), umbral 0.25, dedup por documento.
- **Tests sobre tools:** cobertura determinística real (cards de habitación, preferencias, alergias, anti-inyección, consistencia spec↔tools — red contra bug reincidente, backstop de handoff, paridad del splitter). **Brechas:** handlers de booking con DB real, flujo restaurante, recuperación RAG.

---

## 5. Evaluación de pre-producción

### 5.1 🔴 Críticos (bloquean)

**C1 — `JWT_SECRET` con default inseguro y ausente de `render.yaml`.**
`config.py:83` define `JWT_SECRET = "dev-insecure-change-me"`; `render.yaml` no lo declara. Si no se cargó a mano en Render, cualquiera firma un JWT válido de admin con el secreto público del repo. El warning prometido en el comentario de `config.py:81-82` **no existe en el código**.
→ Setear `JWT_SECRET` en Render + fail-fast en arranque si `DEBUG=False` y el secreto es el default.

**C2 — La mayoría del backoffice no tiene autenticación.**
Solo 10 de ~30 routers usan `require_admin_key`/`require_admin`. **Sin auth:** `leads.py` (PII), `contacts.py` (360° del huésped), `conversations.py` (incluye `DELETE`, `POST /takeover`, `POST /reply` — un atacante puede **borrar conversaciones, tomar control y responder como el hotel**), `restaurant.py`, `knowledge.py` (upload de imágenes), `documents.py` (**PDFs directo al RAG → envenenamiento del conocimiento**), `staff.py`, `hotel_tickets.py`, `reservations.py`, `kanban.py`, `analytics.py`, `promotions.py`, `rooms_admin.py`, `management_knowledge.py`, `admin.py`. La dependencia existe y es fail-closed (`admin_auth.py:46-50`) — es cuestión de aplicarla.

**C3 — Webhook de Instagram sin validación de firma.**
`routers/instagram.py:52-77` acepta cualquier POST y lo despacha al agente. No existe `INSTAGRAM_APP_SECRET` en config. Permite inyectar "DMs" falsos → gasto de OpenAI, leads falsos, respuestas a IGSIDs arbitrarios. (El de Twilio sí valida firma, `whatsapp.py:329-337`.)

### 5.2 🟠 Altos

- **A1 — Login sin rate limiting ni lockout** (`routers/auth.py:36-45`); el limiter solo protege `/api/chat/message`.
- **A2 — Documentos de identidad de huéspedes servidos públicamente con nombre predecible:** check-in guarda DNI en `MEDIA_DIR/checkin/<codigo_reserva>.jpg` (`whatsapp.py:132-137`) y `/media` es `StaticFiles` sin auth (`main.py:282`). Mismo problema en `/vouchers`.
- **A3 — WebSocket de bandeja en vivo sin autenticación:** `ws_hub.origin_allowed` deja pasar clientes sin header Origin (`ws_hub.py:74-81`); con un `session_id` predecible (`wa_<tel>`) un tercero se suscribe al stream en vivo.
- **A4 — Migraciones sin red de seguridad:** stamp de Alembic pendiente en Render (runbook listo, paso manual); `ensure_column` traga excepciones con `except: pass` silencioso (`database.py:72-74,184-186,206-208,225-226`).
- **A5 — Seeds tolerantes a fallo en deploy:** `start.sh:6-15` termina cada seed en `|| echo "[warn]"` — el backend arranca con RAG/promos desactualizados y nadie se entera.

### 5.3 🟡 Medios

- **M1 — Event loop bloqueado por diseño:** routers `async` con SQLAlchemy **sync** y llamadas OpenAI/requests **sync** en rutas async (`agents.py:401`, `summary_service.py:233`, `exchange_rate_service.py:35`); audit log escribe a disco sync en el hot path. Con 1 worker uvicorn, una request lenta congela las demás. Aceptable para 1 hotel; cuello de botella real con tráfico.
- **M2 — Rate limiter en memoria + `request.client.host`** (IP del edge detrás de proxy; verificar `X-Forwarded-For`).
- **M3 — Estado en memoria** (historiales, estado multi-paso, ws_hub): sin escalado horizontal posible.
- **M4 — `/docs` y `/redoc` expuestos en producción** (`main.py:111-112`).
- **M5 — Creación de admins sin política de contraseñas** (`routers/auth.py:59-73`).
- **M6-M8:** `routers/alerts.py` sin montar; `@validator` Pydantic V1; telemetría de ChromaDB (posthog) activa por defecto.

### 5.4 🟢 Correcto (para constancia)

- CORS con allow-list explícita en prod; `allow_credentials` con orígenes concretos.
- JWT bcrypt/HS256/exp 12h con dependencias fail-closed donde se aplican; bootstrap admin idempotente.
- `OPENAI_API_KEY` sin default (arranque falla si falta); `.env` y DB gitignored; `.env.example` sin secretos.
- Validación de inputs (longitudes, uploads con extensión/tamaño), firma Twilio, timeouts, background tasks con logging de excepciones.
- Postgres con `pool_pre_ping` y fix de scheme; `StaticPool` solo en tests.
- Observabilidad: structlog JSON, request logging, OTEL opcional no-op, audit JSONL con rotación (PII solo en debug), `/metrics` y health sin PII.
- **Tests: 290 colectados, 282 passed / 8 skipped** (skipped = juez LLM sin API key), ejecutados en la auditoría.
- **Evals con LLM real** (`backend/evals/`): escenarios fijos + simulador de personas + LLM-as-judge con detección de invenciones — maduros, pero **manuales (no CI)**.

---

## 6. Comparación con buenas prácticas de mercado (agentes LLM en producción)

| Dimensión | Práctica esperada | Estado actual | Brecha |
|---|---|---|---|
| Definición de agentes | Declarativa, versionada, testeable | `AgentSpec` + runtime único + registry | Completar migración (composers muertos, triage/casual fuera del runtime) |
| Routing | Clasificador liviano dedicado, fallback seguro | gpt-4o-mini temp 0 + fallback a preventa + atajos 0-LLM | ✅ Ninguna relevante |
| Tools | Schemas claros, validación server-side, side effects controlados | Docstring-contrato + revalidación server-side + gates | Verificar identidad en `consultar_reserva`; sanitizar errores al LLM |
| Guardrails | Defensa en profundidad (determinístico + modelo) | Gates determinísticos fuertes; input guardrail por substring débil | Guardrail basado en modelo/clasificador en vez de substring |
| Prompts | Composición modular, versionado, anti-inyección | Bloques + versionado DB + `wrap_untrusted_docs` | Bug de voseo; hardcodeos de marca |
| Evals | Evals automáticas en CI como gate de cambios de prompt | Suite madura con LLM-as-judge pero manual | Correr en CI (aunque sea subset acotado por costo) |
| Observabilidad LLM | Trazas por turno (spans LLM/tools), costo por conversación | Logs + audit + usage; OTEL no-op sin backend | Activar trazas (OTEL o tracing del SDK) en pre-prod |
| Estado conversacional | Persistencia externa si >1 worker | RAM + rehidratación DB; single-instance | Aceptable mientras sea 1 instancia/1 worker; documentar el límite |
| Latencia/UX | Streaming de respuesta | Sin streaming; cadena de hasta 3 llamadas LLM secuenciales | Evaluar `run_streamed` para web; el gating de lead-analysis ya es parche |
| Migraciones | Un solo sistema, falla ruidosa | Alembic + ensure_column con `except: pass` | Stamp + política ya definida en runbook; ejecutarla |

---

## 7. Roadmap priorizado para pre-producción

### Fase 0 — Bloqueante (días, esfuerzo bajo)

1. Setear `JWT_SECRET` (+ `BOOTSTRAP_ADMIN_*`) en Render; fail-fast en arranque si el default está activo con `DEBUG=False`. *(C1)*
2. Aplicar `require_admin_key`/`require_admin` a todos los routers de backoffice — empezando por `conversations.py`, `contacts.py`, `leads.py`, `documents.py`. *(C2)*
3. Validar firma `X-Hub-Signature-256` en Instagram (agregar `INSTAGRAM_APP_SECRET`). *(C3)*
4. Rate-limit + lockout en `/api/auth/login`; auth en el WebSocket de conversaciones. *(A1, A3)*
5. Sacar documentos de check-in de `/media` público (servir con auth y nombre no predecible); idem vouchers. *(A2)*
6. Ejecutar el stamp de Alembic en Render con backup, siguiendo `RUNBOOK_ALEMBIC.md`. *(A4)*

### Fase 1 — Endurecimiento (1-2 semanas)

7. `ensure_column` sin `except: pass` (log + falla ruidosa); seeds con fail-fast o alerta clara en `start.sh`. *(A4, A5)*
8. Verificación de identidad en `consultar_reserva` (ej. código + apellido o teléfono). *(T1)*
9. Reparar o eliminar `ingest_docs.py`, `seed_knowledge.py`, `seed_places.py`; borrar `chroma_db_postsale/` y paquetes fantasma. *(T3, T4)*
10. Helper central `channel_from_session()` y atribución de agente sin prefijos frágiles; incluir `ig_` en `agent_directory`.
11. Unificar guardrails anti-jailbreak (una sola fuente, idealmente clasificador) y eliminar hardcodeos "Hampton" en respuestas (usar `BusinessProfile`).
12. Apagar `/docs`/`/redoc` en prod; política mínima de contraseñas; sanitizar texto de excepciones hacia el LLM.
13. Apagar telemetría de ChromaDB (`anonymized_telemetry=False`).

### Fase 2 — Madurez del modelo de agentes (continuo)

14. Sacar la lógica de negocio del dios-router `chat.py` a services/domains; reducir `_chat_impl`.
15. Completar la migración declarativa: implementar composers o eliminar el campo; meter triage/casual al runtime o sacarlos del catálogo.
16. Limpiar residuos del dominio turismo (métricas `travel_agent_*`, fix de paquetes, `notification_service`, stubs RAG, tablas huérfanas en Render).
17. Evals en CI (subset acotado por costo) como gate de cambios de prompts; medir cobertura.
18. Streaming (`run_streamed`) en el canal web; activar trazas OTEL/SDK en pre-producción.
19. Decidir explícitamente el techo de escala: si se necesita >1 worker, mover historiales/locks/estado multi-paso a Redis/DB y rate limiter a storage compartido.
20. Migrar `@validator` → `@field_validator` (Pydantic V2) y unificar datetimes naive/aware.

---

## 8. Relación con la documentación existente

- `backend/DEUDA_TECNICA.md` — sigue vigente; este informe confirma el stamp de Alembic como único paso pendiente y los hardcodeos Hampton; agrega C1-C3 y A1-A5.
- `backend/AUDITORIA_ARQUITECTURA.md` — **desactualizado** (referencia archivos borrados: `postsale_service.py`, `agent_sdk_orchestrator.py`); sus H3 (latencia por cadena LLM), H5 (estado en RAM) y H14 (validators V1) siguen vigentes y quedan reflejados en Fase 2.
- `backend/AGENT_REUSE.md` — decisión de tenancy y contrato de privacidad por rol siguen correctos; referencias a turismo/Freeway desactualizadas.
- `backend/RUNBOOK_ALEMBIC.md` — procedimiento correcto; ejecutar el paso manual pendiente (Fase 0.6).

---

## 9. Fase 2 — Avance y decisión de escala

> Nota de progreso: ejecución de la Fase 2 del roadmap (puntuación interna 2026-07-17).

### 9.1 Trabajo completado

| Ítem | Archivo(s) | Qué se hizo |
|---|---|---|
| Residuos de turismo | `notification_service.py`, `alert_service.py`, `alerts.py`, `intelligent_geography.py`, `geography.py`, `document_classifier.py` | Eliminados; no estaban importados en la app actual. |
| Fix de paquetes truncados | `routers/chat.py` (líneas 623–670) | Eliminado; era un parche específico del dominio turismo. |
| Tracking de destinos/paquetes | `routers/chat.py` (líneas 849–885) | Eliminado; ahora solo se trackean documentos. |
| Destinos en RAG | `vector_store.py`, `rag_service.py`, `routers/chat.py` (`/destinations`) | Removidos. |
| Modelos de turismo | `schemas.py` (`GeographyAnalysis`, `DestinationsResponse`) | Eliminados. |
| Métricas de turismo | `metrics_service.py` | Simplificados (`track_conversation`); eliminados `_get_popular_destinations`/`get_popular_packages`. |
| Pydantic V2 | `schemas.py` | `@validator` → `@field_validator`; `ChatResponse` usa `model_config = ConfigDict(extra="allow")`. |
| Datetimes | `agent_service.py`, `contacts.py`, `hotel_postsale_orchestrator.py`, `lead_service.py` | Reemplazados `datetime.now(timezone.utc)` por `utcnow_naive()` de `app.utils.timezone_utils`. |
| CI | `.github/workflows/backend-tests.yml`, `.github/workflows/evals.yml` | Tests en push/PR; evals manuales por workflow (requiere `OPENAI_API_KEY`). |

### 9.2 Estado de la suite de tests

- **Última corrida:** `cd backend && .venv/Scripts/python -m pytest tests/ -q`
- **Resultado:** `302 passed, 8 skipped, 25 warnings`
- Los 8 skipped corresponden a evaluaciones con LLM real sin API key configurada; son esperados.

### 9.3 Decisión de escala: 1 instancia / 1 worker

Tras los cambios de Fase 2, la aplicación sigue usando **estado en memoria** para:
- historiales de conversación en el runtime declarativo (`AgentRuntime` en `agent_service.py`),
- locks/estado multi-paso del postsale orchestrator (`hotel_postsale_orchestrator.py`),
- sesiones en el rate limiter (`middleware/rate_limiter.py`), y
- `ws_hub` (`ws_hub.py`) para WebSockets.

Esto es **viable y aceptable para pre-producción** si se cumplen estas condiciones:
- Un solo contenedor/servicio en Render (o donde se despliegue) con **1 worker de uvicorn** (`--workers 1`).
- No se escala horizontalmente (replicas > 1) sin antes migrar el estado.
- Se documenta el límite en el runbook de operaciones.

**Para escalar horizontalmente** se requiere:
1. **Historiales de conversación:** moverlos a Redis/Postgres o a un servicio de memoria compartida; actualmente se rehidratan desde la DB pero se mantienen en RAM.
2. **Locks/estado multi-paso del postsale:** migrar a Redis con TTL o a una tabla de estado con locking por row.
3. **Rate limiter:** cambiar el `MemoryStorage` por Redis/Postgres para que sea consistente entre workers.
4. **WebSockets:** usar un broker de pub/sub (Redis, etc.) para que múltiples instancias puedan enviar mensajes a la misma sesión.
5. **Tareas en segundo plano:** si se usan `BackgroundTask` en FastAPI, se deben externalizar a un worker (Celery/RQ) o garantizar que el mismo worker procesa el evento.

### 9.4 Items pendientes grandes y arriesgados de Fase 2

Los siguientes puntos **no se iniciaron** porque implican alto riesgo de regresión y esfuerzo significativo:

| Ítem | Riesgo | Esfuerzo estimado | Por qué no se tocó |
|---|---|---|---|
| Refactor del dios-router `chat.py` (~1100 líneas, ~450 de lógica de negocio) | Alto. Afecta tests, frontend y contratos de API. | 1-2 semanas | Requiere diseño previo de servicios/domains y probablemente ajustes en el frontend. |
| Completar migración declarativa (composers muertos, triage/casual fuera del runtime) | Alto. Cambia el modelo de agentes y los tests de especificaciones. | 1-2 semanas | `AgentSpec.prompt_composer` sigue sin implementarse; triage/casual no usan el runtime declarativo. |
| Streaming (`run_streamed`) | Medio-Alto. Requiere cambios en frontend y orquestador. | 3-5 días | No se priorizó; la UX actual funciona sin streaming. |
| Tablas huérfanas del legacy turismo en Render | Medio. Requiere revisión Alembic con backup. | 1 día | Es un cambio de schema y datos, no de código; se debe ejecutar con precaución. |

### 9.5 Recomendación

Con lo completado en Fase 2, la aplicación está en mejor estado para pre-producción: código muerto eliminado, compatibilidad con Pydantic V2, datetimes unificados, CI básica y tests verdes. **Se recomienda no abordar los ítems grandes de Fase 2 en la misma pasada** para evitar regresiones innecesarias antes de la primera entrega.

**Próximos pasos sugeridos:**
1. Si se acepta el techo de escala 1 instancia/1 worker: documentar en el runbook de operaciones y continuar con **Fase 0 y Fase 1** (seguridad y endurecimiento), que tienen mayor impacto directo en pre-producción.
2. Si se necesita escalar horizontalmente: tratar el tema de memoria compartida como un proyecto aparte antes de salir a producción.
3. Dejar el refactor de `chat.py` y la migración declarativa completa para una iteración posterior, con su propio diseño y tests dedicados.
