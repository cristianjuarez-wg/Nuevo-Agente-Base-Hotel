# Evals — pruebas end-to-end del agente Aura

A diferencia de los unit tests de `tests/` (que **mockean OpenAI** y prueban lógica
determinística), estas evals corren conversaciones reales contra el **agente con LLM**,
con inputs como los de un huésped real (typos, charla informal, varias preguntas juntas,
datos en desorden, referencias a turnos previos). Sirven para encontrar los problemas que
los unit tests no ven.

## Correr

```bash
cd backend
python -m evals.run_evals            # todos los escenarios (~50-75 llamadas OpenAI, ~2-3 min)
python -m evals.run_evals -s S5      # solo S5 (iterar barato)
python -m evals.run_evals -s S5 -s S6
python -m evals.run_evals --list     # ver los escenarios
```

> **Limpieza automática**: al terminar, el runner borra las reservas/mesas/tickets/leads que
> creó (por `session_id`), para que cada corrida sea repetible. Si interrumpís la corrida a la
> mitad, puede quedar data de eval; volvé a correr para que limpie, o borrá por `session_id`
> con prefijo `web-eval`. Nota: la limpieza es AL FINAL, no entre escenarios — en una corrida
> completa larga, varias reservas conviven y pueden saturar una habitación de pocas plazas
> (ej. la accesible tiene 2), lo que ocasionalmente hace que un escenario de precios/cards
> falle de forma espuria. Si un escenario falla en la suite completa pero pasa con `-s SXX`
> aislado, es esto, no un bug del agente.

Requiere `OPENAI_API_KEY` y la DB de desarrollo sembrada (habitaciones, carta, promos).
**Gasta OpenAI** y escribe datos demo (leads/reservas de prueba) en la DB — por eso es
on-demand, no parte de `pytest` ni de CI.

## Cómo leer el resultado

Cada turno imprime `PASS`/`FAIL` con `route`, `tools` y `cards` reales, y el detalle de
cada aserción que falló. El framework "muerde": si una aserción no se cumple, falla con el
motivo exacto.

## Agregar un escenario (cuando encuentres un bug nuevo)

Editá `evals/scenarios.py` y sumá un dict a `SCENARIOS`. Reproducí la charla que rompió el
agente, y declará en cada turno lo que esperás. Aserciones disponibles (todas opcionales):

| clave | qué chequea |
|-------|-------------|
| `route` | "preventa" \| "casual" \| "postsale" |
| `tool_called` / `tool_not_called` | tool(s) que deben / no deben invocarse |
| `card` / `no_card` | card que debe / no debe aparecer (room, date_picker, menu_interactive, table_reservation) |
| `response_contains` / `response_not_contains` | substrings que la respuesta debe / no debe tener |
| `price_from_tool: True` | todo "USD X" en la respuesta debe ser un precio que devolvió una tool en el escenario (caza precios inventados/alucinados) |

`session_prefix: "wa_549..."` simula un huésped de WhatsApp. `tool_called_any: True` a nivel
de escenario hace que `tool_called` con varias opciones pase si llamó **al menos una**.

La idea: **cada vez que encuentres un problema probando a mano, agregá el escenario acá**.
Así el bug queda cubierto para siempre y se detecta si vuelve.

---

## Simulador de huésped + LLM-as-judge (Workstream T.2)

Además de los escenarios deterministas (mensajes fijos), hay un modo **simulador**: un LLM barato
(`OPENAI_MODEL_FAST`) juega el papel de un huésped con una PERSONA y conversa N turnos contra el
agente real; luego un **juez** (otro LLM) evalúa la conversación con salida estructurada,
contrastando lo que el agente afirmó contra el `tool_trace` real (para detectar invenciones
objetivamente) y contra los `facts` del negocio.

```
python -m evals.run_evals --sim                          # todas las personas × F2
python -m evals.run_evals --sim --persona regateador --flow F2
python -m evals.run_evals --sim --persona apurado --persona enojado
```

**7 personas** (`evals/simulator.py`): apurado, indeciso, desprolijo, enojado, extranjero,
regateador, distraido. Cada una tiene un `goal` y un `satisfied_when` que el juez usa.

El **juez** (`evals/judge.py`) devuelve `{goal_achieved, invented_facts[], tone_ok,
rules_respected{descuento_no_default, alergia_segura, cbu_exacto, no_datos_de_otro_huesped,
no_inventa_precio}, notes, ok}`. `ok = sin invenciones Y todas las reglas respetadas`.
`tests/test_judge.py` prueba que el juez DETECTA una invención sembrada (sin ese test, el juez
podría decir siempre "todo bien"); se saltea sin `OPENAI_API_KEY` real.

**Determinismo razonable (gate):** el simulador y el juez son estocásticos. Criterio de gate por
`(persona, flujo)`: **2 de 3 corridas verdes**. Correr la simulación 3 veces y exigir mayoría.

**Costo:** cada simulación ≈ `(max_turns × 2 llamadas: persona + agente) + 1 llamada juez`, con
`OPENAI_MODEL_FAST` (gpt-4o-mini). Una corrida de referencia (7 personas × 1 flujo) tardó ~5 min.
Una corrida completa (7 personas × ~5 flujos × 3 repeticiones) es cara/lenta: **NO va en el smoke
de CI** — se corre a mano como gate pre-release y por instancia nueva (ver
`docs/RUNBOOK_NUEVA_INSTANCIA.md`). El smoke de CI sigue siendo los escenarios fijos.

Corrida de referencia (2026-07-10, 7 personas × F2): 7/7 PASS, 0 invenciones. `enojado` da
`goal=False` correctamente (es persona de post-venta, su objetivo no aplica a F2/disponibilidad).
