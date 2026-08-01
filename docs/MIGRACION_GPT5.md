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

### Qué falla realmente

**Con el SDK correcto, `gpt-5-mini` sí crea las reservas.** El diagnóstico previo
("no ejecuta `crear_reserva`") era artefacto de `openai-agents 0.3.3`. Con 0.17.5
el T1 pasa con `['consultar_disponibilidad', 'crear_reserva']`.

Los fallos que quedan son de **post-venta**, y son de dos tipos:

| Tipo | Ejemplo | Gravedad |
|---|---|---|
| **No registra el pedido** | S56 T2: *"mandame una toalla limpia"* → `tools=[]`. No queda ticket. | Alta: el pedido se pierde |
| **Escala de más** | S57/S29 T2: *"el aire no anda"* → llama `solicitar_servicio` **y también** `derivar_a_humano`, que el escenario prohíbe | Baja: registra el ticket igual, solo avisa a una persona de más |

El segundo tipo es casi cosmético (hace el trabajo y además escala). El primero sí
importa.

Ambos son de **criterio**, no técnicos, así que son plausibles de cerrar con
instrucciones explícitas en el prompt de post-venta: cuándo registrar un pedido
de servicio, y cuándo NO escalar a un humano.

### Sobre gpt-5 (no gpt-5-mini)

Muestra la varianza más alta (20/22 y 18/22) y falla en escenarios distintos cada
vez, incluyendo la creación de reservas. Combinado con costar **+10% que gpt-4o**,
no tiene caso de negocio: más caro y menos confiable.

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

## 6. Deuda relacionada detectada

- **~25.000 tokens de input por turno** para una pregunta de 80 caracteres: el
  system prompt + las 17 tools + el RAG viajan enteros en cada llamada. El
  *prompt caching* de OpenAI cobraría ese input repetido a ~10%. Es la palanca
  de costo más grande que queda sin usar, e **independiente del modelo**.
- `token_pricing.py` hay que actualizarlo si OpenAI cambia tarifas; los precios
  son una copia local.
