"""
Runner de evaluación end-to-end del agente Aura.

Corre cada escenario (conversación multi-turno) contra el agente REAL (LLM incluido),
llamando a `agent_service.chat()` — la misma entrada del endpoint web y de WhatsApp —
y verifica cada turno con aserciones determinísticas (route, tools, cards, substrings).

Uso:
    python -m evals.run_evals               # corre todos los escenarios
    python -m evals.run_evals --scenario S5 # corre solo S5 (iterar barato)
    python -m evals.run_evals --list        # lista los escenarios

Requiere OPENAI_API_KEY y la DB real sembrada (habitaciones, carta, promos). Gasta OpenAI:
es una suite ON-DEMAND, separada de los unit tests de `tests/` (que mockean el LLM).
"""
import argparse
import asyncio
import re
import sys
import time
import uuid

# Importar la app completa garantiza que TODOS los modelos SQLAlchemy queden registrados
# (las relaciones de Booking referencian ExtraCharge, etc.); de lo contrario, llamar a
# agent_service.chat() fuera del arranque normal rompe la inicialización de mappers.
import app.main  # noqa: F401  (efecto: registra modelos y routers)

from app.models.database import SessionLocal
from app.services.agent_service import agent_service
from app.routers import chat as chat_router
from evals.scenarios import SCENARIOS


# ── Captura de cards: replica la lógica de cards del endpoint (chat.py) ──────────
def _build_cards(result: dict, user_message: str, session_id: str, db) -> list:
    """Reconstruye las cards del turno igual que el endpoint /api/chat/message.

    Reusa los mismos helpers de chat.py para que la eval vea exactamente lo que vería el
    frontend. Devuelve la lista de tipos de card (["room", "date_picker", ...]).
    """
    cards = chat_router._build_room_cards(result.get("rooms_offered", []))
    promo_offer = result.get("promo_offer")
    menu_card = result.get("menu_card")
    table_card = result.get("table_card")
    room_photos_card = result.get("room_photos_card")
    if room_photos_card:
        cards = [room_photos_card]
    elif promo_offer:
        cards = [chat_router._build_promo_card(promo_offer)]
    elif menu_card:
        cards = [menu_card]
    elif table_card:
        cards = [table_card]
    elif chat_router._vague_dates_no_day(
        user_message, agent_service.conversation_history.get(session_id, []),
    ):
        cards = [chat_router._date_picker_card(chat_router._suggested_month(user_message))]
    elif chat_router._should_offer_datepicker(
        result.get("response", ""), result.get("tools_used", []),
        has_room_cards=bool(cards), context_type=result.get("context_type", ""),
        dates_given=chat_router._dates_already_given(
            user_message, agent_service.conversation_history.get(session_id, []),
        ),
    ):
        cards = [chat_router._date_picker_card()]
    elif chat_router._should_offer_table(
        user_message, result.get("tools_used", []),
        has_other_cards=bool(cards), context_type=result.get("context_type", ""),
    ):
        cards = [chat_router._build_table_card_fallback(db, session_id)]
    elif chat_router._should_offer_menu(
        user_message, result.get("tools_used", []),
        has_other_cards=bool(cards), context_type=result.get("context_type", ""), db=db,
    ):
        fb = chat_router._build_menu_card_fallback(db, session_id, user_message)
        if fb:
            cards = [fb]
    return [c.get("type") for c in (cards or [])]


def _route_of(result: dict) -> str:
    """Normaliza la rama del turno a 'casual' | 'postsale' | 'preventa'."""
    ct = result.get("context_type")
    if ct in ("casual", "postsale"):
        return ct
    return "preventa"  # pre-venta no setea context_type explícito


# Captura montos "USD 360", "USD 1,155", "USD1200" (normaliza a entero, sin separadores).
_USD_RE = re.compile(r"usd\s*\$?\s*([\d][\d.,]*)", re.IGNORECASE)


def _usd_amounts(text: str) -> set:
    """Extrae los montos en USD que aparecen en un texto, como enteros (ignora decimales)."""
    out = set()
    for m in _USD_RE.finditer(text or ""):
        digits = m.group(1).replace(".", "").replace(",", "")
        if digits.isdigit():
            out.add(int(digits))
    return out


