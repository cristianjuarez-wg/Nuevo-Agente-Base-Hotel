# Guía de reúso del agente — usar esta base como plantilla para otros dominios

> **Alcance.** Este documento **no refactoriza** la demo de turismo (Freeway/Kami): describe la
> frontera entre el **framework del agente** (reutilizable) y la **lógica de dominio**
> (turismo, a reemplazar), y da una guía paso a paso para arrancar un agente de **otro dominio**
> (ej. soporte bancario, e-commerce, RRHH) usando esta base como molde.
> Audiencia: un dev que va a crear un agente nuevo reusando este patrón.
>
> Las referencias son `archivo:línea` relativas a `backend/`, navegables desde el editor.
> Última verificación de líneas: 2026-06-19.

---

## 1. Dictamen de reusabilidad (TL;DR)

La base **sirve hoy como scaffold informal**: hay un núcleo de infraestructura 100% genérico y un
**patrón arquitectónico portable** (Agents SDK + triage + tools por dispatcher + gate
determinístico + manejo de errores anti-500). La lógica de turismo está **localizada** (prompts,
tools, modelos, geografía), no dispersa — así que reemplazarla es un trabajo acotado y claro.

**[Fase 2.1] Actualización:** ya EXISTE la separación física `core/` vs `domains/hotel/`.
La infra genérica vive en `app/core/{llm,rag,channels,observability,security,profile}/` y un
test permanente (`tests/test_architecture.py`) garantiza que **core/ no importa dominio**. Los
prompts se parametrizan por perfil (identity_blocks + BusinessProfile, Fase 1). Pendiente: la
sub-partición fina del dominio por bounded-context (models/services en subcarpetas de
`domains/hotel/`) — no aporta frontera nueva, se hace incrementalmente.

Semáforo por capa (post Fase 2.1):

| Capa | Estado | Acción al portar |
|---|---|---|
| Infra transversal (`core/llm`, `core/rag`, `core/channels`, `core/observability`, `core/security`) | 🟢 genérico, aislado en core/ | Copiar tal cual |
| Perfil del agente (`core/profile/agent_profile` + BusinessProfile en DB) | 🟢 genérico + configurable | Editar desde el backoffice |
| Orquestación SDK (patrón `run()`, triage, gate) | 🟡 molde | Clonar y adaptar (2.2: runtime declarativo) |
| Tools + dispatcher (`execute_tool`) | 🟡 contrato genérico, handlers de dominio | Reescribir handlers |
| Prompts / textos | 🟡 en `domains/hotel/prompts/`, identidad ya parametrizada | Ajustar textos del vertical |
| Modelos ORM de negocio | 🟡 en `app/models/` (hotel) | Reescribir por vertical |

Veredicto: **~20% framework genérico reutilizable, ~80% capa de dominio a reescribir.** Es lo
esperable: esto se construyó como app de turismo, no como librería. El valor de reusar la base es
**no rehacer el patrón** (SDK loop, ruteo, gate, resiliencia, perfil, infra), que es lo difícil.

---

## 2. El patrón arquitectónico (el molde a reusar)

Flujo de un turno de conversación:

```
agent_service.chat(db, message, session_id)
  ├─ validar entrada
  ├─ rehidratar historial (DB)
  ├─ ¿estado conversacional multi-paso activo? → handler de captura → return
  ├─ CORTOCIRCUITOS DUROS (sin LLM):
  │    código de reserva (regex) | sesión post-venta activa (DB) → post-venta directo
  ├─ TRIAGE (si no hubo señal dura):
  │    triage_sdk_orchestrator.route() → casual | pre-venta | post-venta
  ├─ rama destino:
  │    casual    → _generate_casual_response()
  │    post-venta→ run_gate() [determinístico] → postsale_sdk_orchestrator.run()
  │    pre-venta → agent_sdk_orchestrator.run()
  └─ cada run(): Agent del SDK + tools + guardrails → Runner.run(max_turns=6)
                 → extrae tools_used → catch genérico (NUNCA propaga 500)
```

