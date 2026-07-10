# Deuda técnica — backlog documentado

Registro de deuda técnica conocida y decisiones de no-hacer-ahora, surgido de la auditoría
profunda del sistema. Lo ya resuelto está marcado; lo pendiente queda especificado para
encararlo cuando corresponda (sin re-investigar).

## Resuelto en la auditoría
- **P0** — personalización del huésped en el saludo, captación de lead en el cierre,
  post-venta que informa políticas (RAG) en vez de escalar, `except:` desnudos logueados.
- **P1** — service routing (tickets de servicio al staff), upselling natural, lock pesimista
  anti doble-booking, toasts de feedback en el backoffice.
- **P2 (parcial)** — métricas de containment del agente (ahora sobre `HotelTicket`, no el
  `SupportTicket` legacy) + sección "Calidad del agente" en Analíticas; code-split del
  backoffice (bundle inicial 536 KB → 123 KB; AnalyticsView/AgentSection lazy).

## RESUELTO — código legacy de turismo (Fase 0.2, 2026-07-09)
El proyecto evolucionó de turismo a hotel. Se retiró todo el código legacy de turismo:
- **Modelos borrados:** `postsale.py` completo (SoldPackage, SupportTicket, TourPackage,
  y los 10 sub-modelos de paquetes/vuelos/tickets), `provider.py` (Provider/ProviderContact),
  `flight_tracking.py`, `airport_terminal.py`, `geography.py` (GeographicMapping),
  `learning_opportunity.py`. `models/__init__.py` quedó solo con `AgentSnapshot`.
- **Servicios borrados (10):** `postsale_service`, `package_service`, `package_validator`,
  `postsale_vector_store`, `maps_service`, `terminal_discovery_service`, `provider_service`,
  `learning_service`, `geographic_mapping_service`, `voucher_service` (el de turismo; el
  voucher del restaurante vive en `restaurant_service.create_voucher`).
- **Routers borrados:** `postsale.py`, `learning.py`, `providers.py` (ya desmontados/ausentes
  de main.py; se quitaron las 2 líneas comentadas decorativas).
- **Orquestadores fantasma:** `agent_sdk_orchestrator`/`postsale_sdk_orchestrator` ya NO
  existían — solo se limpiaron referencias colgadas en comentarios.
- **kanban NO se tocó:** es el pipeline de leads del HOTEL (`Lead.kanban_stage`), no turismo.
- **Queries muertas retiradas:** `contacts.py` (desvinculación de SoldPackage al borrar
  contacto) y `contact_service`/`summary_service` (historial de paquetes por teléfono) —
  las tablas estaban vacías en el hotel. El payload de contacto conserva `packages`/`tickets`
  vacíos por compatibilidad.

**Verificación:** `from app.main import app` OK, 135/135 tests verde, startup completo sin
errores, smoke en vivo de la ruta casual OK. **Tablas NO dropeadas** (DB de producción
Render): quedan huérfanas hasta la Fase 2 (Alembic), donde se documenta su drop opcional.

## Alembic — PREPARADO en código (Fase 2.4), falta el paso de producción
Setup LISTO: `alembic/` + `alembic.ini` + revisión `0001_baseline` (crea el esquema completo
desde `Base.metadata`, verificado en SQLite limpia → 36 tablas). `env.py` lee la URL de
`settings.DATABASE_URL` y registra todos los modelos. Ver **RUNBOOK_ALEMBIC.md**.

**Falta (toca producción, se hace a mano con backup):** correr `alembic stamp 0001_baseline`
sobre la DB de Render para marcar el baseline como aplicado sin recrear tablas. El runbook
tiene el procedimiento exacto (backup con pg_dump → stamp → verificar). No se automatizó a
propósito: es el único paso que toca datos reales.

**A futuro:** toda columna/tabla nueva = revisión Alembic (`ensure_column` queda solo para
tests/dev). Activar `alembic upgrade head` en `start.sh` cuando se valide en staging.

