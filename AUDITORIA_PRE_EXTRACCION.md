# Auditoría Consolidada Pre-Extracción

> **Documento de trabajo autocontenido.** Está escrito para que cualquier agente o desarrollador pueda ejecutar el backlog sin contexto previo: cada hallazgo incluye evidencia verificable (archivo:línea), fundamento, pasos de resolución y criterio de aceptación.

| | |
|---|---|
| **Fecha de auditoría** | 2026-07-26 |
| **Repositorio** | `cristianjuarez-wg/Nuevo-Agente-Base-Hotel` |
| **Rama auditada** | `master` (HEAD `51c185e`; todas las ramas `feat/fase-*` ya mergeadas) |
| **Alcance** | Backend completo (`backend/`), frontend completo (`landing/`, `presentacion/`), documentación de visión y deuda (raíz, `docs/`, `backend/*.md`) |
| **Método** | Revisión estática exhaustiva (lectura de archivos clave + búsquedas dirigidas sobre todo el código). No se ejecutó la suite de tests ni se modificó código durante la auditoría. |

---

## 0. Contexto y objetivo

Este repositorio implementa un **"empleado digital" para hoteles** (backend FastAPI + SQLAlchemy + OpenAI Agents SDK; frontend React 18 + Vite + Tailwind). El objetivo estratégico del dueño es **extraer el núcleo como "agente base" reutilizable** para proyectos de **otros rubros**, con otros procesos de negocio.

Esta auditoría se realizó **antes** de armar el plan de extracción, para responder:

1. ¿Qué hay que mejorar o refactorizar **antes** de extraer, para no arrastrar deuda al nuevo proyecto?
2. ¿Dónde está exactamente la línea de corte entre **núcleo reutilizable**, **módulo de dominio hotelero** y **lo que se rehace por proyecto**?
3. ¿Qué trabajo conviene hacer **durante** la extracción (no antes)?

### Veredicto en un párrafo

La arquitectura es modular y reutilizable **como plantilla documentada** (no como librería plug-and-play). La separación `app/core/` vs `app/domains/hotel/` es real y está protegida por test permanente. Pero extraer hoy arrastraría: una guía de extracción obsoleta (`AGENT_REUSE.md`), endpoints de backoffice sin autenticación, un circuit breaker que no envuelve ninguna llamada real, el arranque de producción fusionado con los datos del cliente Hampton, y marca (Hilton/Hampton/Aura) hardcodeada en ambos frentes. Todo es trabajo acotado: **el backlog pre-extracción son ~3-4 semanas-persona**, con varios ítems de esfuerzo chico y alto impacto.

---

## 1. Mapa del sistema (para quien llega de afuera)

```
Nuevo-Agente-Base-Hotel/
├── backend/
│   ├── app/
│   │   ├── core/            # NÚCLEO genérico — protegido por tests/test_architecture.py
│   │   │   ├── agents/      # agent_spec.py (AgentSpec declarativo), sdk_runtime.py (loop único
│   │   │   │                #   run_agent), tool_registry.py (registries de tools/composers/guardrails)
│   │   │   ├── llm/         # openai_client, circuit_breaker, retry, pricing, usage
│   │   │   ├── rag/         # embeddings, vector_store (ChromaDB), rag_service, pdf_processor
│   │   │   ├── channels/    # whatsapp_service (Twilio), instagram_service (Meta), ws_hub
│   │   │   ├── profile/     # agent_profile.py (loader de perfiles JSON)
│   │   │   ├── observability/  # structlog, audit_log, OTel
│   │   │   └── security/    # JWT backoffice, admin_key, rate limit
│   │   ├── domains/hotel/   # DOMINIO hotelero
│   │   │   ├── agent_specs.py        # catálogo SPECS: 6 agentes declarativos
│   │   │   ├── prompts/              # 10 módulos de prompts hoteleros + base_blocks.py (transversales)
│   │   │   ├── services/             # agent_router (ruteo por rol), casual_agent, knowledge_service
│   │   │   └── orchestrators/ models/ tools/ seeds/   # VACÍOS a propósito (ver AGENT_REUSE P4.1)
│   │   ├── services/        # ~45 servicios: orquestadores + lógica hotelera mezclados
│   │   │                    #   (hotel_sdk_orchestrator 820 lín., hotel_postsale_orchestrator 711,
│   │   │                    #    owner_orchestrator 617, staff_orchestrator 235, triage_sdk_orchestrator 231,
│   │   │                    #    agent_service 974, lead_service 970, hotel_tools_pkg/ particionado)
│   │   ├── models/          # ~28 modelos ORM (genéricos y hoteleros comparten directorio)
│   │   ├── routers/         # ~28 routers FastAPI
│   │   ├── constants/       # keywords, guardrails, status
│   │   └── main.py          # 467 líneas: composición, lifespan con seeds, health, metadata
│   ├── instance/            # bootstrap_instance.py + hampton.yaml, demo2.yaml, instance.example.yaml
│   ├── alembic/             # baseline 0001 listo; FALTA stamp en producción
│   ├── evals/               # framework de evaluación conversacional (judge LLM, scenarios 867 lín.) — manual, no CI
│   └── tests/               # 49 archivos, 289 tests; test_architecture.py es el guardrail clave
├── landing/                 # React 18 + Vite 5 + Tailwind 3 + Recharts (~16.700 lín., 82 archivos)
│   └── src/
│       ├── App.jsx          # routing manual por hash: home / #admin / #pedido
│       ├── components/      # landing pública (100% hotelera) + ChatWidget + chat/ + restaurant/
│       ├── admin/           # backoffice: AdminApp shell, LoginGate, 14+ vistas, ui.jsx, toast
│       ├── services/api.js  # cliente API centralizado (axios, 956 lín., ~100 funciones)
│       ├── data/hotelInfo.js  # fallback de identidad = datos REALES del Hampton
│       └── hooks/useBusinessProfile.js  # consume /api/public/business-profile
├── presentacion/            # HTML estático comercial (duplicado y divergente en landing/public/)
├── docs/                    # ARQUITECTURA_TENANCY.md, RUNBOOK_NUEVA_INSTANCIA.md, agentes/, etc.
├── backend/DEUDA_TECNICA.md # deuda autodeclarada (parcialmente desactualizada — ver §6.1)
├── backend/AGENT_REUSE.md   # guía de extracción — OBSOLETA (hallazgo C1, el más importante)
├── VISION_EMPLEADO_DIGITAL.md  # regla de diseño: "capacidades como parte del agente base,
│                              #   no features del hotel"
└── ANALISIS_RFI_ASISTENTE_FISCAL.md (+ .pdf)  # ⚠️ AJENO a este proyecto: consulta puntual de
                                               #   otro proyecto (Grupo San Cristóbal, seguros) que
                                               #   quedó mezclada en el repo. NO es un 2° vertical
                                               #   real. Desestimar y remover del repo (ítem #12).
```

