# Deploy a Render — pasos necesarios tras el push `51c185e..49eac86`

> Este push trae 3 tandas de la auditoría pre-extracción. **Tres de los cambios necesitan una
> acción manual en Render**: si deployás sin hacerlas, se rompen WhatsApp/Instagram y el perfil
> público. Los pasos están ordenados: hacé 1 y 2 **antes** del deploy, 3 **después**.

---

## Paso 1 — Variables de entorno de los webhooks ⚠️ CRÍTICO

**Qué cambió:** los webhooks de WhatsApp e Instagram pasaron a *fail-closed*. Antes aceptaban
cualquier POST sin validar firma (cualquiera con la URL podía inyectar mensajes falsos al agente).
Ahora, en producción, **sin la credencial de firma el webhook rechaza con 403**.

**Qué hacer:** en el dashboard de Render → servicio `hotel-backend` → *Environment*, verificá que
estas dos existan y tengan valor:

| Variable | De dónde sale |
|---|---|
| `TWILIO_AUTH_TOKEN` | Twilio Console → Account Info → Auth Token |
| `INSTAGRAM_APP_SECRET` | Meta for Developers → tu app → Settings → Basic → App Secret |

- **Si están** → no hacés nada, la validación simplemente empieza a funcionar como corresponde.
- **Si falta alguna** → cargala **antes** de deployar. Si no, ese canal deja de recibir mensajes.
- ¿No usás Instagram? Podés dejarla vacía: el canal queda cerrado (que es lo correcto) y el
  arranque loguea un `CRITICAL` diciéndolo. No impide que el backend levante.

**Cómo verificar después:** en los logs del arranque NO debe aparecer:
```
WhatsApp: TWILIO_AUTH_TOKEN NO configurado en producción → el webhook rechazará todos los mensajes
```

> Nota técnica: además se corrigió que la firma de Twilio se valide contra la **URL pública**
> (usando `X-Forwarded-Proto/Host`). Antes se validaba contra la URL interna del contenedor, así
> que detrás del proxy de Render la firma legítima podía fallar. Si el canal igual diera 403 con
> el token bien puesto, seteá `PUBLIC_BASE_URL=https://hotel-backend-4xgz.onrender.com`.

---

## Paso 2 — Variable del audit log (recomendado)

**Qué cambió:** el log de auditoría del chat (que contiene mensajes de huéspedes = PII) ya no se
escribe dentro del paquete de la app: ahora usa `AUDIT_LOG_DIR`.

Ya la agregué a `render.yaml` (`AUDIT_LOG_DIR=/data/audit`), así que si Render toma el blueprint
se aplica sola. **Si tu servicio no usa blueprint**, agregala a mano en *Environment*:

```
AUDIT_LOG_DIR = /data/audit
```

Apunta al disco persistente que ya tenés montado (el mismo de ChromaDB), así el rastro sobrevive
a los deploys. Si no la setés, el log cae en `./audit_logs` dentro del contenedor y se pierde en
cada deploy (no rompe nada, solo perdés la auditoría).

---

## Paso 3 — Migración de la base ⚠️ CRÍTICO — DESPUÉS del deploy

**Qué cambió:** `business_profile` tiene 4 columnas nuevas (`contact_phone`, `contact_email`,
`contact_address`, `instagram`) que sirven la identidad pública a la landing. Hasta ahora esas
columnas se creaban con un mecanismo que **solo funciona en SQLite** — en la Postgres de Render
no existen, y `/api/public/business-profile` fallaría al leerlas.

Necesitás correr Alembic **una sola vez**. Desde la Shell de Render (`hotel-backend` → *Shell*):

```bash
# La Shell ya abre en el rootDir del servicio (`backend/`, según render.yaml), así que
# alembic.ini está a mano. Si no, hacé: cd /opt/render/project/src/backend

# 0) BACKUP primero (Render → tu PostgreSQL → Backups → crear manual). No te lo saltees.

# 1) ¿Alembic ya está inicializado en esta base?
alembic current
```

**Caso A — `alembic current` NO devuelve nada** (la base nunca se marcó):
```bash
alembic stamp 0001_baseline   # marca el esquema existente SIN recrear tablas
alembic upgrade head          # aplica la 0002 (agrega las 4 columnas)
```

**Caso B — devuelve `0001_baseline`**:
```bash
alembic upgrade head
```

**Caso C — ya dice `0002_bp_contacto`**: no hay nada que hacer.

**Verificar:**
```bash
alembic current                                    # → 0002_bp_contacto (head)
curl -s localhost:$PORT/api/public/business-profile   # debe incluir contact_address
```

> La migración es idempotente (chequea el catálogo antes de alterar) y sirve tanto para una base
> existente como para una nueva. Probada en ambos escenarios localmente.

---

## Paso 4 — Cargar el contacto del negocio (2 minutos, en el backoffice)

Los datos de contacto salieron del código del frontend y ahora vienen del backoffice. En
producción, la dirección y el Instagram van a estar vacíos hasta que los cargues:

Backoffice → **Negocio → Identidad** → completar **Dirección** e **Instagram** → Guardar.

(Teléfono y email ya estaban en la base, no se pierden.) Si no lo hacés, el footer y la sección de
ubicación de la landing quedan sin esos datos — el resto funciona normal.

---

## Qué NO requiere acción

- **El arranque ya no siembra datos del Hampton.** `start.sh` quedó rubro-agnóstico. El RAG vive
  en el disco persistente (`/data/chroma_db`), así que **sobrevive al deploy**: no hace falta
  re-ingestar. Solo corré `python ingest_docs.py` si cambiaste documentos de `docsbase/`.
- **Los endpoints cerrados** (usage, agents, business-profile completo, etc.) ya reciben el JWT
  del backoffice: el panel sigue funcionando igual.
- **Frontend**: solo un rebuild normal (el `VITE_API_BASE` no cambió).

---

## Checklist rápido

- [ ] `TWILIO_AUTH_TOKEN` seteada en Render (o asumo que WhatsApp queda cerrado)
- [ ] `INSTAGRAM_APP_SECRET` seteada (o asumo que IG queda cerrado)
- [ ] `AUDIT_LOG_DIR=/data/audit`
- [ ] Backup de la base
- [ ] Deploy
- [ ] `alembic stamp 0001_baseline` (si hacía falta) + `alembic upgrade head`
- [ ] `alembic current` → `0002_bp_contacto`
- [ ] Probar: chat del widget, un mensaje de WhatsApp, y la landing (footer con contacto)
- [ ] Cargar Dirección e Instagram en el backoffice