### (histórico) Por qué no se había migrado antes
Hoy el esquema evoluciona con `run_light_migrations()` (`ensure_column` idempotente).
Limitación: sin versionado ni rollback. Introducir Alembic sobre la DB de producción requiere
baseline + backup — delicado, por eso se preparó todo salvo el stamp final.

**Plan cuando se haga:** (1) `alembic init`, configurar `env.py` con el `Base.metadata` y la
`DATABASE_URL`; (2) `alembic revision --autogenerate` para el baseline y marcarlo como
aplicado (`alembic stamp head`) en la base existente sin re-crear tablas; (3) a partir de ahí,
toda columna nueva va por una revisión Alembic en vez de `ensure_column`; (4) conservar
`ensure_column` para entornos efímeros/tests. Hacer con backup de la DB de Render.

## Pendiente — barrido fino de marca hardcodeada (Fase 1, residual)
La Fase 1 parametrizó desde el BusinessProfile lo de mayor impacto: los ENCABEZADOS de
identidad de los 5 prompts de agente, el timezone, y la moneda mostrada en las cards.
Quedan menciones de marca hardcodeadas de MENOR impacto, a barrer en la fase de instancia
(Fase 3) o cuando se onboardee el primer cliente real:
- **App metadata** (`main.py`: título FastAPI, logs de arranque, `/` root) — cosmético.
- **Fallbacks de error** (`agent_service.py:595`, `hotel_sdk_orchestrator`, `hotel_postsale_orchestrator`)
  con "Hampton" — solo se ven ante un error; parametrizar desde el perfil.
- **Saludos i18n EN/PT/FR** (`chat.py:_GREETINGS`) con la marca embebida.
- **Límites de dominio casual/pre-venta** (`base_blocks.py`) con "Hampton by Hilton Bariloche"
  — parametrizables, pero tocan la paridad de los tests de Fase 0; hacer con cuidado.
- **Nombre del restaurante** ("PLAZA - Hampton's Kitchen House") en tools/prompts — es un
  DATO del cliente; debería salir del perfil/RAG, no de constantes.
- **Contexto de negocio del owner** (estacionalidad/economía de Bariloche) — específico del
  Hampton; se reemplaza vía material de entrenamiento del cliente.
Ninguno bloquea el objetivo de la fase (identidad/moneda/timezone configurables): son el
"último 20%" de exhaustividad.

### Hallazgo del test de aceptación (dialecto no 100% efectivo)
En el test en vivo con un perfil `es_neutro`, el nombre/negocio/moneda cambiaron bien, PERO
el saludo casual seguía usando voseo ("¿vos cómo andás?"). Causa: el `NATURALIDAD_BLOCK`
(compartido casual+pre-venta, `generation_prompts.py`) trae EJEMPLOS de tono con voseo
rioplatense hardcodeado, que el modelo imita por encima de la instrucción `{dialect_block}`.
Fix pendiente: parametrizar los ejemplos del NATURALIDAD_BLOCK por dialecto (o quitarlos
para dialectos != voseo). La instrucción de dialecto SÍ llega; el problema son los ejemplos
que compiten. Impacto: un cliente no-rioplatense verá al agente "vosear" en small talk hasta
que se haga este fix.

## Pendiente — sub-partición fina del dominio (Fase 2.1, resto)
La Fase 2.1 logró lo central: separar `core/` (framework) de `domains/hotel/`, con un test
de arquitectura permanente (`tests/test_architecture.py`) que impide que core/ importe
dominio. Se movieron: infra a `core/{llm,rag,channels,observability,security,profile}/`,
prompts a `domains/hotel/prompts/`, y varios módulos de dominio (hotel_location, geography,
agent_router, knowledge_service) a `domains/hotel/`.

**Pendiente (cosmético, no cruza frontera arquitectónica):** mover el resto del dominio que
sigue en `app/models/`, `app/services/` y los orquestadores a las subcarpetas de
`domains/hotel/` (models/, services/booking/, services/restaurant/, orchestrators/, seeds/).
Esto NO agrega ninguna frontera nueva (el check ya pasa) y toca decenas de imports internos
con riesgo mecánico; se hace incrementalmente cuando convenga, no bloquea nada. Los models
tienen create_all a nivel de módulo + FKs entre sí, así que moverlos requiere cuidado extra.

