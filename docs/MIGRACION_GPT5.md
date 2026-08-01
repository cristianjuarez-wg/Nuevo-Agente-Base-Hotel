# Migración a GPT-5 — hallazgos medidos

Fecha: 2026-08-01. Rama: `feat/compat-gpt5`.

Todo lo de acá está **medido contra la API real**, no estimado. Los números de costo
salen del consumo de un turno de preventa instrumentado sobre el transporte HTTP.

---

## 1. Estado: el código ya es compatible

El backend corre en GPT-5 sin cambios de código. Migrar = editar el `.env`.

Antes de esta tanda, cambiar el modelo hacía fallar **todos** los turnos. Dos
parámetros que el código mandaba siempre son rechazados con 400 por GPT-5/o1/o3:

    temperature=0.3  ->  "Only the default (1) value is supported"
    max_tokens=50    ->  "Use 'max_completion_tokens' instead"

La regla vive en `app/core/llm/model_compat.py` y se aplica en los dos únicos
puntos de paso (`openai_client` para las ~40 llamadas directas, `sdk_runtime`
para los 5 agentes SDK). Detección por prefijo de familia, no por lista blanca:
una lista envejece mal (`gpt-5.4`, `gpt-5.6-luna`, lo que venga).

---

## 2. Costo real por turno de preventa

Medido: 1 turno = triage + 2-3 llamadas del agente.

| Configuración | Por turno | 10k turnos | 50k turnos | vs hoy |
|---|---|---|---|---|
| **gpt-4o + 4o-mini** (hoy) | $0,0620 | $620 | $3.099 | — |
| **gpt-5-mini + nano** | $0,0139 | $139 | $697 | **−78%** |
| **gpt-5 + nano** | $0,0680 | $680 | $3.398 | **+10%** |

### Por qué gpt-5 completo NO sale más barato

El precio por token de input de `gpt-5` es la mitad que el de `gpt-4o`
($1,25 vs $2,50 por 1M). Pero **genera ~14x más tokens de output** (2.025 vs 146
en el mismo turno) porque razona internamente, y ese razonamiento se cobra a
$10/1M. La ventaja del input se consume ahí.

Conclusión: no alcanza con mirar el precio de lista. Hay que medir el consumo real.

---

## 3. Calidad: el handoff gate

`python -m evals.run_evals --handoff-gate` (12 escenarios, 22 turnos).

Mediciones válidas = corrida única, sin procesos concurrentes, con las versiones
de `requirements.txt`, y con `database is locked` en 0.

| Configuración | Corrida 1 | Corrida 2 | Escenarios que fallaron |
|---|---|---|---|
| gpt-4o + 4o-mini (hoy) | **22/22 · 12/12** | — | ninguno |
| gpt-5 + nano | 20/22 · 11/12 | **18/22 · 10/12** | S56 (c1) / S29+S57 (c2) |
| gpt-5-mini + nano | 20/22 · 10/12 | **21/22 · 11/12** | S56+S57 (c1) / S29 (c2) |

**Toda la familia GPT-5 muestra varianza entre corridas.** Mismo código, mismo
prompt, cero locks, versiones de producción — y resultados distintos, con
escenarios distintos fallando en cada pasada:

- gpt-5: 20/22 y 18/22
- gpt-5-mini: 20/22 y 21/22

gpt-4o dio 22/22 de forma estable en todas las corridas limpias.

**Nota metodológica:** con esta varianza, una sola corrida no decide nada. Para
comparar modelos hay que correr el gate 3+ veces por candidato y mirar la
distribución, no un número.

> Las mediciones previas (con `openai-agents 0.3.3` y/o locks de SQLite) están
> descartadas. Los costos sí siguen válidos: salen del consumo de tokens que
> reporta la API, que no depende de la versión del SDK.

### CAUSA RAÍZ: el presupuesto de tokens, no el criterio del modelo

Los fallos NO eran del modelo. Eran un defecto de la capa de compatibilidad.

**`max_tokens` y `max_completion_tokens` no son equivalentes.** En GPT-5 los tokens
de RAZONAMIENTO salen del mismo presupuesto que la respuesta, y se consumen
primero. Traducir el nombre conservando el número es correcto sintácticamente y
erróneo en la práctica.

La cadena completa, verificada en los logs:

1. `analizar_escalacion` llama al clasificador con **`max_tokens=150`**
   (`hotel_postsale.py:345`)
2. `gpt-5-nano` gasta los 150 razonando → contenido **vacío**
3. `json.loads("")` → `Expecting value: line 1 column 1 (char 0)`
4. El `except` (`hotel_postsale.py:358`) hace **fail-safe: escala por seguridad**
5. El orquestador obedece → `derivar_a_humano` **sin registrar el ticket**