def _real_prices_from_trace(tool_trace: list) -> set:
    """Precios USD reales que devolvió `consultar_disponibilidad`/`calcular_precio_promo`."""
    prices = set()
    for t in tool_trace or []:
        if t.get("name") in ("consultar_disponibilidad", "calcular_precio_promo"):
            prices |= _usd_amounts(str(t.get("output") or ""))
    return prices


# ── Aserciones ──────────────────────────────────────────────────────────────────
def _as_list(v):
    return v if isinstance(v, list) else [v]


def _check_turn(expect: dict, route: str, tools: list, cards: list, response: str,
                tool_called_any: bool, real_prices: set) -> list:
    """Devuelve la lista de fallos (strings). Vacía = turno OK.

    `real_prices` = precios USD que las tools devolvieron en el escenario hasta este turno;
    se usa para la aserción `price_from_tool` (detecta precios inventados/alucinados).
    """
    fails = []
    resp_low = (response or "").lower()

    if "route" in expect and route != expect["route"]:
        fails.append(f"route={route!r}, esperaba {expect['route']!r}")

    if "tool_called" in expect:
        want = _as_list(expect["tool_called"])
        if tool_called_any:
            if not any(t in tools for t in want):
                fails.append(f"ninguna de {want} fue llamada (tools={tools})")
        else:
            for t in want:
                if t not in tools:
                    fails.append(f"tool {t!r} no se llamó (tools={tools})")

    if "tool_not_called" in expect:
        for t in _as_list(expect["tool_not_called"]):
            if t in tools:
                fails.append(f"tool {t!r} NO debía llamarse")

    if "card" in expect:
        for c in _as_list(expect["card"]):
            if c not in cards:
                fails.append(f"falta card {c!r} (cards={cards})")

    if "no_card" in expect:
        for c in _as_list(expect["no_card"]):
            if c in cards:
                fails.append(f"card {c!r} NO debía aparecer (cards={cards})")

    if "response_contains" in expect:
        for s in _as_list(expect["response_contains"]):
            if s.lower() not in resp_low:
                fails.append(f"la respuesta no contiene {s!r}")

    if "response_not_contains" in expect:
        for s in _as_list(expect["response_not_contains"]):
            if s.lower() in resp_low:
                fails.append(f"la respuesta contiene lo prohibido {s!r}")

    # Igual que el anterior pero por PALABRA COMPLETA (\b): para términos cortos como
    # "spa"/"sauna" que darían falso positivo por substring (espacio, español, huéspedes).
    if "response_not_contains_word" in expect:
        for s in _as_list(expect["response_not_contains_word"]):
            if re.search(rf"\b{re.escape(s.lower())}\b", resp_low):
                fails.append(f"la respuesta menciona (palabra) lo prohibido {s!r}")

    # Precio anti-alucinación: cualquier "USD X" mencionado debe ser uno de los que devolvieron
    # las tools de precio en el escenario. Un monto que la tool nunca dio = precio inventado.
    if expect.get("price_from_tool"):
        said = _usd_amounts(response)
        invented = {p for p in said if p not in real_prices}
        if invented:
            fails.append(f"precio(s) inventado(s) {sorted(invented)} "
                         f"(reales de la tool: {sorted(real_prices) or '∅'})")

    return fails


# ── Ejecución ────────────────────────────────────────────────────────────────────
async def _run_scenario(sc: dict) -> dict:
    db = SessionLocal()
    prefix = sc.get("session_prefix") or "web-eval"
    session_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    tool_any = sc.get("tool_called_any", False)
    turn_results = []
    real_prices = set()  # precios USD reales acumulados de las tools a lo largo del escenario
    try:
        for i, turn in enumerate(sc["turns"], 1):
            msg = turn["user"]
            result = await agent_service.chat(db, msg, session_id, "es")
            route = _route_of(result)
            tools = result.get("tools_used", []) or []
            cards = _build_cards(result, msg, session_id, db)
            response = result.get("response", "")
            real_prices |= _real_prices_from_trace(result.get("tool_trace", []))
            fails = _check_turn(turn.get("expect", {}), route, tools, cards, response,
                                tool_any, real_prices)
            turn_results.append({
                "n": i, "user": msg, "route": route, "tools": tools,
                "cards": cards, "response": response, "fails": fails,
            })
    finally:
        db.close()
    return {"id": sc["id"], "name": sc["name"], "session_id": session_id, "turns": turn_results}


