# Plan de mejora — Nivelación de reglas de los agentes

> Objetivo: eliminar el **desnivel de reglas** entre los agentes del sistema. Hoy cada
> agente reimplementa sus reglas por su cuenta, así que unos quedaron mucho mejor
> equipados que otros. Este plan propone un **baseline común** (reglas que todos deben
> tener por igual) más las **reglas específicas de cada rol**, reusando el patrón de
> bloques compartidos que ya existe en el código.
>
> Documento hermano: `PROMPTS_AGENTES.md` (transcripción de los 6 prompts).

---

## 1. Contexto y problema

El sistema tiene **6 agentes** (ver `PROMPTS_AGENTES.md`): Triage, Casual, Pre-venta,
Post-venta, Dueño y Staff. Cada uno tiene su propio system prompt en `backend/app/prompts/`.

El problema: **no existe un "baseline" de reglas común**. El único bloque compartido es
`NATURALIDAD_BLOCK` (`generation_prompts.py:7`), y solo entre Casual y Pre-venta. Todo lo
demás está **copiado a mano** en cada prompt o directamente **ausente**. Consecuencias:

- El **Dueño** tiene una "REGLA DE HONESTIDAD" ejemplar (distingue dato real / estimación /
  recomendación). Ningún otro agente la tiene como principio general.
- El **Staff** tiene una sola regla anti-invención ("no inventes tickets") y **ni siquiera
  un límite de dominio**.
- La regla **anti-inventar-personas** (agregada recientemente para corregir un bug real
  donde Aura fingía conocer a "Eli") vive **solo en el Casual** — ni siquiera en el
  Pre-venta, que es la misma persona.
- Reglas idénticas (datos bancarios, alergias, "el hotel no tiene spa ni sauna") están
  **duplicadas literalmente** en dos prompts, lo que garantiza que se desincronicen con
  el tiempo.

El resultado es lo que el negocio no quiere: **reglas mejores en un agente que en otro**,
sin una razón de diseño que lo justifique.

---

## 2. Por qué Casual y Pre-venta están separados (contexto de arquitectura)

Antes de nivelar, conviene entender que **no todo agente es igual**. Casual y Pre-venta son
"la misma persona" (Aura) pero corren por **dos motores distintos**, por una razón de
costo/latencia + control de riesgo:

| | **Casual** | **Pre-venta** |
|---|---|---|
| Motor | `chat.completions` directo, **sin tools** | Agents SDK con **16 tools** + guardrail + lead analysis |
| Pasadas | 1 sola | hasta 6 turnos de razonamiento |
| Temperature | 0.8 (creativo) | 0.3 (preciso) |
| Contexto | 4 mensajes | 20 mensajes |
| Para qué | saludos, clima, despedidas, off-topic | precios, disponibilidad, promos, reservar |

Para un *"hola"* no hace falta ningún dato real del hotel: pagar el loop caro del SDK sería
tirar plata y latencia. Y al revés, dejar que el Casual conteste precios "de memoria" sería
un riesgo de negocio. Por eso hay un **triage barato** que decide la ruta. **Casual es
exclusivo del huésped/pre-venta**; el Dueño y el Staff nunca lo usan.

**Implicancia para este plan:** la nivelación **no** significa "un solo prompt para todos".
Significa **un baseline de reglas compartidas** inyectado en cada agente vía placeholder,
respetando que cada uno tenga además sus reglas propias. El motor de cada agente no cambia.

---

## 3. Matriz de reglas actual (dónde está el desnivel)

Reglas de cada agente clasificadas en 5 categorías. `Fuerte` = regla explícita y completa;
`Parcial` = existe pero acotada; `Básica` = mínima; `Ausente` = no existe.

| Categoría | Casual | Pre-venta | Post-venta | Dueño | Staff | Triage |
|---|---|---|---|---|---|---|
| **Anti-alucinación / honestidad** | Parcial (solo personas) | **Fuerte** (todo desde tools) | **Fuerte** | **Fuerte** (dato/estimación/recom.) | Básica (no inventar tickets) | Media |
| **Tono / voz de marca** | **Fuerte** (NATURALIDAD) | **Fuerte** (TONO + NATURALIDAD) | Fuerte (HAMPTONALITY) | Media | Básica | — |
| **Seguridad / datos sensibles** | Ausente | **Fuerte** (CBU + alergias) | **Fuerte** (CBU + alergias) | Ausente | Ausente | Solo enruta pago |
| **Alcance / límite de dominio** | Fuerte | Fuerte | Fuerte (+ escalación) | Fuerte | **Débil** (no hay) | Es su núcleo |
| **Específicas del rol** | Captación de lead | Booking / precios / upsell | Soporte / escalación | BI / revenue / planes | Tickets / áreas | Ruteo |

