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

## Otros ítems menores (de la auditoría, no bloqueantes)
- Refactor de `agent_service.chat()` (función larga, imports diferidos) — legibilidad.
- Cobertura de tests en hot-path (orquestadores, reservation_service).
- Guardrail semántico de relevancia (hoy off-topic se maneja post-hoc) y tratar el contenido
  RAG como no confiable (anti prompt-injection).
- Pydantic `@validator` → `@field_validator` (V2).
- Imágenes `.jpg` → `.webp`; pre-llenar date picker; búsqueda por nombre en Reservas.