def _cleanup(session_ids: list) -> None:
    """Borra los datos que los evals crearon (reservas, mesas, tickets, leads) por session_id.

    Los evals corren contra la DB real y crean reservas reales; sin esta limpieza, cada corrida
    satura el inventario (ej. la habitación accesible tiene 2 plazas) y ensucia la base. Best-effort.
    """
    if not session_ids:
        return
    db = SessionLocal()
    try:
        from app.models.hotel import Booking, HotelTicket
        from app.models.lead import Lead
        deleted = 0
        for sid in session_ids:
            for Model in (Booking, HotelTicket, Lead):
                try:
                    n = db.query(Model).filter(Model.session_id == sid).delete(synchronize_session=False)
                    deleted += n or 0
                except Exception:
                    db.rollback()
            # Reservas de mesa (si el modelo existe)
            try:
                from app.models.restaurant import TableReservation
                db.query(TableReservation).filter(
                    TableReservation.session_id == sid
                ).delete(synchronize_session=False)
            except Exception:
                db.rollback()
        db.commit()
        print(f"\n[limpieza] {deleted} registros de eval borrados ({len(session_ids)} sesiones).")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"\n[!] Limpieza fallo (no critico): {e}")
    finally:
        db.close()


def _print_report(reports: list) -> int:
    total_turns = ok_turns = 0
    failed_scenarios = []
    for r in reports:
        sc_failed = False
        print(f"\n{'='*72}\n[{r['id']}] {r['name']}")
        for t in r["turns"]:
            total_turns += 1
            status = "PASS" if not t["fails"] else "FAIL"
            if t["fails"]:
                sc_failed = True
            else:
                ok_turns += 1
            print(f"  T{t['n']} {status}  route={t['route']} tools={t['tools']} cards={t['cards']}")
            print(f"       user: {t['user'][:90]}")
            if t["fails"]:
                for f in t["fails"]:
                    print(f"       ✗ {f}")
                print(f"       resp: {t['response'][:160]}")
        if sc_failed:
            failed_scenarios.append(r["id"])
    print(f"\n{'='*72}\nRESUMEN: {ok_turns}/{total_turns} turnos OK · "
          f"{len(reports)-len(failed_scenarios)}/{len(reports)} escenarios limpios")
    if failed_scenarios:
        print(f"Escenarios con fallos: {', '.join(failed_scenarios)}")
    return 1 if failed_scenarios else 0


async def _main_async(selected):
    scen = [s for s in SCENARIOS if (not selected or s["id"] in selected)]
    if not scen:
        print(f"No hay escenarios que coincidan con {selected}")
        return 2
    print(f"Corriendo {len(scen)} escenario(s) contra el agente real…")
    t0 = time.time()
    reports = []
    for sc in scen:
        reports.append(await _run_scenario(sc))
    rc = _print_report(reports)
    print(f"\nTiempo total: {time.time()-t0:.1f}s")
    # Limpiar lo que crearon los evals (reservas/mesas/tickets/leads) para que la corrida sea
    # repetible y no sature el inventario de la DB real.
    _cleanup([r["session_id"] for r in reports])
    return rc


def main():
    ap = argparse.ArgumentParser(description="Evaluación end-to-end del agente Aura")
    ap.add_argument("--scenario", "-s", action="append",
                    help="ID(s) de escenario a correr (ej. -s S5 -s S6). Por defecto, todos.")
    ap.add_argument("--list", action="store_true", help="Lista los escenarios y sale.")
    args = ap.parse_args()

    if args.list:
        for s in SCENARIOS:
            print(f"  {s['id']:4} {s['name']}  ({len(s['turns'])} turnos)")
        return

    selected = set(args.scenario) if args.scenario else None
    rc = asyncio.run(_main_async(selected))
    sys.exit(rc)


if __name__ == "__main__":
    main()