**Los 6 agentes** (catálogo en `domains/hotel/agent_specs.py` → `SPECS`):

| Agente | Rol | Orquestador | Tools |
|---|---|---|---|
| `hotel_presale` (Aura) | guest | `services/hotel_sdk_orchestrator.py` | 17 |
| `hotel_postsale` (Aura) | guest | `services/hotel_postsale_orchestrator.py` + gate en `hotel_postsale.py` | 13 |
| `hotel_owner` (Asesor) | management | `services/owner_orchestrator.py` | 19 (BI) |
| `hotel_staff` | staff | `services/staff_orchestrator.py` | 3 |
| `casual` | guest | `domains/hotel/services/casual_agent.py` (completions directo) | 0 |
| `triage` | guest | `services/triage_sdk_orchestrator.py` | handoffs |

---

## 2. Lo que está BIEN (no tocar — es el valor del núcleo)

Estas piezas son la razón por la que la extracción vale la pena. El backlog NO debe romperlas:

1. **`tests/test_architecture.py`** — falla en CI si cualquier archivo de `app/core/` importa de dominio (`app.domains`, `app.services`, `app.prompts`, `app.routers`), con whitelist explícita (`app.models.{database,schemas,conversation,admin_user}`). Es el guardrail más importante del proyecto.
2. **Runtime declarativo de agentes** (`core/agents/`): una `AgentSpec` (dataclass frozen) + un solo loop `run_agent(spec, instructions, context, input_list, ...)` usado por los 4 orquestadores SDK + registries fail-fast de tools/composers/guardrails. Agregar un agente = declarar spec + registrar tools con keys namespacadas.
3. **Filosofía "el LLM analiza, el código decide"**: gate determinístico post-venta (`hotel_postsale.py`), backstops (`needs_human`, `apply_ticket_action`, channel gate, datepicker gating). Patrón especialmente valioso para dominios regulados o acciones sensibles.
4. **Auth de backoffice en escritura**: JWT + bcrypt fail-closed, fail-fast si `JWT_SECRET` queda default en producción (`main.py:39-42`), rate limit en login.
5. **Freno de presupuesto**: `usage_service.is_budget_exceeded` antes de llamar al LLM.
6. **Mecanismo de instancia por cliente**: `instance/bootstrap_instance.py` + YAML → bootstrap idempotente; `docs/RUNBOOK_NUEVA_INSTANCIA.md` con la vara "alta en <2h sin editar Python". Prueba de fuego ya superada: `demo2.yaml` (pousada en BRL).
7. **Anti-inyección sobre documentos RAG**: `wrap_untrusted_docs` (`base_blocks.py:67`, aplicado en `hotel_tools_pkg/info.py:49-52`).
8. **Frontend**: `api.js` centralizado con interceptores; `useBusinessProfile` → endpoint público (patrón correcto, a medio aplicar); ChatWidget con reconexión backoff, dedupe, accesibilidad (`aria-*`, `prefers-reduced-motion`); sidebar del admin ya separada conceptualmente en "Operar / El agente / Sistema".
9. **`evals/`**: judge LLM + escenarios + gate de comportamiento — la herramienta correcta para lo que pytest no ve.

---

## 3. Hallazgos BACKEND

Severidad: 🔴 crítico (bloquea o contamina la extracción) · 🟡 importante (hacer antes o durante) · 🟢 menor.

### 🔴 C1 — `backend/AGENT_REUSE.md` describe un sistema que ya no existe

