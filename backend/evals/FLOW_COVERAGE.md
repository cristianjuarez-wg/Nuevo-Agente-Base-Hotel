# Matriz de cobertura de flujos (Workstream T.1)

> **Qué es:** el mapa entre los **12 flujos críticos** del negocio (plan de productización §T.1)
> y los **escenarios de eval** que los cubren (`evals/scenarios.py`). Sirve para que los EVAL
> GATES exijan "matriz completa en verde", no solo un pass-rate agregado.
>
> **Regla:** un flujo está 🟢 si tiene al menos un escenario que ejercita su camino feliz Y sus
> variantes obligatorias. 🟡 si el camino feliz está cubierto pero falta una variante. 🔴 si no
> hay ningún escenario.
>
> **Estado de la corrida:** `evals/scenarios.py` tiene **52 escenarios** (48 `core` + 4 `instance`)
> con verificación 100% determinística (sin juez ni simulador — eso es T.2). Partición Fase 3.3:
> `run_evals --tier core|instance` filtra; `run_evals --smoke` corre el subconjunto barato de CI
> (8 escenarios núcleo). La última corrida verde se anota abajo (gasta OpenAI).

Última corrida registrada: 2026-07-10 — S43–S47 (F8/F9) limpios; **smoke 8/8** verde. Suite completa (48): pendiente en el próximo EVAL GATE.

---

## Matriz

| # | Flujo | Camino feliz | Variantes obligatorias | Escenarios | Estado |
|---|---|---|---|---|---|
| **F1** | Pre-venta informativa | pregunta por hotel/servicios → `info_hotel` (RAG) | pregunta por algo que NO existe (facts) | S2, S16, S19, S20 | 🟢 |
| **F2** | Disponibilidad → reserva | fechas + pax → cards `room` → `crear_reserva` | fechas ambiguas/vagas, cambio de fechas, sin pax, datos desordenados | S1, S1b, S1c, S4, S9, S13, S14, S30, S31, S32, S35, S36, S37, S38, S40 | 🟢 |
| **F3** | Captación de lead | interés sin reservar → pedir contacto | huésped que no da datos; variante flow "sin_presión" | S14 (parcial) | 🟡 |
| **F4** | Promos y objeción de precio | objeción → `calcular_precio_promo` | pedir descuento directo (política: no default) | S3 | 🟡 |
| **F5** | Restaurante | ver carta → armar pedido → registrar / reservar mesa | pedido con alérgeno declarado → NO confirmar el plato | S5, S10, S13, S15, S24, S25 | 🟡 |
| **F6** | Post-venta | código de reserva → consulta/ticket | escalación; queja con enojo | S18, S19, S20, S21, S22, S23, S27, S28, S29, S33, S34 | 🟡 |
| **F7** | Triage y cortocircuitos | casual→casual, precio→pre, código→post | mensaje mixto ("hola! tenés lugar el 15?") | S1, S6, S11, S12, S17, S41, S42 | 🟢 |
| **F8** | Pago | pedir CBU/alias → exacto desde tool | intentar que "ajuste" el CBU | S43, S44 | 🟢 |
| **F9** | Seguridad | jailbreak simple; inyección vía documento RAG | pedir datos de otro huésped | S45, S46, S47 (jailbreak + terceros + inyección RAG) | 🟢 |
| **F10** | Owner (BI) | métrica simple → dato real vs estimación etiquetados | pregunta sin datos → admite no saber | S48, S49 | 🟢 |
| **F11** | Staff | cerrar/crear ticket | pedido fuera de dominio → reconduce | S50, S51 | 🟢 |
| **F12** | Canal WhatsApp | F2 por `wa_` (formato cards limitado) | concurrencia (ya hay test unitario) | S7 | 🟡 |

**Resumen:** 7 🟢 · 5 🟡 · 0 🔴 sobre 12 flujos.

**F10/F11 cubiertos (Tarea C):** owner y staff NO pasan por `agent_service.chat` — el runner los
despacha a sus orquestadores (`owner_orchestrator.run` / `staff_orchestrator.run`) con un
`StaffMember` sembrado (campo `agent: "owner"|"staff"` en el escenario + `_seed_staff`/`_cleanup_staff`).
S48 (owner llama consultar_ocupacion), S49 (no inventa facturación futura), S50 (staff crea ticket),
S51 (pedido fuera de dominio → reconduce). 4/4 verde contra el agente real.

**F8 y F9 cubiertos (2026-07-10):** S43 (CBU/alias exacto desde `info_pago`), S44 (se niega a
emitir un CBU alterado), S45 (no obedece jailbreak de descuento), S46 (no divulga datos de otro
huésped). Los 4 corridos contra el agente real: 4/4 limpios. F9 queda 🟡 (no 🟢) porque falta la
**inyección vía documento RAG**, que se escribe con la tarea 3.3 (delimitadores + regla anti-injection).
El runner ganó `setup_payments` (siembra una entry de pagos con datos conocidos y la limpia por
título marcador) para que el assert del CBU sea determinístico e independiente del dato del hotel.

---

## Huecos priorizados (qué escribir)

Ordenados por riesgo de negocio (lo que más duele si se rompe sin que nos enteremos):

### ✅ Cerrados
- **F8 Pago** → S43 (CBU/alias exacto vía `info_pago`) + S44 (no emite CBU alterado). 🟢
- **F9 Seguridad** → S45 (jailbreak) + S46 (datos de terceros) + S47 (inyección vía RAG, con la
  defensa anti-injection de la tarea 3.3). 🟢
- **F10 Owner** → S48 (métrica de tool) + S49 (no inventa métrica futura). 🟢 (Tarea C)
- **F11 Staff** → S50 (crea ticket) + S51 (fuera de dominio → reconduce). 🟢 (Tarea C)

### 🟡 Prioridad media — camino feliz cubierto, falta la variante dura
5. **F3** — variante "huésped que se niega a dar datos" y el flow "sin_presión" (no captura).
6. **F4** — "pedir descuento directo": la política es NO dar descuento por default; hoy solo
   está la promo legítima (S3), falta el turno adversario.
7. **F5** — **alérgeno declarado en el pedido**: si el huésped declara un alérgeno y pide un
   plato que lo contiene, el agente NO debe confirmar el plato. Es seguridad alimentaria; alto
   valor pese a ser 🟡.
8. **F6** — **escalación y queja con enojo**: el post-venta cubre servicios/preferencias/tickets
   pero falta el camino de `analizar_escalacion` y el tono ante una queja airada.
9. **F12** — la variante de concurrencia existe como test unitario (no como escenario de eval);
   documentar el cruce o portarla.

---

## Cómo se mantiene

- Cada vez que se agrega un escenario a `evals/scenarios.py`, sumar su id a la fila del flujo
  que cubre y reevaluar el color.
- Los EVAL GATES del plan (fin de 0.1, 1.6, 2.2, 2.7, y cada gate de Fase 3) pasan a exigir que
  **ningún flujo esté 🔴** y que los flujos tocados por la fase estén 🟢.
- T.2 (simulador de huésped + juez) se monta sobre estos mismos flujos: las personas del
  simulador ejercitan F1–F12 de forma estocástica, complementando —no reemplazando— estos
  escenarios determinísticos.
