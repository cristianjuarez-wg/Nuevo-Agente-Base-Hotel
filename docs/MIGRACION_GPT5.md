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

| Configuración | Resultado |
|---|---|
| gpt-4o + 4o-mini (hoy) | **22/22 turnos · 12/12 escenarios** |
| gpt-5-mini + nano | **20/22 turnos · 10/12 escenarios** |
| gpt-5 + nano | ver corrida completa |

### El fallo de gpt-5-mini: una sola causa raíz

S29 y S57 fallan el mismo turno, y **no son dos problemas sino uno**:

- **T1** pide *"Reservá la King del … para 2 adultos"* y espera `crear_reserva`.
  `gpt-5-mini` llama solo `consultar_disponibilidad` y se detiene — no ejecuta
  la reserva.
- **T2** ("el aire no anda") entonces cae en pre-venta y deriva a un humano, en
  vez de registrar el ticket de post-venta. **Es consecuencia del T1**: sin
  reserva creada, el huésped no está alojado.

`gpt-5-mini` es más conservador para ejecutar tools que escriben en la base de
datos. Aislando los escenarios el fallo se agrava (1/5 turnos), así que es
sistemático, no ruido.

`gpt-5` completo pasa **5/5** en esos mismos escenarios.

---

## 4. Recomendación

**No migrar a `gpt-5-mini` tal cual.** El −78% de costo es muy atractivo, pero
falla el gate que la propia doc del proyecto marca como obligatorio, y falla en
algo que importa: no completa reservas.

Tres caminos, en orden de preferencia:

1. **Quedarse en gpt-4o por ahora.** El código ya es compatible; la migración
   queda disponible cuando se decida. Costo cero, riesgo cero.
2. **Ajustar el prompt para gpt-5-mini y volver a correr el gate.** El fallo es
   de criterio ("¿ejecuto la reserva o pregunto primero?"), no técnico, así que
   es plausible cerrarlo con instrucción explícita. Si funciona, se gana el −78%.
3. **Migrar a `gpt-5` completo** si se prioriza capacidad sobre costo. Pasa los
   escenarios críticos, pero cuesta 10% más que hoy.

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
