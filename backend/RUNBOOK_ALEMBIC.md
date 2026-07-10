# Runbook — Alembic (Fase 2.4)

Migraciones de esquema versionadas. Reemplaza el `run_light_migrations()` (`ensure_column`
idempotente) por revisiones Alembic con historial y baseline.

**Estado:** el setup está LISTO en código (`alembic/`, `alembic.ini`, revisión
`0001_baseline`). Falta el paso que toca la DB de PRODUCCIÓN (Render) — se hace a mano,
con backup, siguiendo este runbook. **Nadie automatizó ese paso: hay que ejecutarlo con
cuidado.**

---

## 0. Qué hay ya hecho (no requiere acción)

- `alembic init alembic` corrido; `alembic/env.py` configurado para:
  - leer la URL de `settings.DATABASE_URL` (Render=PostgreSQL, local=SQLite) — NO del ini.
  - registrar TODOS los modelos (relationships por string resueltas) → `target_metadata`.
- `alembic/versions/0001_baseline.py` — la revisión BASELINE:
  - `upgrade()` crea el esquema completo desde `Base.metadata` (`checkfirst=True`, idempotente).
  - Verificado: `alembic upgrade head` en una DB SQLite limpia crea las 36 tablas + `alembic_version`.

---

## 1. Aplicar en PRODUCCIÓN (Render) — HACER CON BACKUP

La DB de producción YA tiene las 36 tablas. **No hay que recrearlas**: solo marcar el
baseline como aplicado, para que las revisiones futuras arranquen desde ahí.

```bash
# 1. BACKUP de la DB de Render (imprescindible antes de tocar nada).
#    Render → Dashboard → tu PostgreSQL → "Backups" → crear uno manual,
#    o vía pg_dump con la EXTERNAL Database URL:
pg_dump "$RENDER_EXTERNAL_DATABASE_URL" -Fc -f backup_pre_alembic_$(date +%Y%m%d).dump

# 2. Con la app apuntando a la DB de producción (DATABASE_URL seteada), marcar el baseline
#    como YA aplicado — SIN recrear tablas:
cd backend
alembic stamp 0001_baseline

# 3. Verificar: debe existir la tabla alembic_version con version_num = 0001_baseline
psql "$RENDER_EXTERNAL_DATABASE_URL" -c "SELECT * FROM alembic_version;"
```

`stamp` solo escribe la marca de versión; NO ejecuta el `upgrade()` (no toca el esquema).
Si algo sale mal, la marca se borra con `DELETE FROM alembic_version;` y se restaura del dump.

---

## 2. Instancia NUEVA (cliente N+1, DB vacía)

```bash
cd backend
alembic upgrade head    # crea TODO el esquema desde el baseline (checkfirst=True)
```

(Alternativamente el startup de la app ya crea el esquema con `create_all`; el `upgrade head`
lo deja además marcado en `alembic_version`, que es lo correcto de acá en más.)

---

## 3. Política a partir de ahora (TODO cambio de esquema)

- **Columna/tabla nueva = revisión Alembic**, NO más `ensure_column`:
  ```bash
  # tras cambiar un modelo:
  alembic revision --autogenerate -m "add leads.some_column"
  # revisar el archivo generado en alembic/versions/, ajustar si hace falta, y:
  alembic upgrade head
  ```
- `run_light_migrations()` / `ensure_column` en `models/database.py` se CONSERVAN solo para
  el SQLite efímero de tests/dev (arranque sin Alembic). En producción, el deploy debe correr
  `alembic upgrade head` (agregar a `start.sh` cuando se active este flujo — ver §4).
- El `Base.metadata.create_all` a nivel de módulo de cada modelo también se conserva por
  ahora (idempotente); Alembic y create_all conviven sin conflicto (ambos con checkfirst).

---

## 4. Activar Alembic en el deploy (opcional, cuando se decida)

Agregar a `backend/start.sh`, ANTES del `uvicorn`:

```bash
alembic upgrade head || echo "[warn] alembic upgrade falló, continuando con create_all de startup"
```

Dejarlo tolerante al fallo mientras se valida en staging; una vez confiable, quitar el `||`.

---

## 5. Limpieza turismo (revisión manual, aparte)

Las tablas huérfanas del legacy de turismo (postsale/paquetes, providers, etc.) quedaron en
la DB de Render tras la Fase 0.2 (se borró el código, NO las tablas). Cuando se quiera:

```bash
alembic revision -m "drop legacy turismo tables"   # editar upgrade() con los op.drop_table
```

Marcarla como manual-only (no en el `upgrade head` automático) hasta validar en staging que
ninguna consulta viva las toca.