- **Qué:** la guía de reúso referencia como piezas a copiar archivos eliminados en la Fase 0.2: `agent_sdk_orchestrator.py`, `postsale_sdk_orchestrator.py`, `agent_tools.py`, `postsale_tools.py`, `models/postsale.py`, `models/provider.py`, `core/geography.py`, `core/intelligent_geography.py`, `app/prompts/*`, `data/agent_profiles/turismo.json`. Su tabla "copiar tal cual vs reescribir" (§6) y checklist (§7) apuntan a líneas de archivos inexistentes. Dice "Última verificación de líneas: 2026-06-19", anterior a la Fase 0.2 (2026-07-09). Describe el runtime como "molde a clonar" (§4.3) cuando ya existe el runtime declarativo `core/agents/` (Fase 2.2), que cambia completamente la recomendación.
- **Evidencia:** verificar con `ls backend/app/services/agent_sdk_orchestrator.py` → no existe; comparar con las referencias del doc.
- **Por qué importa:** es EL documento que seguiría quien porte el núcleo. Seguirlo hoy lleva a buscar archivos que no existen y a clonar orquestadores en vez de escribir una `AgentSpec`. Peor que no tener guía: da confianza falsa.
- **Resolución:** reescribir `AGENT_REUSE.md` contra el estado real: `AgentSpec` + `sdk_runtime.run_agent` + `tool_registry`, `hotel_tools_pkg/`, prompts en `domains/hotel/prompts/`, mecanismo de instancia YAML. La sección §5 de este documento (línea de corte) es el insumo base.
- **Criterio de aceptación:** toda ruta mencionada en el doc existe (`grep` de cada path citado); la recomendación central es "declarar specs, no clonar orquestadores".
- **Esfuerzo:** M.

### 🔴 C2 — Endpoints de backoffice expuestos sin autenticación (lectura)

- **Qué:** `main.py:261,276,277` monta los routers `usage`, `agents` y `business_profile` sin `_admin_dep`, y sus GET no tienen dependencia propia:
  - `GET /api/agents/{id}/training` (`routers/agents.py:238-248`) — documentos de entrenamiento del cliente, sin auth.
  - `GET /api/agents/{id}/performance` (`agents.py:144-150`) — costo de IA y desempeño, sin auth.
  - `GET /api/usage/summary` y `/api/usage/config` (`usage.py:31-48`) — gasto en USD y topes, sin auth.
  - `GET /api/business-profile` (`business_profile.py:45-48`) — perfil completo. Existe además `/public/business-profile` (:60) diseñado explícitamente como "subset SEGURO", lo que prueba que el full debió quedar protegido.
  - `GET /api/agents`, `/{id}`, `/capabilities`, `/daily-report`, `/skills` (`agents.py:41,86,94,167,444`) — el docstring de :98 asume "Lectura, sin auth (mismo patrón…)": es un patrón implícito nunca auditado.
- **Por qué importa:** información de negocio (costos, material de entrenamiento) pública en internet hoy; si el núcleo se vuelve multi-cliente, se hereda tal cual.
- **Resolución:** montar esos routers con `_admin_dep` o agregar la dependencia admin a cada GET (el frontend ya envía JWT). Revisar uno por uno los 28 routers y documentar cuáles quedan públicos y por qué (whitelist explícita, no patrón implícito).
- **Criterio de aceptación:** cada GET de la lista devuelve 401 sin token; tests HTTP que lo verifiquen (el `conftest.py` ya tiene fixtures `client` y `admin_headers`).
- **Esfuerzo:** S. **Hacerlo ya, independiente de la extracción** — es un agujero vivo en producción.

### 🔴 C3 — El circuit breaker de OpenAI es decorativo

- **Qué:** `openai_circuit_breaker` (`core/llm/circuit_breaker.py:145`) **nunca envuelve una llamada a OpenAI**. Solo se lee para stats (`agent_service.py:953`, `admin.py:98`, `analytics.py`) y se resetea por admin. El `vector_store_circuit_breaker` sí se usa (`rag_service.py:73,185`). Si OpenAI cae, cada turno espera el timeout completo del SDK (y hasta 60 s del `wait_for` de chat/whatsapp) sin fail-fast, y el health reporta `closed` aunque todo falle.
- **Por qué importa:** la resiliencia anti-caída de OpenAI es parte del "patrón" que se vendería como núcleo; hoy es una promesa vacía. El anti-500 evita el crash, no la latencia/costo en cascada.
- **Resolución:** envolver el cliente compartido o `Runner.run` dentro de `sdk_runtime.run_agent` con `openai_circuit_breaker.acall(...)`; definir qué cuenta como fallo (timeout, 5xx, rate-limit sostenido) y umbral de apertura; respuesta de fallback cuando el circuito está abierto.
- **Criterio de aceptación:** test que simula N fallos consecutivos y verifica que el circuito abre y las llamadas siguientes fallan rápido con fallback; el health refleja el estado real.
- **Esfuerzo:** M.

### 🔴 C4 — `start.sh` siembra los datos del Hampton en cada arranque

- **Qué:** `start.sh` ejecuta en CADA boot: `seed_hotel.py`, `seed_room_units.py`, `ingest_docs.py`, `seed_knowledge.py`, `seed_places.py`, `seed_promotions.py` — datos hardcodeados del Hampton, con `set -euo pipefail` (un seed roto tumba producción). Además `main.py` lifespan (:69-89) tiene seeds propios y `models/database.py:55` hace `create_all` al importar.
- **Por qué importa:** es la acopliación más concreta entre infra y cliente: arrancar el núcleo para otro rubro exige reescribir el entrypoint. Además re-ingesta al RAG en cada restart.
- **Resolución:** mover los seeds a provisión one-shot usando lo que ya existe: `instance/bootstrap_instance.py` + YAML (`hampton.yaml`). `start.sh` debe quedar rubro-agnóstico: migraciones + uvicorn. Quitar seeds del lifespan de `main.py`.
- **Criterio de aceptación:** `start.sh` no menciona ningún seed de dominio; levantar una instancia nueva = `bootstrap_instance` + arranque limpio; boot sin re-ingesta RAG.
- **Esfuerzo:** M.