## agent_service.py y el objetivo "<400 líneas" de Fase 2.3
El plan (2.3) fijó como meta dejar `agent_service.py` en <400 líneas. Tras cerrar la deuda de
Fase 2 quedó en **933**, y ESO es lo correcto, no un incumplimiento:
- Se retiró el código muerto de turismo (`_handle_conversation_state`, captura de leads de
  eventos, inalcanzable en el hotel): 1202 → 1071.
- Se extrajo el agente casual a `domains/hotel/services/casual_agent.py`: 1071 → 933.
- El **store de historial** (rehidratación/persistencia, ~190 líneas) NO se extrajo a propósito:
  está acoplado a la API pública que consumen 3 módulos externos (`chat.py`, `agent_router`,
  `conversations`) vía `agent_service.conversation_history` / `_save_message_to_db`. Extraerlo
  sería alto riesgo por beneficio cosmético; se difiere hasta que haya otra razón para tocar
  esos call-sites.
- Lo que queda (`_chat_impl` ~300 líneas + interceptores + validación) es coordinación legítima.
  El "<400" fue una estimación optimista pre-refactor. Meta real cumplida: agent_service es un
  coordinador honesto, sin lógica de agente ni código muerto.

## Residuos de instancia (post prueba de fuego 3.5, bajo impacto)
La prueba de fuego arregló los bugs de instancia que el huésped ve más (facts, ubicación, moneda,
contacto en los fallbacks de info_hotel/info_pago, RoomUnits). Quedan hardcodes de contacto del
Hampton de MENOR exposición, a parametrizar desde `contact_phone`/`contact_email` cuando se toque
esa área:
- `hotel_postsale_orchestrator.py:195` — "+54 294-474-6200" en un fallback de post-venta.
- `checkin_express_service.py:40` — `_HOTEL_PHONE` del flujo de check-in por WhatsApp.
RESUELTO en Tarea A (instanciabilidad de agentes): los 6 agentes ya no tienen datos del Hampton
hardcodeados (facts/ubicación/contacto/moneda salen del BusinessProfile). Los facts del Hampton
("no spa ni sauna", etc.) se movieron del texto de los prompts al perfil (facts), con migración
`ensure_hampton_facts`.

PENDIENTE — `app/domains/hotel/hotel_location.py`: aún tiene HOTEL_NAME/HOTEL_ADDRESS/HOTEL_CITY/
HOTEL_AIRPORT hardcodeados al Hampton ("Libertad 290", "bariloche"). Lo usan `como_llegar` (arma
las URLs de Google Maps con la dirección) y `near_hotel_search_url`. Para un cliente nuevo, el
texto visible ya usa `city` del perfil (Fase A), pero las URLs de maps siguen apuntando a la
dirección del Hampton. Parametrizar el módulo desde `lat`/`lng`/`city`/`region_line` del perfil
requiere que lea el BusinessProfile (hoy son constantes de módulo) y toca varias tools — mismo
tipo de trabajo que room_prices. Bajo impacto (solo el link de ruta al hotel).

RESUELTO en Tarea B (moneda multimoneda): existe la tabla `room_prices` (precio por moneda) +
`exchange_rate_service.convert(from, to)`. La disponibilidad, las cards del chat (RoomCard usa
`formatMoney` + `card.currency`), el owner (tarifas) y el post-venta (total) muestran el precio
en la moneda del perfil. Verificado con demo2 (Pousada BRL: disponibilidad en BRL real 1680/2600).
PENDIENTE menor: (a) el par de conversión sigue siendo solo USD↔ARS (dolarapi) — para otro par
sin fila explícita en room_prices ni cotización, se cae al USD sin convertir (no inventa); sumar
más fuentes de cotización es extender `convert` sin tocar llamadores. (b) las columnas legacy
`base_price_usd/ars` de `rooms` quedan (se siguen poblando por compat); su DROP va en una
migración Alembic futura (junto con las tablas huérfanas de turismo).

