# Guía de reúso — construir un agente de OTRO rubro sobre esta base

> **Verificado contra el código el 2026-07-26.** Todas las rutas citadas existen. Si encontrás
> una que no, el documento se desactualizó: arreglalo antes de seguir (la versión anterior de
> esta guía mandaba a copiar ~20 archivos que ya no existían — hallazgo C1 de la auditoría).

Este repo implementa un "empleado digital" para hoteles. Lo reusable **no es el hotel**: es el
**runtime declarativo de agentes** (`app/core/agents/`) más la infraestructura alrededor (LLM,
RAG, canales, seguridad, observabilidad). Un rubro nuevo **declara sus agentes y escribe sus
tools**; no clona orquestadores.

---

## 1. La regla de oro: la frontera core ↔ dominio

`tests/test_architecture.py` falla si un archivo de `app/core/` importa de `app.domains`,
`app.services`, `app.prompts` o `app.routers`. Única excepción: una whitelist de modelos de
infraestructura (`app.models.database`, `.schemas`, `.conversation*`, `.admin_user`).

**El dominio importa core; core NUNCA importa dominio.** Por eso las tools del dominio se
*registran* (`register_tool`) en vez de importarse desde core.

Si un cambio te tienta a romper esa regla, estás yendo en la dirección equivocada.

---

## 2. Los 4 pasos para agregar un agente

El ejemplo canónico es el agente más simple del repo: **`hotel_staff`** (3 tools,
`app/services/staff_orchestrator.py`, ~235 líneas). Ese es el patrón a copiar.

### Paso 1 — Escribir las tools con `@function_tool`

```python
# app/services/<rubro>_orchestrator.py
from agents import RunContextWrapper, function_tool

class MiContext:                      # contexto del turno: clase plana propia del dominio
    def __init__(self, db, usuario, message, session_id=""):
        self.db, self.usuario, self.message, self.session_id = db, usuario, message, session_id

@function_tool
async def resolver_algo(ctx: RunContextWrapper[MiContext], referencia: str, nota: str = "") -> str:
    """El DOCSTRING ES EL PROMPT que ve el modelo: explicá cuándo usar la tool y qué significa
    cada parámetro. La lógica de negocio NO va acá: delegá a un service."""
    return mi_service.hacer_algo(ctx.context.db, referencia, nota)
```

Referencia real: `app/services/staff_orchestrator.py:56-124` (las 3 tools) y el contexto en `:45-50`.

### Paso 2 — Registrar las tools

```python
_TOOLS = [resolver_algo, otra_tool]
from app.core.agents.tool_registry import register_tool
for _t in _TOOLS:
    register_tool(f"mirubro.{_t.name}", _t)      # convención: "<rol>.<nombre_funcion>"
```

Ver `app/services/owner_orchestrator.py:532-536` (idiom en bucle, el recomendado).

⚠️ **El registro corre como side-effect del import del módulo.** Si nadie importa tu orquestador,
`resolve_tools` lanza `KeyError: Tools no registradas: [...]`
(`app/core/agents/tool_registry.py:41-45`). En tests, importá el módulo explícitamente.

### Paso 3 — Declarar la spec (el agente como DATOS)

```python
# app/domains/<rubro>/agent_specs.py
SPECS = {
  "mi_agente": AgentSpec(
      key="mi_agente",
      display_name="Coordinador",
      display_role="staff",              # "guest" | "management" | "staff"
      engine="sdk",                      # "sdk" (con tools) | "completions" (sin tools)
      model_setting="OPENAI_MODEL",      # NOMBRE del atributo en settings, no el valor
      temperature=0.4,
      max_turns=5,
      max_history=10,
      tools=("mirubro.resolver_algo", "mirubro.otra_tool"),
      channels=("whatsapp",),
  ),
}
```

Campos completos: `app/core/agents/agent_spec.py:17-37`. Ejemplo real:
`app/domains/hotel/agent_specs.py:17-29`.

