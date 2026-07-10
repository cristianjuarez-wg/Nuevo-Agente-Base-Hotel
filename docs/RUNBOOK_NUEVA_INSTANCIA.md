# Runbook — dar de alta una instancia nueva (Fase 3.1)

> Procedimiento repetible para desplegar el agente para un cliente nuevo **sin tocar código**.
> Modelo: instancia por cliente (ver `docs/ARQUITECTURA_TENANCY.md`). Objetivo de tiempo: < 1
> día-persona; ideal < 2 horas.
>
> Cada paso que requiera editar Python es un **bug de la fase** — reportarlo, no parchearlo a mano.

---

## Prerrequisitos

- Cuenta de Render (o el hosting equivalente) con permiso para crear servicios + una DB.
- Credenciales del cliente: `OPENAI_API_KEY` (con budget), y si usa WhatsApp/Instagram, las de
  Twilio/Meta.
- Los datos del cliente: identidad, catálogo de habitaciones con precios, y los documentos de
  conocimiento (políticas, servicios, FAQ, lugares).

---

## Paso 1 — Preparar el archivo de instancia

1. Copiar la plantilla:
   ```bash
   cp backend/instance/instance.example.yaml backend/instance/<cliente>.yaml
   ```
2. Completar `<cliente>.yaml` con los datos del cliente. Campos clave (todos documentados en el
   `.example`): `business.name`, `agent_name`, `timezone`, `language`, `dialect_style`,
   `primary_currency`/`secondary_currency`, `city`, `facts`, y el catálogo `rooms`.
   - **Nada de secretos en el YAML** (la password del admin va por env var, ver paso 3).
   - Referencia real de un YAML completo: `backend/instance/hampton.yaml`.

---

## Paso 2 — Crear la infraestructura en Render

1. Crear la **base de datos** (PostgreSQL) para el cliente.
2. Crear el **servicio web** (backend) apuntando al repo, `rootDir: backend`. Basarse en el
   `render.yaml` existente (mismo build/start), cambiando nombres por cliente.
3. Crear el **static site** (landing), `rootDir: landing`.
4. Setear las **env vars** del backend (lista mínima):
   - `DATABASE_URL` → la connection string de la DB del cliente.
   - `OPENAI_API_KEY` → la del cliente (con budget).
   - `JWT_SECRET` → un secreto largo y único por instancia (≥ 32 bytes).
   - `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` → el primer admin del backoffice
     (se crea solo si la tabla de admins está vacía; ver paso 4).
   - `ALLOWED_ORIGINS` → la URL del static site del cliente.
   - `DEBUG` → `false` (producción; fail-closed de auth activo).
   - `CHROMA_PERSIST_DIRECTORY`, `MEDIA_DIR` → rutas en el disco montado.
   - Si usa WhatsApp: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`.

---

## Paso 3 — Migrar el esquema

En la primera release del servicio, antes de servir tráfico:

```bash
alembic upgrade head          # crea el esquema (o usar el baseline, ver RUNBOOK_ALEMBIC.md)
```

> El `bootstrap_instance` también hace `create_all` como red de seguridad (idempotente), pero la
> fuente de verdad del esquema en producción es Alembic. Ver `backend/RUNBOOK_ALEMBIC.md` para el
> stamp del baseline en una DB con datos preexistentes.

---

## Paso 4 — Aplicar la instancia (bootstrap)

```bash
python -m instance.bootstrap_instance instance/<cliente>.yaml
```

Esto (idempotente — se puede repetir):
- Crea/actualiza el `BusinessProfile` (identidad, moneda, idioma, dialecto, facts).
- Siembra el catálogo de `rooms` con sus precios.
- Crea el **admin bootstrap** con `BOOTSTRAP_ADMIN_EMAIL` (password de `BOOTSTRAP_ADMIN_PASSWORD`)
  **solo si la tabla de admins está vacía**.

Verificación rápida: entrar al backoffice (`/#admin`), loguearse con el admin bootstrap, y
confirmar en "Identidad del negocio" que los datos son los del cliente.

---

## Paso 5 — Cargar el conocimiento

Desde el backoffice (sección Negocio → Conocimiento), subir los documentos del cliente:
políticas, servicios, FAQ, datos de pago (CBU/alias), lugares/excursiones. El agente los usa vía
RAG. Estructura esperada del conocimiento por vertical hotel: la del Hampton en `docsbase/` sirve
de plantilla de qué documentos crear.

> **Importante (F8 pago):** cargar la entry de categoría `pagos` con el CBU/alias EXACTOS. El
> agente los comunica textualmente desde la tool `info_pago`; si están mal cargados, están mal
> comunicados (el agente no los corrige ni los inventa — es el comportamiento correcto).

---

## Paso 6 — Verificar antes del go-live

1. **Evals del cliente:** correr la suite (cuando exista el particionado core/instancia de la
   tarea 3.3). Mínimo, correr `run_evals` y confirmar que ningún flujo crítico está roto
   (ver `evals/FLOW_COVERAGE.md`).
2. **Chat de prueba** (el wizard de onboarding 3.2 lo integra): preguntar el precio (moneda
   correcta), preguntar por algo que el cliente NO tiene (respeta `facts`), pedir los datos de
   pago (CBU exacto), y una consulta casual (dialecto correcto).
3. **Checklist de go-live:**
   - [ ] Identidad correcta en el saludo (nombre del negocio + agente).
   - [ ] Precios en la moneda del cliente.
   - [ ] `facts` respetados (no inventa servicios inexistentes).
   - [ ] Datos de pago exactos.
   - [ ] Canales (WhatsApp/IG) conectados solo si el cliente los usa.
   - [ ] `DEBUG=false` confirmado (auth fail-closed).

---

## Retro (obligatorio)

Al terminar, anotar cuánto tardó el procedimiento y **qué paso requirió tocar código**. Cada
uno de esos es un bug de la fase de empaquetado — arreglarlo cierra el objetivo de 3.5 (crear la
instancia N+1 sin tocar código).