**Por qué es portable:** `chat()` no depende de FastAPI (recibe una `Session` de SQLAlchemy, no un
`Request`); las tools están desacopladas detrás de un dispatcher; las acciones sensibles se
deciden de forma determinística fuera del LLM.

### Los 4 contratos que un dominio nuevo NO debe romper

1. **Entrada:** `async def chat(self, db, message, session_id) -> Dict` — agnóstica de la capa web.
2. **Dispatcher de tools:** `async def execute_tool(name, args, ctx) -> Dict` — `ctx` es un dict
   **mutable compartido por turno**; el retorno incluye `{"tool_result": str, ...}`.
   (`agent_tools.py:249`, `postsale_tools.py:182`)
3. **Orquestador:** una clase con `async def run(...)` que arma un `Agent` (instrucciones + tools
   `@function_tool` + guardrails), corre `Runner.run(..., max_turns=6)`, extrae `tools_used` de
   `result.new_items` y envuelve todo en un `try/except` con respuesta de fallback.
4. **Gate determinístico:** para acciones sensibles (acceso, dinero, escalación), validar y
   ejecutar **fuera** del LLM. Patrón: `postsale_service.run_gate()` (`:664`) corre antes del loop;
   `postsale_orchestrator._apply_ticket_action()` (`:23`) aplica la acción según lo que el LLM
   *analizó*, pero **el LLM no decide** la acción.

---

## 3. Mapa de capas: framework genérico vs dominio

| # | Capa | Dónde vive | Naturaleza |
|---|---|---|---|
| 1 | Infra transversal | `app/core/` (salvo geografía) | Genérica |
| 2 | Perfil del agente | `core/agent_profile.py` + `data/agent_profiles/*.json` | Genérico (loader) + dominio (instancias) |
| 3 | Orquestación SDK | `services/*_sdk_orchestrator.py` | Patrón genérico, prompts de dominio |
| 4 | Tools + dispatcher | `services/agent_tools.py`, `postsale_tools.py`, `shared_sdk_tools.py` | Contrato genérico, handlers de dominio |
| 5 | Prompts / textos | `app/prompts/` | Dominio |
| 6 | Modelos ORM + config | `app/models/*`, `config.py` | Dominio (salvo `conversation*`/`database.py`) |

---

## 4. El patrón pieza por pieza

### 4.1 Entry point agnóstico — `services/agent_service.py`
`chat(db, message, session_id)` orquesta el turno. Los **cortocircuitos duros** (regex de código
de reserva + consulta de sesión activa) corren antes del LLM y cuestan 0 tokens.
- **Reusable:** la estructura del dispatcher y los cortocircuitos.
- **A tocar:** `BOOKING_CODE_PATTERNS` (`:30`) es el formato de Freeway; las frases sociales de
  fallback (`:269`) dicen "viaje".

### 4.2 Triage por handoffs — `services/triage_sdk_orchestrator.py`
Una sola pasada del SDK con handoffs desambigua pre/post/casual. **~80% agnóstico**: la mecánica
(agentes-marcador + `last_agent`) sirve para cualquier dominio; solo los textos
(`handoff_description` `:57-66` y `_build_triage_instructions` `:71-94`) hablan de "viajes".
Tiene fallback conservador: si el Runner falla, devuelve pre-venta (`:148`).

### 4.3 Patrón de orquestador SDK — `agent_sdk_orchestrator.py` / `postsale_sdk_orchestrator.py`
Estructura común de `run()`: arma instrucciones, registra tools con `@function_tool`, define
guardrails, corre `Runner.run(max_turns=6)`, extrae `tools_used` con
`getattr(result, "new_items", [])`, y atrapa toda excepción con un fallback amable.
- **Reusable:** toda esa estructura (es el "esqueleto" del agente).
- **A tocar:** las descripciones de tools (`agent_sdk_orchestrator.py:105-126`), los fallbacks de
  dominio (`:341-351`) y el análisis de lead (`_build_lead_block`).

