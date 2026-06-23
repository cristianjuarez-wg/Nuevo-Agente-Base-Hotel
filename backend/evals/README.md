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