### 🟡 I1 — Duplicación residual y código muerto en orquestadores (post-Fase 2.2)

- **Qué:** `_build_input_list` duplicado y **sin uso** en `hotel_sdk_orchestrator.py:673`, `owner_orchestrator.py:577`, `staff_orchestrator.py:198`, `hotel_postsale_orchestrator.py:577` (todos llaman `sdk_runtime.build_input_list`; solo el de `triage:167` se usa). `set_default_openai_client(...) + set_tracing_export_api_key(...)` a nivel de módulo ×5. Bloque "fecha en español con try/except" ×3 (`hotel_sdk:493-495`, `owner:552-554`, `staff:184-186`). Imports muertos: `extract_usage` ×4, `ModelSettings`/`OpenAIChatCompletionsModel` ×4 (0 usos). Inicialización del dict `usage` repetida en 4 `run()`.
- **Por qué importa:** el núcleo debe mostrar UN patrón limpio; hoy cada orquestador es un "clon podado" y no se distingue contrato de residuo.
- **Resolución:** eliminar código muerto; mover lo repetido real a `core/agents/` (helper de fecha, setup de SDK en un solo módulo importado por todos).
- **Esfuerzo:** S. **Momento ideal: durante la extracción**, al reescribir orquestadores como specs.

### 🟡 I2 — Registro de tools/guardrails por efecto lateral de import

- **Qué:** `tool_registry._TOOLS` se llena en top-level de cada módulo orquestador (`hotel_sdk_orchestrator.py:437-439`, `owner:533-536`, `postsale:439-441`, `staff:130-133`). `resolve_tools` falla con `KeyError` si el módulo registrador no fue importado antes (`tool_registry.py:43-45` — el propio mensaje de error "¿Falta importar el módulo…?" delata que ya mordió). El orden de imports define si el runtime funciona.
- **Resolución:** punto de composición explícito: un `register_all()` por dominio invocado desde el arranque (o entrypoint del paquete de dominio). Es exactamente el patrón plugin que el núcleo necesita.
- **Esfuerzo:** M. Hacer **durante** la extracción.

### 🟡 I3 — Estado global mutable sin límite en singletons

- **Qué:** `agent_service` global (`agent_service.py:974`) mantiene `conversation_history`, `session_metadata` y `_session_locks` por sesión; el número de sesiones no tiene bound y los locks solo se eliminan en `clear_history` (:882-884). Igual `_role_histories` y `_last_owner_chart` en `agent_router.py:31,35`. En un proceso long-lived la RAM crece para siempre. Además routers acceden a privados (`chat.py:573`, `whatsapp.py:229` usan `_save_message_to_db`; `hotel_sdk_orchestrator:588` y `whatsapp.py:215` usan `lead_service._get_or_create_lead`).
- **Resolución:** TTL/LRU sobre historiales y locks; API pública de historial; promover los métodos `_` consumidos externamente a públicos.
- **Esfuerzo:** M.

### 🟡 I4 — Sin inyección de dependencias; sesiones DB ad-hoc dentro de la lógica

- **Qué:** `owner_orchestrator._build_instructions` (:556-561) y `triage_sdk_orchestrator._build_triage_instructions` (:82-87) abren un `SessionLocal()` nuevo **por mensaje** solo para leer el BusinessProfile, aunque el caller ya tiene `db`. `agent_router._route_owner` abre otra sesión `mem_db` (:154) por un smell transaccional (comentario :149-151). Singletons importados (`rag_service`, `lead_service`, `profile_manager`, `business_profile_service`) impiden sustituir colaboradores en tests sin monkeypatch. El perfil de negocio se relee de DB varias veces por turno.
- **Resolución:** pasar `db` por parámetro; cachear BusinessProfile por turno (o TTL corto); introducir DI gradual en orquestadores (constructor con colaboradores, default a singletons).
- **Esfuerzo:** M. Hacer **durante** la extracción.

### 🟡 I5 — Triple fuente de verdad del esquema: `create_all` + `ensure_column` + Alembic

- **Qué:** conviven (a) `Base.metadata.create_all` al importar (`database.py:55` y a nivel de módulo en `action_plan.py:44`, `admin_user.py:40`, `agent.py:60`, `business_profile.py:86`, `centro_config.py:33`, `chat_theme.py:78`…), (b) `run_light_migrations()` con ~40 `ensure_column` + recreación de tabla SQLite (`database.py:82-214`), y (c) Alembic baseline sin `stamp` en producción ni `upgrade` en `start.sh`. Tablas huérfanas de turismo aún vivas en la DB de Render.
- **Resolución:** una sola fuente: Alembic. Pasos: backup de prod → `alembic stamp 0001` en prod → agregar `alembic upgrade head` a `start.sh` → congelar `ensure_column` solo para tests/SQLite → migración que dropee tablas huérfanas → quitar `create_all` de producción.
- **Esfuerzo:** M (coordinado con backup; independiente del código).

### 🟡 I6 — Guardrail anti-jailbreak trivialmente rodeable y con falsos positivos