Detalle de diseño: `model_setting`/`temperature_setting` guardan el **nombre del atributo de
settings**, no el valor — así el modelo no queda hardcodeado en la spec.

### Paso 4 — Orquestador FINO: componer instructions + llamar `run_agent`

```python
from app.core.agents.sdk_runtime import run_agent, build_input_list
from app.domains.mirubro.agent_specs import SPECS

async def run(self, db, usuario, message, session_id, history):
    spec = SPECS["mi_agente"]
    out = await run_agent(
        spec,
        instructions=self._build_instructions(db, usuario),   # tu prompt compuesto
        context=MiContext(db, usuario, message, session_id=session_id),
        input_list=build_input_list(history, message, spec.max_history),
        fallback_response="Disculpá, tuve un problema. ¿Podés repetirlo?",
    )
    return {"response": out["response"], "tools_used": out["tools_used"], "usage": out["usage"]}
```

Referencia real: `app/services/staff_orchestrator.py:204-232` (el `run()` completo son ~20 líneas).
**Eso es todo**: el orquestador compone el prompt y adapta el resultado.

---

## 3. Qué te da el runtime (y qué no)

`run_agent` (`app/core/agents/sdk_runtime.py:43`) hace por vos:

- Construye el `Agent` del SDK con tools, modelo, temperatura y guardrails resueltos desde la spec.
- Corre el loop (`Runner.run` con `max_turns`) **envuelto en el circuit breaker de OpenAI**
  (`sdk_runtime.py:81-90`): si el proveedor se cae, tras N fallos el circuito abre y los turnos
  siguientes fallan rápido en lugar de esperar el timeout completo.
- Extrae `usage` (tokens/costo) y `tools_used`.
- Catch anti-500 con `fallback_response` + log estructurado.

**Devuelve** `{"response", "tools_used", "usage", "result", "agent_key", "error"}`. `result` es el
objeto crudo del Runner, para que el orquestador extraiga lo que dejó el contexto.

**Contrato de excepciones:** si NO pasás `fallback_response`, las excepciones **se propagan**
(incluida `InputGuardrailTripwireTriggered`) y decidís vos. Así post-venta responde con su propio
mensaje ante un jailbreak (`app/services/hotel_postsale_orchestrator.py:614-628`).

**NO hace** (queda en tu orquestador): componer el prompt, el post-procesamiento de dominio
(acciones sobre tickets, flags, charts) y el manejo específico del tripwire.

---

## 4. El núcleo, módulo por módulo (se copia tal cual)

| Paquete | Qué provee |
|---|---|
| `app/core/agents/` | **La pieza clave.** `agent_spec.py` (AgentSpec), `sdk_runtime.py` (`run_agent`, `build_input_list`), `tool_registry.py` (`register_tool`/`resolve_tools`, guardrails) |
| `app/core/llm/` | `openai_client.py` (singletons), `circuit_breaker.py`, `retry_config.py`, `sdk_usage.py` (tokens), `token_pricing.py` (costo USD) |
| `app/core/rag/` | `rag_service.py`, `vector_store.py` (ChromaDB), `embeddings.py` (caché LRU), `text_splitter.py`, `pdf_processor.py`, `llm_metadata_extractor.py`, `knowledge_extractor.py` |
| `app/core/channels/` | `whatsapp_service.py` (Twilio), `instagram_service.py` (Meta), `ws_hub.py` (WebSocket al widget) |
| `app/core/profile/` | `agent_profile.py` — carga el JSON de `settings.AGENT_PROFILE_PATH` (los JSON viven en `backend/data/agent_profiles/`) |
| `app/core/observability/` | `logging_config.py` (structlog), `audit_log.py` (JSONL por turno; escribe en `settings.AUDIT_LOG_DIR`, fuera del paquete porque lleva PII), `otel_setup.py` |
| `app/core/security/` | `auth.py` (bcrypt + JWT), `admin_auth.py` (`require_admin_key`, fail-closed en producción), `rate_limit.py` |
| `app/core/origin.py` | Modelo de origen `generated_by` × `channel` (genérico) |

