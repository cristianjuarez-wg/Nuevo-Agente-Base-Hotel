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

## Pendiente — migraciones formales (Alembic)
Hoy el esquema evoluciona con `run_light_migrations()` (`ensure_column` idempotente) en
`models/database.py`. Funciona en SQLite y PostgreSQL, es idempotente y corre en el startup
y en los seeds. **Limitación:** sin versionado ni rollback; agrega columnas pero no maneja
cambios complejos (renombrar, cambiar tipos, mover datos).

**Por qué no se migra ahora:** introducir Alembic sobre una base **con datos en producción
(Render)** requiere generar un baseline que matchee el esquema actual exacto y validar cada
migración con backup — es delicado y arriesgado para una demo que ya funciona.

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

## Otros ítems menores (de la auditoría, no bloqueantes)
- Refactor de `agent_service.chat()` (función larga, imports diferidos) — legibilidad.
- Cobertura de tests en hot-path (orquestadores, reservation_service).
- Guardrail semántico de relevancia (hoy off-topic se maneja post-hoc) y tratar el contenido
  RAG como no confiable (anti prompt-injection).
- Pydantic `@validator` → `@field_validator` (V2).
- Imágenes `.jpg` → `.webp`; pre-llenar date picker; búsqueda por nombre en Reservas.