- **Qué:** `JAILBREAK_MARKERS` (`constants/guardrails.py`): 6 substrings literales ("system prompt", "ignore previous", "actúa como"…). Un huésped que escribe "system prompt" legítimamente dispara el tripwire; un atacante que escribe "ignora tus reglas previas" pasa. El input del usuario va crudo al prompt con solo esta lista como defensa.
- **Resolución:** clasificador con `OPENAI_MODEL_CLASSIFIER` (gpt-4o-mini ya configurado) o lista curada + tests de evasión en `evals/` (la infra ya existe).
- **Esfuerzo:** M.

### 🟡 I7 — Cobertura de tests: fuerte en prompts/dominio, floja en el hot-path

- **Qué cubren (49 archivos / 289 tests):** composición de prompts y paridad, seguridad Fase 0, `test_architecture.py`, runtime de specs (`test_agent_runtime.py` mockea Runner), gates determinísticos, timezone, money, room prices.
- **Qué NO cubren:** `agent_service._chat_impl` end-to-end (~300 líneas que deciden todo), orquestadores pre/post-venta con sus 16+13 tools, `reservation_service` (**lock pesimista anti doble-booking sin test de concurrencia**), handlers de `hotel_tools_pkg` (442 lín. `booking.py`), `lead_service` (970 lín.), la mayoría de los 28 routers a nivel HTTP (fixtures listos, poco usados). `evals/` es manual y gasta OpenAI — nada corre en CI.
- **Por qué importa:** refactorizar el núcleo sin red en el hot-path es hacerlo a ciegas. Los tests de paridad de prompts son snapshots frágiles: al portar, decidir cuáles son contrato y cuáles se tiran.
- **Resolución (mínimo viable):** test de doble-booking concurrente sobre `crear_reserva`; tests del gate post-venta ya existen — extender a flujo completo; 2-3 tests HTTP por router crítico (chat, whatsapp, admin auth).
- **Esfuerzo:** L (el más caro de la lista; acotar al mínimo viable pre-extracción).

### 🟡 I8 — Audit log con PII dentro del paquete y efímero en producción

- **Qué:** `audit_log.py:25-26` escribe `backend/app/logs/aura_audit.jsonl` **dentro del paquete** con mensajes completos del huésped y args/outputs de tools (PII). Rotación: un solo backup de 10 MB. En Render el repo no es disco persistente (`/data`), así que el rastro se pierde en cada deploy. Hay un `aura_audit.jsonl` con conversaciones reales presente en el working tree (riesgo de commiteo).
- **Resolución:** mover a `MEDIA_DIR`/`/data` o a DB; agregar a `.gitignore`; redacción opcional de PII; política de retención.
- **Esfuerzo:** S.

### 🟢 Menores backend

| # | Hallazgo | Evidencia | Esfuerzo |
|---|---|---|---|
| M1 | `main.py` mezcla composición, seeds, health y metadata de cliente ("Hampton Bariloche" en :116-117, :382-384); residuos de turismo en contratos: `HealthResponse.geography_service` hardcodeado `healthy: True` (:352-356), métricas `/metrics` con nombres `travel_agent_*` (:434-444) | `main.py` | S |
| M2 | `core/profile/agent_profile.py` (¡en el núcleo!) con 4 bare `except:` (:28-35) y `locale.setlocale` global (no thread-safe) en método legacy sin uso (:50-55) | `agent_profile.py` | S |
| M3 | `_validate_input` teatral: rechaza por substrings `'DROP TABLE'`, `'eval('` — inútil contra SQLi (SQLAlchemy parametriza) y bloquea mensajes legítimos | `agent_service.py:487-492` | S |
| M4 | `hotel_location.py` 100% Hampton (:15-22, "Libertad 290" y distancias); `identity_blocks.py:51,57,93,100` tiene `if negocio == "Hampton by Hilton Bariloche"` para paridad byte-a-byte | — | M (cuidado: tests de paridad) |
| M5 | Voseo hardcodeado en `NATURALIDAD_BLOCK` | `generation_prompts.py:56,59` | S |
| M6 | Webhooks fail-open si falta credencial: Twilio valida firma solo `if settings.TWILIO_AUTH_TOKEN` (`whatsapp.py:341`), Instagram igual (`instagram.py:64`). Además la firma Twilio usa `str(request.url)` (:346) — verificar scheme/host tras proxy de Render. Debe ser fail-closed en prod | — | S |
| M7 | Residuos: `app/prompts/` con solo `__init__.py`; `app/scripts/001_create_postsale_tables.py` (403 lín.) crea tablas de turismo muertas; `GET /metrics` público | — | S |
| M8 | Dependencias pesadas heredadas de ChromaDB 1.2.1: `kubernetes==34.1.0`, `posthog==5.4.0` pinneadas como "directas obligatorias". Evaluar reemplazo del vector store al extraer | `requirements.txt` | M/L |
| M9 | `evals/` deja datos si se interrumpe y puede saturar habitaciones en corridas largas (documentado en su README) | `evals/` | S |
| M10 | 69 ocurrencias de "Hampton" en 18 archivos `.py` bajo `app/` (títulos, fallbacks de error, constantes) | grep | S-M |

---

## 4. Hallazgos FRONTEND (`landing/` + `presentacion/`)

### 🔴 F1 — Marca Hilton como token de diseño estructural

- **Qué:** `tailwind.config.js:8-20` define el azul Hilton como color `hilton`, usado en ~40 archivos y cientos de clases (`KnowledgeView` 39 usos, `ThemesView` 19, `AdminApp` 12…).
- **Por qué importa:** sin neutralizar esto no hay plantilla — cada rubro nuevo heredaría el azul Hilton en cada botón.
- **Resolución:** renombrar token `hilton` → `brand` (reemplazo global mecánico) y mover los valores a un archivo de tema por instancia.
- **Criterio de aceptación:** cero resultados de `grep -r "hilton" landing/src`; cambiar el tema = editar un solo archivo.
- **Esfuerzo:** M (mecánico pero voluminoso).