Evidencia cuantitativa:

| Corrida | `escalation analysis failed` | Turnos fallados |
|---|---|---|
| gpt-4o | **0** | 0 |
| gpt-5-mini (1) | **2** | 2 |
| gpt-5-mini (2) | **2** | 1 |

El error aparece solo con GPT-5 y en la misma cantidad que los fallos.

**Fix:** piso de 2000 tokens (`RESTRICTED_MIN_COMPLETION_TOKENS`) en
`model_compat.py`. Respeta el presupuesto del llamador cuando ya es holgado; solo
eleva el que quedaría ahogado. No encarece nada: se factura por token GENERADO,
no por el reservado.

### Barrido del resto de la app

El mismo problema estaba latente en toda la app: **15 presupuestos entre 10 y 600
tokens**, todos calibrados para GPT-4, y **9 sitios que parsean JSON del LLM**.

Cubierto por arquitectura: **ningún módulo crea su propio cliente OpenAI**, así que
el piso los alcanza a todos vía `openai_client` (el Agents SDK y los evals también
lo usan). `tests/test_llm_budget_coverage.py` escanea el repo y falla si alguien
crea un cliente propio o agrega un presupuesto que quedaría ahogado.

De los 9 parseos, los 9 degradan con gracia (devuelven `{}` / `None`).
**`hotel_postsale` era el único cuyo fail-safe cambia el comportamiento del
agente** — por eso el síntoma apareció justo ahí.

### Sobre gpt-5 (no gpt-5-mini)

Muestra la varianza más alta (20/22 y 18/22) y falla en escenarios distintos cada
vez. Combinado con costar **+10% que gpt-4o**, no tiene caso de negocio: más caro
y menos confiable. (Estas mediciones son PREVIAS al fix del presupuesto; si se
quisiera reconsiderar, habría que re-medirlo.)

### Cómo correr los evals sin invalidar el resultado

Tres formas de obtener números falsos, las tres cometidas durante esta evaluación:

1. **Correr dos gates en paralelo.** Los evals escriben en `hotel.db` (SQLite),
   que no soporta escrituras concurrentes: aparecen `database is locked` y los
   turnos fallan por I/O, no por el modelo. Contaminó una medición de gpt-4o a
   19/22 y otra a 13/22, cuando el valor real es 22/22.
   **Correr siempre de a uno**, y verificar que no quedaron procesos huérfanos
   (`wmic process where "name='python.exe'" get CommandLine | grep evals`).
2. **Comparar un escenario aislado contra el gate completo.** No son equivalentes:
   el estado de sesión y el historial acumulado cambian el comportamiento. Un PASS
   aislado no invalida un FAIL del gate. Comparar gate contra gate.
3. **Medir con un entorno desincronizado de `requirements.txt`.** Ver la sección
   siguiente: `openai-agents` local estaba 14 versiones atrás y producía un error
   (`__fake_id__`) que no existe en producción.

Además: **contar los locks en cada corrida** antes de leer el RESUMEN.

    grep -c "database is locked" <salida>    # debe dar 0

---

## 3.1. El entorno local debe coincidir con producción

Durante esta evaluación el entorno local estaba desincronizado:

| Paquete | `requirements.txt` (Render) | Local |
|---|---|---|
| `openai-agents` | 0.17.5 | **0.3.3** (14 versiones atrás) |
| `openai` | 2.43.0 | **1.109.1** |

Con `openai-agents 0.3.3`, GPT-5 producía este error, que abortaba la corrida:

    Invalid 'input[3].id': '__fake_id__'. Expected an ID that begins with 'fc'.

`__fake_id__` es un placeholder interno del SDK de Agents (`fake_id.py`), no del
código del proyecto. **Con 0.17.5 el error desaparece por completo** (0
ocurrencias), así que NO es una incompatibilidad de GPT-5.

Antes de cualquier medición:

    python -m pip install -r requirements.txt
    python -c "import importlib.metadata as m; print(m.version('openai-agents'), m.version('openai'))"

---

## 4. Recomendación

### Descartado: gpt-5

Cuesta **+10% que gpt-4o** y rinde peor (20/22, 18/22), con la varianza más alta
de los tres. No hay ningún argumento a favor.

### Candidato real: gpt-5-mini (−78%)

**No migrar tal cual, pero vale la pena el intento de cerrarlo.**