### 4.4 Tools + dispatcher — `agent_tools.py`, `postsale_tools.py`
Las `@function_tool` del orquestador son finas: delegan en handlers vía
`execute_tool(name, args, ctx)`. El `ctx` lleva `service`, `db`, `message`, `history` y las tools
escriben ahí lo que el orquestador necesita después (ej. `escalation_analysis`, `flight_issues`).
- **Reusable:** el dispatcher y el contrato del `ctx`.
- **A reescribir:** los handlers (`buscar_paquetes`, `consultar_estado_vuelo`, etc.) son turismo.

### 4.5 Gate determinístico — `postsale_service.run_gate()` + `_apply_ticket_action()`
Antes del loop LLM, `run_gate()` (`:664`) valida acceso (código de reserva, voucher) y devuelve
`{"handled": True, "result": ...}` (respuesta terminal) o `{"handled": False, "package", "ticket", ...}`
(seguir al loop). La acción final sobre el ticket la aplica `_apply_ticket_action()` (`:23`) de
forma **determinística**. Patrón clave para **dominios regulados** (banca, salud): el LLM analiza,
pero la acción sensible la decide código auditable.

### 4.6 Perfil del agente — `core/agent_profile.py` + `data/agent_profiles/template.json`
`AgentProfileManager` es 100% genérico: carga y valida JSON, permite `switch_profile()` en runtime.
Ya hay un `template.json` con placeholders `{agent_name}`, `{domain}`, `{custom_instructions}`,
`{context}`, `{chat_history}`. **Este es el molde del perfil**: `turismo.json` y `postventa.json`
son instancias. Campos requeridos: `profile_name`, `domain`, `system_prompt_template`,
`agent_name`, `greeting_message`, `no_info_response`.

### 4.7 RAG agnóstico — `services/rag_service.py` + `services/vector_store.py`
El RAG en sí (búsqueda semántica, dedupe, thresholds) es agnóstico. **Solo** el enrichment
geográfico (`core/geography.py`, `core/intelligent_geography.py`) es turismo. Para otro dominio:
reusar el RAG, quitar/reemplazar el enricher geográfico.

---

## 5. Guía paso a paso: crear un agente de un dominio nuevo

Caso ejemplo: **soporte bancario**. Orden recomendado (cada paso indica qué tocás y qué NO):

1. **Perfil de dominio.** Copiar `data/agent_profiles/template.json` →
   `data/agent_profiles/banca.json`. Completar `domain`, `agent_name`, `system_prompt_template`,
   `greeting_message`, `capabilities`, `conversation_starters`. Apuntar `AGENT_PROFILE_PATH`
   (`config.py:36`) a ese archivo. *NO tocás* `agent_profile.py`.

2. **Config.** En `config.py`: `CHROMA_COLLECTION_NAME` (`:21`, hoy `"travel_documents"`) →
   colección del dominio; eliminar/ignorar `FLIGHTAPI_API_KEY` (`:7`), `WEATHER_API_KEY` (`:8`),
   `GEOGRAPHY_DATA_PATH` (`:37`) si no aplican. *NO tocás* los settings de infra (modelo, retries,
   circuit breaker, logging).

3. **Modelos de negocio.** Reemplazar `models/postsale.py`, `models/lead.py`, `models/provider.py`
   por los del dominio (ej. `Account`, `Transaction`, `Case`). *Conservás tal cual*
   `models/conversation.py`, `models/conversation_message.py`, `models/database.py`.

4. **Tools del dominio.** Crear `services/banca_tools.py` con handlers que respeten el contrato
   `(args, ctx) -> {"tool_result": ...}` y un `_DISPATCH` + `execute_tool` como en `agent_tools.py`.
   Ej.: `consultar_saldo`, `ultimos_movimientos`, `bloquear_tarjeta`.