### 🔴 F2 — Landing pública acoplada por construcción → NO parametrizar: se rehace por proyecto

- **Qué:** `App.jsx:38-50`, `data/hotelInfo.js` (datos reales del Hampton), `public/fotos/` referenciadas en `About.jsx:13` y `Gallery.jsx:6-19`, título/meta en `index.html:6-9`, secciones `Hero/Rooms/BookingEngine/Restaurant/Gallery/Location` 100% hoteleras.
- **Decisión:** la landing pública es la vidriera de cada cliente; su valor es exactamente su especificidad. **No entra al núcleo. No gastar esfuerzo en parametrizarla.** Sí queda como módulo de referencia para generar la de cada cliente.
- **Única acción pre-extracción:** `hotelInfo.js` como fallback con datos reales de un cliente es un riesgo de filtrado entre instancias (ver F7).

### 🟡 F3 — "Aura" hardcodeado pese a existir `agentName`

- **Qué:** 22 usos en `i18n/chat.js` (los 4 idiomas), header del chat (`ChatWidget.jsx:455`), backoffice (`KnowledgeView.jsx:80`, `DashboardView.jsx:86`, `DetailDrawer.jsx:437`, `PromotionsView.jsx:73`…). `useBusinessProfile.js:32` ya expone `agentName` — nadie lo consume.
- **Resolución:** interpolar `agentName` del business-profile en i18n, header del widget y vistas admin.
- **Esfuerzo:** S. Alto impacto simbólico para la plantilla.

### 🟡 F4 — Dispatcher de cards del chat acoplado al dominio

- **Qué:** `ChatWidget.jsx:549-560` — if-chain `room` / `date_picker` / `menu_interactive` / `table_reservation` / `menu` + imports hoteleros en `:7-11`. Bloquea la extracción del widget, que es el activo frontend más valioso (~70% del archivo es shell genérico de alta calidad: FAB, burbujas, typewriter, 4 idiomas, tema dinámico desde backend, sesión persistente, reconexión WS con backoff).
- **Resolución:** registry de cards inyectable: `const CARD_REGISTRY = { room: RoomCard, ... }` provisto por el dominio; el shell queda rubro-agnóstico. El WS ya es genérico (solo transporta takeover humano, `ChatWidget.jsx:187-232`).
- **Esfuerzo:** M.

### 🟡 F5 — Categorías de conocimiento hoteleras hardcodeadas

- **Qué:** `KnowledgeView.jsx:18-26` (`checkin`, `cancelacion`, `mascotas`…) y `PLACE_CATEGORIES` (`excursion`, `gastronomia`…). El backend ya expone schemas (`/api/agents/training-schemas`, `api.js:896-899`) pero la vista no los usa.
- **Resolución:** consumir las categorías del backend.
- **Esfuerzo:** M.

### 🟡 F6 — `api.js` mezcla core y dominio en 956 líneas

- **Qué:** funciones genéricas (auth, conversations, usage, knowledge, agents, themes) intercaladas con hoteleras (reservations, restaurant, rooms, hotel-tickets en `api.js:223-261`).
- **Resolución:** split en `api/core.js` + `api/hotel.js` (mover funciones, sin cambiar firmas).
- **Esfuerzo:** S-M.

### 🟡 F7 — Fallback de identidad = datos reales del Hampton

- **Qué:** `data/hotelInfo.js:4-15` — dirección, teléfono, email reales del cliente como estado inicial de todo el sitio.
- **Resolución:** reemplazar por perfil neutro placeholder ("Su Negocio", sin datos reales).
- **Esfuerzo:** S. **Hacerlo ya** — riesgo de filtrar datos de un cliente a otro.

### 🟢 Menores frontend

| # | Hallazgo | Evidencia | Esfuerzo |
|---|---|---|---|
| F8 | Código muerto: `admin/views/ConversationsView.jsx` sin importadores (AdminApp usa `LiveConversationsView`, `AdminApp.jsx:30,154`); `presentacion/hampton-wigou.html` duplicado y divergente en `landing/public/presentacion/`; `CATEGORIES` de menú duplicado (`menuShared.jsx` vs `MenuView.jsx:9`) | — | S |
| F9 | Sin TypeScript, sin tests, sin `.eslintrc` (hay un `eslint-disable` huérfano en `ChatWidget.jsx:372`), sin `.env.example` (única env var: `VITE_API_BASE`, `api.js:4`) | — | S (env+lint) / M (TS incremental, opcional) |
| F10 | Storage keys con marca: `hampton_admin_key`, `hampton_auth_token` (`api.js:31,47`), `hampton_chat_session` (`ChatWidget.jsx:32`); package `name: hampton-bariloche-landing` | — | S |
| F11 | Catches que confunden "error" con "vacío" (`.catch(() => [])`, ~11 silenciosos de ~104) en el admin; el toast system existe y es consistente — extenderlo | `KnowledgeView.jsx:53-57` etc. | S |
| F12 | Stack 2023: lucide-react 0.292, Vite 5, Tailwind 3.3.6. Sin CVEs bloqueantes conocidos; bump de menores alcanza por ahora | `package.json` | S |
| F13 | Hash routing sin guards reales (guard admin es client-side, `AdminApp.jsx:104-106`) — aceptable para plantilla; react-router solo si se rehace | `App.jsx:17-22` | — |