---

## 4. Los 8 huecos concretos

1. **Tono de marca (`NATURALIDAD_BLOCK`) solo en 2 agentes.** Casual y Pre-venta lo comparten;
   Post-venta reimplementa su propia voz (HAMPTONALITY), Dueño y Staff tienen tono aparte.
   → Riesgo de que la voz de la marca se sienta distinta según el agente.

2. **Anti-inventar-personas solo en Casual.** No existe en Pre-venta, Post-venta, Dueño ni
   Staff. En Post-venta importa (un huésped puede nombrar a un empleado) y en Pre-venta
   también (es la misma Aura, mismo tipo de charla). **Hueco de mayor prioridad** junto al #3.

3. **Regla de honestidad "dato real vs estimación" desnivelada.** Está enunciada de forma
   ejemplar en el Dueño (`owner_prompts.py`) pero en los demás está **fragmentada por-tool**
   ("no inventes precio", "no inventes promo", "no inventes servicio"). El Staff casi no la
   tiene. → Debería existir un principio general común, y las reglas por-tool quedan como
   refuerzo específico.

4. **Datos bancarios (CBU/alias) duplicados literalmente.** Texto casi calcado en Pre-venta
   (`info_pago`) y Post-venta (`consultar_pago`). → Candidato a bloque único compartido
   (no aplica a Dueño/Staff/Casual).

5. **Alergias / seguridad alimentaria desnivelada.** En Pre-venta (regla 10, muy completa:
   cruzar alérgenos de la carta, respetar ⚠️ del perfil) y Post-venta (más breve). → Unificar
   con la versión completa como base.

6. **Datos del hotel hardcodeados y duplicados.** "El hotel NO tiene spa ni sauna" está
   repetido literal en Pre-venta y Post-venta. → Un solo bloque de "hechos del hotel" (o
   idealmente traído de la base de conocimiento) evita que se contradigan.

7. **Staff sin límite de dominio.** Casual, Pre-venta, Post-venta y Dueño dicen qué hacer si
   les piden algo fuera de su rol; el Staff no. → Falta una regla de reconducción/derivación
   para el empleado que pregunta algo fuera de operaciones.

8. **Escalación a humano solo en Post-venta.** El Post-venta tiene `analizar_escalacion` y un
   protocolo claro; el Pre-venta no tiene noción de "esto no lo puedo resolver, derivo". → No
   es urgente, pero conviene una regla común de "cuándo y cómo derivar a un humano".

---

## 5. Propuesta — Baseline común + reglas específicas

### 5.1 Principio de diseño

Reusar el patrón que **ya existe**: `NATURALIDAD_BLOCK` es una constante que se inyecta en el
prompt de 2 agentes vía `{naturalidad_block}`. Se extiende ese mismo mecanismo a un set de
**bloques baseline** que se inyectan en TODOS los agentes que correspondan, mediante
placeholders. Cada agente arma su prompt = `baseline` + `reglas del rol`.

### 5.2 Bloques baseline propuestos (nuevos, en `generation_prompts.py` o un `base_blocks.py`)

| Bloque (constante) | Qué contiene | Se inyecta en |
|---|---|---|
| `HONESTIDAD_BLOCK` | Principio general: distinguir DATO REAL (de tools/contexto) vs ESTIMACIÓN vs OPINIÓN; nunca presentar lo no verificado como hecho; si no sabés, decilo. (Abstracción de la regla del Dueño, `owner_prompts.py:63-71`.) | **Todos** (Casual, Pre, Post, Dueño, Staff) |
| `ANTI_INVENCION_PERSONAS_BLOCK` | No fingir conocer a una persona nombrada; solo reconocer a quien figure en el equipo real (`{team_block}`); si no, ser honesto. (Generalización de la regla del Casual, `generation_prompts.py:38-45`.) | Casual, Pre-venta, Post-venta (los que hablan con huéspedes que pueden nombrar staff) |
| `DATOS_BANCARIOS_BLOCK` | CBU/alias/datos bancarios SIEMPRE desde la tool, exactos, nunca inventar/modificar. (Unificación de Pre `info_pago` + Post `consultar_pago`.) | Pre-venta, Post-venta |
| `ALERGIAS_BLOCK` | Alergias = seguridad alimentaria: registrar apenas se mencionen, nunca confirmar plato con el alérgeno, cruzar alérgenos, respetar ⚠️ del perfil. (Versión completa del Pre-venta.) | Pre-venta, Post-venta |
| `HECHOS_HOTEL_BLOCK` | Datos duros del hotel que no deben inventarse ni contradecirse (ej. "no hay spa ni sauna"). Idealmente derivado de la base de conocimiento. | Pre-venta, Post-venta (y consultable por Dueño) |
| `LIMITE_DOMINIO_BLOCK` | Patrón común de "si te piden algo fuera de tu rol, reconducí/derivá con calidez", parametrizable por rol. | Todos (con variante por rol) |
| `NATURALIDAD_BLOCK` (ya existe) | Voz de marca. Evaluar extender una variante a Post-venta para unificar la voz. | Casual, Pre-venta (+ evaluar Post-venta) |