5. **Orquestador(es).** Clonar el patrón de `agent_sdk_orchestrator.py` (y `postsale_sdk_orchestrator.py`
   si hay flujo "ya cliente"): envolver las nuevas tools con `@function_tool`, mantener
   `max_turns`, el catch genérico y la extracción de `tools_used`. *NO cambiás* la mecánica del SDK.

6. **Gate determinístico** (banca casi seguro lo necesita). Replicar el patrón `run_gate()` +
   `_apply_ticket_action()`: validar identidad/autorización antes del LLM y ejecutar acciones
   sensibles (transferencias, bloqueos) de forma determinística y auditable.

7. **Prompts y textos.** Reescribir `prompts/tool_agent_prompts.py` (`:17-64`),
   `prompts/postsale_tool_prompts.py` (`:16-52`), `prompts/generation_prompts.py` (`:6`,
   "Aura Travel"), `prompts/context_blocks.py`. Y los prompts hardcodeados en los orquestadores
   (ver §7).

8. **Triage.** Editar `handoff_description` (`triage_sdk_orchestrator.py:57-66`) y
   `_build_triage_instructions` (`:71-94`) con las categorías del dominio (ej. consulta general /
   gestión de cuenta existente / charla casual).

9. **Guardrails.** Conservar el guardrail de jailbreak (genérico). Reemplazar
   `paises_disponibles_monitor` (`agent_sdk_orchestrator.py:156`) por el guardrail del dominio
   (o quitarlo si no aplica).

10. **Verificación.** Recorrer el checklist §7 y hacer un smoke test de un turno por rama
    (casual / pre / post / gate), levantando el backend y pegando a `POST /api/chat/message`
    (recordá: `session_id` de ≥ 8 caracteres).

---

## 6. Tabla: copiar tal cual vs reescribir

| Componente | Archivo | Acción |
|---|---|---|
| Cliente OpenAI singleton | `core/openai_client.py` | **Copiar tal cual** |
| Circuit breaker | `core/circuit_breaker.py` | **Copiar tal cual** |
| Retry config | `core/retry_config.py` | **Copiar tal cual** |
| Logging | `core/logging_config.py` | **Copiar tal cual** |
| Profile manager | `core/agent_profile.py` | **Copiar tal cual** |
| DB setup | `models/database.py` | **Copiar tal cual** |
| Historial de conversación | `models/conversation.py`, `conversation_message.py` | **Copiar tal cual** |
| Vector store | `services/vector_store.py` | **Copiar tal cual** |
| Estado conversacional (FSM) | `services/conversation_state_manager.py` | **Copiar tal cual** |
| RAG | `services/rag_service.py` | **Copiar** (quitar enricher geográfico) |
| Entry / dispatcher de chat | `services/agent_service.py` | **Parametrizar** (booking patterns, fallbacks) |
| Triage | `services/triage_sdk_orchestrator.py` | **Parametrizar** (prompts/handoffs) |
| Patrón de orquestador | `services/*_sdk_orchestrator.py` | **Molde** (clonar, reescribir tools/prompts) |
| Gate determinístico | `services/postsale_service.py` (`run_gate`), `postsale_orchestrator.py` (`_apply_ticket_action`) | **Molde** |
| Perfil JSON | `data/agent_profiles/template.json` | **Molde** (crear instancia del dominio) |
| Tools del dominio | `services/agent_tools.py`, `postsale_tools.py`, `shared_sdk_tools.py` | **Reescribir** |
| Prompts | `app/prompts/*` | **Reescribir** |
| Modelos de negocio | `models/postsale.py`, `lead.py`, `provider.py` | **Reescribir** |
| Geografía | `core/geography.py`, `core/intelligent_geography.py` | **Reescribir / quitar** |
| Config de dominio | `config.py` (keys de §5.2) | **Reescribir** |

---

## 7. Checklist de acoplamiento (definition of done al portar)