---

## 5. La línea de corte para la extracción

### Backend

| Destino | Piezas |
|---|---|
| **Núcleo (copiar tal cual)** | Todo `app/core/` (agents, llm, rag, channels, profile, observability, security); modelos/contratos genéricos (conversaciones, historial, agentes como entidad, skills, training documents, `BusinessProfile`, `CentroConfig`); `instance/bootstrap_instance.py` + YAML; `evals/`; `tests/test_architecture.py` |
| **Módulo de dominio hotelero (separa del núcleo, viaja como ejemplo/plugin)** | `domains/hotel/` completo; los 4 orquestadores de `services/`; `hotel_tools_pkg/`; modelos hoteleros de `models/` (Booking, RoomUnit, HotelTicket, restaurant, room_price, promotions, staff, lead); routers hoteleros; constants de dominio |
| **Rehacer por proyecto** | Tools/handlers del nuevo rubro, prompts del nuevo rubro, modelos de negocio del nuevo rubro, seeds, integraciones de canal específicas del nuevo rubro (plomería enterprise, no IA) |

### Frontend

| Destino | Piezas |
|---|---|
| **Núcleo** | Backoffice "El agente" + "Sistema" (~60-65% del admin): `EmployeeHubSection` + 5 sub-vistas, `LiveConversationsView` + takeover HITL + `HandoffAlert`, `KnowledgeView` (parametrizada, ver F5), `ThemesView`, `LimitsView`/`UsageView`, `AnalyticsView`, `DemoView`, `OnboardingWizard`, `BusinessIdentityView`, `AdminApp` shell, `LoginGate`, `ui.jsx`, `components/`, toast; **ChatWidget shell** (previo F4); `api/core.js` (post F6) |
| **Módulo de dominio hotelero** | `BookingsView`, `HabitacionesView`, `PassengersView`, `TicketsView`, sección restaurante completa, `AsesoriaView`, cards del chat hoteleras, `api/hotel.js` |
| **Rehacer por proyecto** | Toda la landing pública (F2) |

---

## 6. Backlog de remediación PRE-extracción (ordenado de ejecución)

Orden pensado para ejecución secuencial por un agente/dev. Cada ítem es independiente salvo indicación.

| # | Ítem | Ref | Esfuerzo | Por qué en este orden |
|---|---|---|---|---|
| 1 | Cerrar GETs de backoffice sin auth + whitelist explícita de endpoints públicos | C2 | S | Agujero vivo en producción; independiente de todo |
| 2 | Neutralizar datos reales del cliente en frontend (`hotelInfo.js` → placeholder neutro) | F7 | S | Riesgo de filtrado entre clientes; trivial |
| 3 | Reescribir `AGENT_REUSE.md` contra el estado real (usar §5 de este doc como base) | C1 | M | Es el mapa de todo lo que sigue |
| 4 | Pasada de "marca de agua con fecha" en `DEUDA_TECNICA.md` (ítems resueltos listados como pendientes; conteos viejos: 933→974 líneas, 135→289 tests) | §6.1 | S | Fuente de verdad confiable para el resto |
| 5 | Desacoblar arranque: seeds Hampton fuera de `start.sh` y del lifespan; `start.sh` = migraciones + uvicorn | C4 | M | Sin esto no existe núcleo arrancable |
| 6 | Metadata de marca fuera de `main.py` (título, health, nombres de métricas `travel_agent_*`) | M1 | S | Junto con #5 deja el entrypoint neutro |
| 7 | Circuit breaker real de OpenAI envolviendo `run_agent` | C3 | M | La resiliencia es parte del producto núcleo |
| 8 | Token `hilton` → `brand` + valores de tema en un solo archivo | F1 | M | Desbloquea la plantilla visual |
| 9 | "Aura" → `agentName` interpolado (i18n, header chat, vistas admin) | F3 | S | Simbólico y barato |
| 10 | Registry de cards en ChatWidget | F4 | M | Convierte el widget en activo portable |
| 11 | Split `api.js` → `api/core.js` + `api/hotel.js`; categorías de conocimiento desde backend | F5+F6 | M | Define la frontera core/dominio del frontend |
| 12 | Limpieza: borrar `ConversationsView.jsx`, duplicado de `presentacion/`, `app/scripts/001_create_postsale_tables.py`, `app/prompts/` vacío; **remover del repo `ANALISIS_RFI_ASISTENTE_FISCAL.md` y `ANALISIS_RFI_ASISTENTE_FISCAL.pdf`** (pertenecen a otro proyecto — consulta puntual de Grupo San Cristóbal — y quedaron mezclados por error; contienen datos de un tercero); `.env.example`; storage keys y package name neutros; audit log fuera del paquete + `.gitignore` | F8, F10, M7, I8 | S | Higiene de plantilla |
| 13 | Webhooks fail-closed cuando falta credencial + verificación de URL tras proxy | M6 | S | Seguridad del canal |
| 14 | Alembic: backup prod → `stamp 0001` → `upgrade head` en `start.sh` → drop tablas huérfanas → congelar `ensure_column` a tests | I5 | M | Una sola fuente de verdad del esquema |
| 15 | Tests mínimos del hot-path: doble-booking concurrente, 2-3 tests HTTP por router crítico | I7 (mínimo) | L (acotado) | Red de seguridad para los refactors de extracción |