---

## 5. Instanciar para un cliente NUEVO del mismo rubro (sin tocar Python)

Distinto de "hacer un rubro nuevo". Mecanismo: `instance/bootstrap_instance.py` + un YAML.

```bash
python -m instance.bootstrap_instance instance/<cliente>.yaml
```

Idempotente. Ejemplos: `instance/hampton.yaml` (hotel real, USD/ARS, voseo rioplatense) y
`instance/demo2.yaml` (**pousada en Brasil, pt_BR, BRL** — la prueba de que se da de alta un
cliente nuevo sin tocar código). Plantilla comentada: `instance/instance.example.yaml`.

Bloques que configura (mapa en `instance/bootstrap_instance.py:33-52`):
- **`business:`** → `BusinessProfile`: nombre, marca, nombre del agente, timezone, locale, idioma,
  dialecto, ciudad, monedas, contacto y `facts` (hechos duros que el agente no puede contradecir).
- **`rooms:`** → catálogo + unidades físicas + precios por moneda. *Para otro rubro, este bloque se
  reemplaza por el catálogo que corresponda.*
- **`admin:`** → usuario admin inicial (la password llega por env `BOOTSTRAP_ADMIN_PASSWORD`,
  nunca en el YAML).

**Lo que el YAML NO configura** (la línea divisoria): tools, specs, prompts base y lógica de
negocio. El cliente configura los **bloques que se inyectan** al prompt (tono, política,
identidad, entrenamiento), no el cerebro.

> Los bloques `flow_variant:` y `channels:` aparecen en los YAML pero `bootstrap_instance`
> todavía **no los lee** (solo consume `business`, `rooms` y `admin`).

---

## 6. Qué es hotelero (lo que un rubro nuevo reescribe)

- `app/domains/hotel/` — `agent_specs.py`, `agent_capabilities.py`, `hotel_location.py`,
  `prompts/` (10 módulos, ~1.700 líneas) y `services/` (`agent_router.py`, `casual_agent.py`,
  `knowledge_service.py`).
- Orquestadores en `app/services/`: `hotel_sdk_orchestrator.py` (pre-venta),
  `hotel_postsale_orchestrator.py`, `owner_orchestrator.py`, `staff_orchestrator.py` (**empezá
  leyendo este**) y `triage_sdk_orchestrator.py`.
- `app/services/hotel_tools_pkg/` — handlers con contrato `(args, ctx) -> {"tool_result": str}`.
- Modelos de negocio en `app/models/` (`hotel.py`, `restaurant.py`, `promotions.py`, `staff.py`,
  `lead.py`…) y sus routers en `app/routers/` (`reservations.py`, `restaurant.py`, `checkin.py`…).
- Los `seed_*.py` de la raíz de `backend/`.

Genéricos y reusables con poca adaptación: `app/routers/{chat,auth,admin,documents,knowledge,
analytics,usage,whatsapp,instagram,conversations,agents,business_profile,contacts}.py` y los
servicios transversales (`usage_service`, `skill_service`, `business_profile_service`,
`conversation_*`, `human_attention_service`, `training_service`…).

---

## 7. Dos advertencias (andamiaje que parece existir y no)

1. **`prompt_composer` NO está cableado.** El campo existe en `AgentSpec` y las 6 specs lo setean,
   pero `register_composer`/`resolve_composer` (`tool_registry.py:54,59`) **no se invocan en ningún
   lado**. Cada orquestador arma su prompt en su propio `_build_instructions`. Para un rubro nuevo:
   **escribí tu `_build_instructions`**, no registres un composer.
2. **`app/domains/hotel/{orchestrators,models,tools,seeds}/` están VACÍOS** (solo `__init__.py`).
   Son el destino planeado de una migración que no se hizo: hoy los orquestadores viven en
   `app/services/` y los modelos en `app/models/`. No los cites como si tuvieran contenido. Ídem
   `app/prompts/` (el contenido está en `app/domains/hotel/prompts/`).

---