## Inconsistencia de zona horaria en los timestamps — ✅ RESUELTA (unificación a UTC)
**Estado: cerrada.** Antes convivían TRES convenciones para los timestamps de datos
(`utcnow_naive()` UTC, `now_business()` hora AR, y `datetime.now` hora del server), lo que rompía
comparaciones cruzadas. Se unificó **todo timestamp de datos a `utcnow_naive()` (UTC naive)**.

**Qué se migró:**
- `lead.py`: `created_at`/`updated_at`/`last_status_change` y demás timestamps `now_business()`→
  `utcnow_naive()`. La serialización pasó de `iso_business(..., source="ar")` a `source="utc"`.
- Modelos de dominio: `hotel.py` (Booking/RoomUnit/HotelTicket), `restaurant.py`, `promotions.py`,
  `knowledge.py`, `agent.py`, `staff.py`, `skill.py`, `chat_theme.py`, `exchange_rate.py`,
  `training_document.py`, `prompt_config_version.py`, `database.py`: `datetime.now`→`utcnow_naive`
  (defaults `default=`/`onupdate=` y llamadas).
- Servicios/routers con asignaciones o comparaciones sobre esas columnas: `metrics_service.py`,
  `agent_service.py` (ventana de sesión de 24h), `operations_service.py:138` (`stale_cutoff` vs
  `HotelTicket.updated_at`), `restaurant_service.py` (`updated_at`/`redeemed_at`),
  `exchange_rate_service.py` (`cached_at`), `chat_themes.py`/`documents.py`/`promotions.py`/
  `management_knowledge.py`/`pattern_manager.py` (timestamps de auditoría).

**Bugs latentes que la migración además arregló:**
- `business_metrics.py:400` (atribución conversión lead→booking): antes comparaba Booking
  (`datetime.now` server) vs Lead (`now_business` AR = UTC-3) → un booking posterior podía parecer
  anterior y no contarse. Ahora ambos en UTC. Cubierto por `tests/test_timezone_conversion.py`.
- `LeadEvent:311`: guardaba en AR pero serializaba como UTC (source por defecto). Coherente tras
  migrar `created_at` a UTC.
- `operations_service.py:138`: `stale_cutoff` (server-local) vs `HotelTicket.updated_at` (ya UTC
  tras migrar `hotel.py`) — desfase del mismo tipo, ahora ambos en UTC.

**Residual deliberado (NO se migra — son hora de pared LOCAL por diseño, no timestamps de auditoría):**
- `restaurant_service.py:442,519`: `reserved_for` es la hora que el huésped pidió (`strptime` de
  fecha+hora sin zona); se compara contra `datetime.now()` local. Pasarlo a UTC correría la reserva 3h.
- `promotions_service.py:92`: `now` se compara contra `valid_from`/`valid_until`, fechas locales
  que carga el dueño (`YYYY-MM-DD`).
- `chat_themes.py:89`: `today` se usa como `(mes, día)` para el rango estacional del tema.
- `now_business()`/`iso_business()` siguen usándose SOLO para MOSTRAR al usuario (notas de lead con
  `.strftime`, rangos de reporte `.date()`, fecha/hora en el prompt del orquestador). Ese es su
  propósito y es correcto.

> Refinamiento futuro (menor, no bloquea): los rangos de reporte en `business_metrics.py`
> (`now_business().date()` en líneas 66/218/336) definen el "día del negocio" en hora local pero
> filtran columnas ahora en UTC; el borde de medianoche puede desplazarse hasta 3h. Es semántica de
> reporte, no un cruce de convenciones; se afina si el cliente reporta discrepancias de borde.

## Otros ítems menores (de la auditoría, no bloqueantes)
- Refactor de `agent_service.chat()` (función larga, imports diferidos) — legibilidad.
- Cobertura de tests en hot-path (orquestadores, reservation_service).
- Guardrail semántico de relevancia (hoy off-topic se maneja post-hoc) y tratar el contenido
  RAG como no confiable (anti prompt-injection).
- Pydantic `@validator` → `@field_validator` (V2).
- Imágenes `.jpg` → `.webp`; pre-llenar date picker; búsqueda por nombre en Reservas.