**Al terminar este backlog**, el repo queda en condiciones de armar el plan de extracción del núcleo.

### 6.1 Verificación de la deuda autodeclarada (insumo para ítem #4)

| Ítem de `DEUDA_TECNICA.md` | Estado real verificado |
|---|---|
| Legacy de turismo retirado (Fase 0.2) | ✅ Confirmado |
| Alembic preparado, falta `stamp` | ✅ Vigente (I5) |
| Barrido de marca hardcodeada | ⚠️ Parcial: teléfono postventa y saludos i18n ya resueltos (listados como pendientes); siguen vigentes `hotel_location.py`, voseo, paridad Hampton en `identity_blocks.py` |
| `agent_service.py` "933 líneas" | ⚠️ Drift: hoy 974 |
| Sub-partición fina del dominio | ✅ Vigente (`domains/hotel/{models,orchestrators,tools,seeds}/` vacíos a propósito) |
| `@validator` → `@field_validator` | ✅ Resuelto |

---

## 7. Trabajo que NO hay que hacer antes — es la extracción misma

Hacerlo antes sería doble trabajo; hacerlo durante la extracción es el trabajo:

1. **I1** — limpieza fina de orquestadores (se reescriben como specs al extraer).
2. **I2** — registro explícito de tools por dominio (patrón plugin: `execute_tool` resolviendo `_DISPATCH` según perfil activo).
3. **I4** — inyección de dependencias en orquestadores.
4. **Mover descripciones de tools/handoffs/fallbacks de orquestadores al JSON de perfil** (mayor punto de fricción restante, según el propio plan §9 de AGENT_REUSE).
5. **Interfaz `Gate` abstracta** (hoy el gate post-venta es un patrón clonado, no una abstracción).
6. **Completar el registry de composers** (`resolve_composer` existe en `tool_registry.py` pero no se usa en runtime — los prompts se componen en `_build_instructions` propios de cada orquestador).
7. **Script de scaffolding cookiecutter** para nuevos verticales.
8. **Empaquetar `core/` como distribuible separado** y test de arquitectura adicional que prohíba imports dominio→dominio cuando exista un segundo vertical.

## 8. Puede esperar (post-extracción)

- **I3** (bound de estado global) — importante para multi-tenant real, no bloquea.
- **I6** (guardrail semántico) — la lista actual + `wrap_untrusted_docs` alcanzan para demo.
- **M4/M5** (barrido fino de marca/voseo, `hotel_location` como enricher inyectable) — pertenece a la fase de instanciación.
- **M8** (reemplazo de ChromaDB / deps pesadas) — decisión de empaquetado.
- **F9** (TypeScript incremental en frontend), **F12** (bump de stack), **F13** (react-router).
- Separar config de dominio de config de infra en `config.py` (hoy mezcla settings de LLM con Chroma/Twilio/Meta).

---

## 9. Nota final para el ejecutor

- **No rompas `tests/test_architecture.py`**: es la garantía de que la frontera core/dominio sigue existiendo después de cada cambio. Si un ítem del backlog te tienta a importar dominio desde core, estás yendo en la dirección equivocada.
- **Corré los 289 tests después de cada ítem** (`cd backend && python -m pytest tests/`), y prestá atención especial a los de paridad de prompts al tocar `identity_blocks.py` o `generation_prompts.py` (ítems M4/M5).
- **Si una decisión de refactor duda entre "más genérico" y "más hotelero", elegí genérico**: el norte funcional es la regla de diseño de `VISION_EMPLEADO_DIGITAL.md` — *construir las capacidades como parte del agente base, no como features del hotel*.
- **Ignorá `ANALISIS_RFI_ASISTENTE_FISCAL.md` y su PDF**: pertenecen a otro proyecto (consulta puntual de Grupo San Cristóbal, seguros) y quedaron mezclados en este repo por error. No son un segundo vertical de este producto ni fundamento de ninguna decisión de esta auditoría; están marcados para remoción en el ítem #12.

---

## Anexo — Estado de resolución (2026-07-26, segunda pasada)

Tras la implementación de las tandas 1-3 y el cierre de pendientes (tanda 4), el backlog §6 quedó así:

- **Ítems 1-15: RESUELTOS en código**, salvo el paso operativo de I5 en producción (backup → `alembic stamp` → `upgrade`, con runbook en `DEPLOY_RENDER.md`) y el drop de tablas huérfanas de turismo, que quedan como tarea de deploy.
- **Tanda 4 (este cierre):** M1 (metadata neutra, métricas `empleado_digital_*`), #4 (DEUDA_TECNICA actualizada), #12 completo (limpieza backend + frontend, storage keys migradas con compat, package name neutro), F3 (agentName en todo lo visible), F6 (frontera core/dominio del api corregida), C4 residual documentado.
- **Caveat F5:** `KnowledgeView` enriquece desde `training-schemas` con fallback, pero el endpoint devuelve schemas de *entrenamiento*, no las categorías de conocimiento. Solución completa = endpoint backend que exponga `KNOWLEDGE_CATEGORIES`/`PLACE_CATEGORIES` (queda como tarea futura, no bloquea).
- **Deuda de verificación:** la suite pytest no pudo ejecutarse en el entorno de auditoría (sin venv). `compileall` OK y verificación estática de imports hecha. **Correr `cd backend && python -m pytest tests/ -x -q` en el entorno con dependencias antes de deployar.**

La base queda lista para arrancar el **módulo de extracción de IA** (§7 de este documento).
