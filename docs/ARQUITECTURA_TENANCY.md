# Arquitectura de tenancy — decisión y consecuencias (Fase 3.0)

> **Decisión (2026-07-10): INSTANCIA POR CLIENTE.**
> Cada hotel corre en su propio deploy, con su propia base de datos y su propio índice de
> conocimiento (Chroma). No hay `tenant_id`; no hay datos de dos clientes en la misma tabla.

Esta decisión es el punto de partida de la Fase 3 (empaquetado producto). Se documenta acá con
sus consecuencias para que cualquiera que retome el proyecto entienda por qué el sistema NO es
multi-tenant y qué haría falta si algún día se decide serlo.

---

## El modelo elegido

**Un cliente = un deploy independiente:**

| Recurso | Por instancia |
|---|---|
| Servicio web (FastAPI) | uno |
| Landing (static site) | una |
| Base de datos (PostgreSQL) | una |
| Índice de conocimiento (ChromaDB, disco `/data`) | uno |
| Credenciales (OpenAI, Twilio, ADMIN) | propias, vía env vars |
| `BusinessProfile` (identidad) | singleton `id=1` de esa DB |

El código Python es **el mismo** para todos los clientes. Lo único que cambia entre instancias
es **configuración, seeds y conocimiento** — nunca código. Eso es exactamente lo que Fases 0-2
habilitaron (identidad en DB, prompts compuestos desde el perfil, framework core/dominio) y lo
que Fase 3.1+ automatiza (plantilla de instancia + runbook).

---

## Por qué instancia-por-cliente (y no multi-tenant en una sola DB)

1. **Aislamiento total de datos.** Leads, huéspedes, precios, reservas y conversaciones de un
   hotel NUNCA comparten tabla con los de otro. En hospitalidad esto es crítico: un bug de
   scoping en una query no puede filtrar datos de un cliente a otro porque, físicamente, no
   están en la misma base.
2. **Cero cambios de esquema.** Multi-tenant real exigiría `tenant_id` en ~30 modelos + scoping
   en TODAS las queries + particionar las colecciones de Chroma por tenant. Es un proyecto en sí
   mismo, con superficie de error grande y permanente (cada query nueva es una posible fuga).
3. **Blast-radius acotado.** Un deploy que se cae, una migración que falla o un índice corrupto
   afecta a UN cliente, no a todos.
4. **Costo de infra bajo.** En Render, una instancia (web + static + DB chica + 1 GB de disco) es
   barata. El costo real del modelo NO es infra, es **operar N deploys** — y ese costo es
   justamente lo que Fase 3.1-3.3 elimina automatizando el alta (plantilla + bootstrap + runbook).

El intercambio es explícito: cambiamos "complejidad permanente en el código" (scoping multi-tenant)
por "procedimiento de alta repetible" (un runbook). La Fase 3 hace que ese procedimiento sea de
horas, no de días.

---

## Consecuencias operativas (lo que este modelo implica)

- **Alta de cliente = nuevo deploy**, no una fila nueva en una tabla. Se automatiza en 3.1
  (`instance/<cliente>.yaml` + `bootstrap_instance.py`) y 3.2 (wizard de onboarding).
- **El Hampton es la primera instancia de la plantilla**, no un caso especial: sus seeds actuales
  (`seed_hotel.py`, etc.) se reexpresan como `instance/hampton.yaml`, probando el mecanismo
  contra un cliente real.
- **Deploy actual (`render.yaml` + `start.sh`):** hoy `start.sh` corre 6 seeds hardcodeados del
  Hampton. Con la plantilla, el arranque pasa a `alembic upgrade head` + `bootstrap_instance
  <cliente>.yaml`, sin editar Python por cliente.
- **Métricas y observabilidad son por instancia** (3.4): cada deploy tiene su propio usage/costo;
  no hay un dashboard cross-cliente (si se necesita, es un agregador externo, fuera de este plan).

---

## Camino de migración futuro (si el volumen lo pidiera)

Instancia-por-cliente NO cierra la puerta a multi-tenant. Si en el futuro el número de clientes
hace que operar N deploys sea caro, la migración sería un proyecto propio con estas piezas:

1. `tenant_id` (FK a una tabla `tenants`) en todos los modelos con datos de cliente.
2. Scoping obligatorio por `tenant_id` en TODAS las queries (idealmente forzado por un default
   de sesión SQLAlchemy o un mixin, no a mano query por query).
3. Colecciones de Chroma particionadas por tenant.
4. Resolución de tenant por request (subdominio o header) + un `BusinessProfile` por tenant en
   vez de singleton.

No está diseñado en este plan y **requiere su propia sesión de diseño**. Se anota como fuera de
alcance en `DEUDA_TECNICA.md`.

---

## Referencias

- Plan de productización §3.0 (recomendación de instancia-por-cliente).
- Fase 1: `BusinessProfile` (identidad en DB, singleton `id=1`).
- Fase 3.1: plantilla de instancia (`instance/`, `bootstrap_instance.py`) y
  `docs/RUNBOOK_NUEVA_INSTANCIA.md`.
