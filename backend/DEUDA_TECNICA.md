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

## Pendiente — código legacy de turismo
El proyecto evolucionó de un sistema de turismo a hotel. Quedan modelos/routers/servicios
de turismo **importados pero desconectados** del flujo del hotel:
- Modelos: `Provider`, `ProviderContact`, `FlightStatusTracking`, `AirportTerminal`,
  `SoldPackage`, `SupportTicket`, `Geography`, `LearningOpportunity`.
- Routers: `providers`, `flight_monitoring`, `kanban`, partes de `postsale` legacy.
- Orquestadores legacy: `agent_sdk_orchestrator`, `postsale_sdk_orchestrator` (no usados;
  el hotel usa `hotel_sdk_orchestrator` y `hotel_postsale_orchestrator`).

**Por qué no se retira ahora:** la app importa varios de estos en cadena (relationships de
SQLAlchemy, imports en `main.py`). Retirarlos requiere desenredar las dependencias con
cuidado y verificar que `Base.metadata.create_all` siga resolviendo las FKs. Es un trabajo
de limpieza de riesgo medio sin impacto funcional, mejor en una sesión dedicada y no antes
de una demo.

**Plan cuando se haga:** (1) mapear qué importa cada módulo legacy; (2) quitar sus
`include_router` de `main.py`; (3) eliminar los modelos sin relationships activas verificando
`from app.main import app` tras cada paso; (4) borrar servicios huérfanos. Hacer por capas,
con el import-check como prueba de regresión.

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