## 8. Checklist al portar a un rubro nuevo

- [ ] `pytest tests/test_architecture.py` verde (no rompiste la frontera core↔dominio).
- [ ] Tus tools están registradas y el módulo que las registra se importa en el arranque.
- [ ] `spec.tools` coincide con tu `_TOOLS` real — el patrón de
      `tests/test_spec_runtime_consistency.py` atrapa ese bug (reincidió 2 veces en este repo).
- [ ] El orquestador es fino: compone prompt + llama `run_agent`. Si supera ~250 líneas, revisá qué
      lógica de negocio se te coló ahí.
- [ ] `start.sh` sigue siendo rubro-agnóstico (migraciones + servidor). Los datos del cliente se
      cargan con `bootstrap_instance`, nunca en el arranque.
- [ ] Cero datos reales de un cliente hardcodeados (backend o frontend).
- [ ] Frontend: usá el token `brand-*` (definido en `landing/theme.config.js`) y el nombre del
      agente vía `useAgentName()` — nunca literales de marca.

---

## Modelos: por qué viven en `app/models/` (no en `domains/hotel/models/`)

`app/domains/hotel/models/` existe pero está vacío a propósito. Los modelos (Room, Booking,
StaffMember, Contact, etc.) viven en `app/models/`, con registro centralizado vía
`ensure_domain_models_registered()` (`app/models/__init__.py`). El orden de registro es sensible
(staff → restaurant → hotel → contact...) porque hay FKs cross-módulo declaradas por string y
`hotel.py` hace `create_all` a nivel de módulo; ya hubo una regresión por esto (ver el docstring de
`ensure_domain_models_registered`).

**Decisión (P4.1):** NO se mueven a `domains/hotel/models/`. El beneficio sería estético; el costo
es real y alto (mover 10 modelos con FKs por string, reordenar el registro y el barrido del
conftest, arriesgar otra regresión de mappers). El registro centralizado funciona y está cubierto
por `test_architecture.py`. Si algún día se mueven, hacerlo con `git mv` uno por vez, import-check
tras cada uno, y actualizando el orden de registro en el mismo commit del primer movimiento.

---

## Contrato de privacidad: qué datos del huésped ve cada rol (Fase 1 — Capa 2)

Los datos del huésped (Capa 2: estadías, preferencias, recurrencia, gasto, `ai_summary`) se
inyectan en el prompt del agente a través de un ÚNICO helper con niveles de acceso por rol:
`guest_context_service.build_guest_context(agent_role, contact_id, db)`. Es el único lugar donde se
decide qué ve cada rol — la política de privacidad está centralizada, no dispersa.

| Rol (`display_role`) | Empleado | Qué ve del huésped EN EL PROMPT |
|---|---|---|
| `guest` | Aura (pre-venta, post-venta, casual) | Perfil 360 completo: estadías, recurrencia, habitación preferida, preferencias, consumo, alergias, y el `ai_summary` si existe. |
| `management` | Asesor | **Nada individual.** `build_guest_context("management", ...)` devuelve `""` siempre. Gerencia trabaja con agregados. |
| `staff` | Operaciones | **Mínimo:** nombre + habitación del ticket, y alergias (seguridad). Nada comercial (sin gasto, consumo, recurrencia ni preferencias de venta). |

**Precisión de la garantía (importante, no vender de más):** el nivel `management` garantiza que el
PROMPT del owner **no inyecta datos individuales de forma pasiva**. NO garantiza que gerencia no
pueda consultar un huésped a propósito: la tool `buscar_huesped` (`owner_orchestrator.py`) devuelve
nombre/reserva/fechas de una reserva puntual cuando el dueño la invoca. Eso es una acción
deliberada del dueño (buscar una reserva para operar), no una fuga. El test de privacidad valida el
prompt, no prohíbe la tool.

**`ai_summary` (Fase 1):** el agente solo LEE el resumen que ya generó el backoffice; no se
regenera en runtime (evita latencia/costo por turno). La regeneración automática es un posible
sub-hito futuro.