- [ ] Prompts turismo: `prompts/tool_agent_prompts.py:17-64`, `prompts/postsale_tool_prompts.py:16-52`, `prompts/generation_prompts.py:6` ("Aura Travel"), `prompts/context_blocks.py`
- [ ] Prompts en orquestadores: `triage_sdk_orchestrator.py:57-94`, `agent_sdk_orchestrator.py:105-126` y `:341-351`, `postsale_sdk_orchestrator.py:102,263`
- [ ] Tools: `agent_tools.py`, `postsale_tools.py`, `shared_sdk_tools.py` (`obtener_clima`)
- [ ] Modelos ORM de negocio: `models/postsale.py`, `models/lead.py`, `models/provider.py`
- [ ] Geografía: `core/geography.py`, `core/intelligent_geography.py`
- [ ] Config: `CHROMA_COLLECTION_NAME:21`, `AGENT_PROFILE_PATH:36`, `GEOGRAPHY_DATA_PATH:37`, `FLIGHTAPI_API_KEY:7`, `WEATHER_API_KEY:8`
- [ ] Guardrail de dominio: `paises_disponibles_monitor` en `agent_sdk_orchestrator.py:156`
- [ ] `BOOKING_CODE_PATTERNS` (`agent_service.py:30`) y frases sociales de fallback (`:269`)
- [ ] Perfil JSON nuevo en `data/agent_profiles/` + `AGENT_PROFILE_PATH` apuntando a él

---

## 8. Qué NO copiar (artefactos de la demo)

- Datos/persistencia: `*.db` (`documents.db`, `aura_travel.db`), `chroma_db*/`, `vouchers/`,
  `uploads/`, backups (`*.backup*`).
- Scripts de la demo: `scripts_archive/`, `reset_demo_2026.py`, `add_missing_providers.py`, seeds.
- Reportes/diagnósticos específicos: `REPORTE_*`, `ANALISIS_*`, `DIAGNOSTICO_*`, `OBSERVABILIDAD.md`
  (este último, regenerarlo por dominio).
- Integraciones externas no portables sin reemplazo: clientes de vuelos/clima
  (`flightapi_client.py`, `aviationstack_client.py`, `weather_service.py`) y servicios de turismo
  (`package_service`, `flight_monitor_service`, etc.).

---

## 9. Recomendaciones de desacople futuro (NO ejecutar ahora)

Si en algún momento se quiere convertir esto en un **scaffold formal** (no solo un molde
documentado), en orden de impacto:

1. **Parametrizar prompts y handoffs por perfil.** Hoy es el mayor punto de fricción: los textos
   viven hardcodeados en los orquestadores. Moverlos a campos del JSON de perfil (descripciones de
   handoff, descripciones de tools, fallbacks) haría que cambiar de dominio sea casi solo editar
   JSON.
2. **Registro de tools por dominio.** Que `execute_tool` resuelva su `_DISPATCH` según el perfil
   activo, en vez de un módulo de tools fijo por orquestador (patrón plugin).
3. **Abstraer una interfaz `Gate`.** Extraer "validar acceso + aplicar acción determinística" como
   interfaz, para que cada dominio implemente la suya sin clonar `postsale_service`.
4. **Sacar la geografía del core.** Convertirla en un "enricher" opcional inyectable en
   `rag_service`, no una dependencia del core.
5. **Agrupar la config de dominio.** Separar en `config.py` un bloque de settings de dominio
   (colección Chroma, keys externas, paths) del `Settings` base de infra.
6. **Externalizar `BOOKING_CODE_PATTERNS` y frases sociales** a config/perfil.
7. **(Opcional) Script de scaffolding** (cookiecutter) que genere `{dominio}_tools.py`,
   `{dominio}_sdk_orchestrator.py` y `{dominio}.json` desde el molde.

> Estas mejoras son independientes entre sí y se pueden hacer incrementalmente. Ninguna es
> necesaria para usar la base como plantilla hoy.