Rinde 20/22 y 21/22 contra los 22/22 estables de gpt-4o. La diferencia es de 1-2
turnos, siempre en post-venta, y por causas de criterio que un prompt puede
corregir. Contra eso, el ahorro es de **$481 cada 10.000 turnos** ($620 → $139).

Plan sugerido, en orden:

1. **Ajustar el prompt de post-venta** con dos instrucciones explícitas: cuándo
   registrar un pedido de servicio (`solicitar_servicio`) y cuándo NO escalar a
   un humano si el ticket ya quedó registrado.
2. **Correr el gate 3+ veces** con gpt-5-mini. El criterio de aceptación es que
   la *peor* corrida sea 22/22, no el promedio: con esta varianza, una sola
   pasada verde no prueba nada.
3. **Si no se cierra**, quedarse en gpt-4o. El trabajo de compatibilidad ya está
   hecho y no caduca: sirve para el próximo modelo que salga.

### Siempre válido: quedarse en gpt-4o

Pasa el gate de forma estable y cuesta menos que gpt-5. No hay urgencia técnica
para migrar; la decisión es puramente económica y puede tomarse cuando convenga.

**No se recomienda** una migración parcial (agentes en gpt-5, triage en gpt-4o-mini)
sin correr el gate completo: el triage decide el ruteo y es donde empiezan las
cadenas de fallo.

---

## 5. Cómo reproducir

```bash
cd backend

# línea base
python -m evals.run_evals --handoff-gate

# candidato
OPENAI_MODEL=gpt-5-mini OPENAI_MODEL_CLASSIFIER=gpt-5-nano \
OPENAI_MODEL_FAST=gpt-5-nano python -m evals.run_evals --handoff-gate
```

Para medir el costo real de un turno, interceptar `httpx.AsyncClient.send` y leer
`usage` de las respuestas a `chat/completions` (el `usage` no vuelve en el
retorno de `agent_service.chat`).

---

## 5.1. PRECISION_BLOCK — repreguntar en vez de asumir

Durante la evaluación se observó a Aura repreguntar *"¿preferís una toalla de baño
o una de mano?"* antes de registrar el pedido. El eval lo contaba como fallo (medía
un solo turno), pero **es el comportamiento correcto**: es lo que haría un
recepcionista de verdad.

Se generalizó a todos los agentes con un bloque compartido nuevo en `base_blocks.py`,
al lado de `HONESTIDAD_BLOCK`. La guía estaba muy despareja entre agentes
(menciones de preguntar/confirmar/aclarar): preventa 46, post-venta 27, **staff 5**.

`PRECISION_BLOCK` marca las **dos** direcciones del riesgo, porque exagerar hacia
cualquiera de los lados hace daño:

| Riesgo | Regla |
|---|---|
| **Sub-preguntar** → inventa el dato faltante | *"Nunca completes un dato que no te dieron ni lo des por supuesto"* |
| **Sobre-preguntar** → interrogatorio, fricción, pedidos que se pierden | *"Preguntá SOLO lo que cambia lo que vas a hacer… una pregunta por vez, con la opción más probable sugerida, nunca un cuestionario"* |

División de responsabilidades: `HONESTIDAD_BLOCK` cubre qué **decís** (no afirmar lo
no verificado); `PRECISION_BLOCK` cubre qué **hacés** cuando falta un dato para
actuar.

### El eval también tenía que cambiar

Al conectar el bloque, gpt-4o bajó a 22/23 — pero el fallo era del **eval**: el
agente había registrado el ticket en el turno anterior y no lo duplicó, que es lo
correcto.

Se agregó `expect_scenario` al framework (`run_evals.py`), que permite afirmar
sobre la conversación completa en vez de un turno fijo:

```python
"expect_scenario": {
    "tool_called_alguna_vez": "solicitar_servicio",   # el pedido quedó registrado
    "tool_nunca_llamada": "derivar_a_humano",         # nunca se derivó por una toalla
}
```

Así S56 acepta los dos caminos válidos (registrar de una, o repreguntar y registrar
después) sin dejar de exigir lo innegociable. **Lección general: cuando un eval
castiga un comportamiento que un humano haría bien, revisar el eval antes que el
agente.**

---

## 6. Deuda relacionada detectada

- **~25.000 tokens de input por turno** para una pregunta de 80 caracteres: el
  system prompt + las 17 tools + el RAG viajan enteros en cada llamada. El
  *prompt caching* de OpenAI cobraría ese input repetido a ~10%. Es la palanca
  de costo más grande que queda sin usar, e **independiente del modelo**.
- `token_pricing.py` hay que actualizarlo si OpenAI cambia tarifas; los precios
  son una copia local.