### 5.3 Qué queda como específico de cada rol (NO se toca)

- **Pre-venta:** flujo de booking, tarjetas, política de descuentos, upselling comercial.
- **Post-venta:** `analizar_escalacion`, soporte de reserva, servicios al alojado.
- **Dueño:** BI, revenue, `consultar_conocimiento`, planes de largo plazo, gráficos.
- **Staff:** resolución/reporte de tickets, deducción de área.
- **Casual:** captación de lead, reconducción a la venta.
- **Triage:** lógica de ruteo (es un clasificador, no redacta al usuario).

---

## 6. Fases de implementación

**Fase 1 — Lo sensible primero (mayor riesgo, menor superficie).**
Extraer e inyectar `HONESTIDAD_BLOCK` y `ANTI_INVENCION_PERSONAS_BLOCK` en Pre-venta y
Post-venta (además del Casual que ya lo tiene). Esto cierra los huecos #2 y #3, que son los
de mayor riesgo de negocio (un agente afirmando algo falso a un huésped).

**Fase 2 — Deduplicación de reglas condicionales.**
Extraer `DATOS_BANCARIOS_BLOCK`, `ALERGIAS_BLOCK` y `HECHOS_HOTEL_BLOCK`; reemplazar el texto
duplicado en Pre-venta y Post-venta por los placeholders. Cierra #4, #5, #6.

**Fase 3 — Nivelación de alcance y tono.**
`LIMITE_DOMINIO_BLOCK` en el Staff (hueco #7). Evaluar variante de `NATURALIDAD_BLOCK` para
Post-venta (#1). Regla común de escalación a humano donde aplique (#8).

**Fase 4 — Baseline transversal.**
Consolidar todos los bloques baseline en un único módulo (`base_blocks.py`) y documentar el
contrato: "todo agente nuevo arranca del baseline + sus reglas de rol". Esto evita que el
desnivel se reintroduzca al crear el próximo agente.

---

## 7. Fundamento — por qué conviene hacerlo así

- **Consistencia de marca y de riesgo.** Un huésped que pasa de charla casual a soporte no
  debería percibir "otra" Aura con reglas peores. Un baseline común garantiza el mismo piso
  de honestidad y seguridad en todos los puntos de contacto.
- **Un solo lugar para cambiar.** Hoy, corregir "el hotel no tiene spa" o endurecer la regla
  de datos bancarios exige editar 2+ prompts y arriesgar que se desincronicen. Con bloques
  compartidos, se cambia una constante y aplica a todos.
- **Escala a más agentes sin regresión.** El proyecto es un "agente base" replicable. Definir
  el baseline ahora hace que cada agente futuro nazca al mismo nivel, en vez de heredar el
  desnivel actual.
- **Reusa un patrón probado.** No inventa una arquitectura nueva: `NATURALIDAD_BLOCK` ya
  demuestra que inyectar un bloque compartido vía placeholder funciona. Es extender lo que ya
  anda.

---

## 8. Verificación (cuando se implemente)

- **Paridad:** tras extraer un bloque, el prompt renderizado de cada agente debe ser
  equivalente al anterior (mismos textos, ahora vía placeholder). Comparar byte a byte donde
  el bloque sustituye texto idéntico.
- **Pruebas de comportamiento** (como las que ya se corrieron para el fix de "Eli"): por cada
  regla nivelada, un escenario que la ejercite en el agente que antes NO la tenía. Ej.:
  nombrar un empleado inexistente en Post-venta → no debe inventar; pedir un CBU al Post-venta
  → debe salir de la tool, exacto.
- **Suite de tests** (`backend/tests/`) en verde tras cada fase.
- **Sin regresión de tono:** revisar manualmente algunas respuestas del Post-venta si se le
  aplica la variante de `NATURALIDAD_BLOCK`, para que no pierda su HAMPTONALITY.

---

## 9. Alcance de este documento

Este es un **plan**, no una implementación. No se modificó ningún prompt. La ejecución de las
fases 1-4 es un trabajo posterior, a acordar y priorizar con el negocio.
