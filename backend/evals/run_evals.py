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

# El reporte usa flechas/acentos (→, ñ) en los nombres de escenario. En Windows la consola
# default es cp1252 y `print` explota con UnicodeEncodeError. Forzamos UTF-8 en stdout/stderr
# para que el reporte se imprima igual en cualquier consola (no-op si ya es UTF-8).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Importar la app completa garantiza que TODOS los modelos SQLAlchemy queden registrados
# (las relaciones de Booking referencian ExtraCharge, etc.); de lo contrario, llamar a
# agent_service.chat() fuera del arranque normal rompe la inicialización de mappers.
import app.main  # noqa: F401  (efecto: registra modelos y routers)

from app.models.database import SessionLocal
from app.services.agent_service import agent_service
from app.services import owner_orchestrator, staff_orchestrator  # F10/F11
from app.routers import chat as chat_router
from evals.scenarios import SCENARIOS


# Teléfono marcador del StaffMember que siembra el eval de owner/staff (F10/F11).
_EVAL_STAFF_PHONE = "+5490000000000"


def _seed_staff(db, role: str):
    """Siembra (idempotente) un StaffMember con el rol pedido (owner/staff), necesario para
    invocar sus orquestadores en los evals. Se limpia por teléfono marcador en _cleanup_staff."""
    from app.models.staff import StaffMember
    row = db.query(StaffMember).filter(StaffMember.phone == _EVAL_STAFF_PHONE).first()
    name = "Dueño Eval" if role == "owner" else "Operador Eval"
    if row:
        row.role = role
        row.name = name
        row.active = True
    else:
        row = StaffMember(name=name, phone=_EVAL_STAFF_PHONE, role=role,
                          area="general", active=True)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _cleanup_staff() -> None:
    """Borra el StaffMember marcador que sembró el eval (best-effort)."""
    db = SessionLocal()
    try:
        from app.models.staff import StaffMember
        n = db.query(StaffMember).filter(
            StaffMember.phone == _EVAL_STAFF_PHONE).delete(synchronize_session=False)
        db.commit()
        if n:
            print(f"[limpieza] {n} StaffMember de eval borrado.")
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()


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
    # Catálogo de habitaciones (espeja chat.py): pide ver tipos/fotos antes de dar fechas.
    elif (result.get("context_type", "") not in ("postsale", "casual")
          and chat_router._wants_room_catalog(user_message)
          and not chat_router._dates_already_given(
              user_message, agent_service.conversation_history.get(session_id, []),
          )):
        catalog = chat_router._build_room_catalog_cards(db)
        if catalog:
            cards = catalog
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
                tool_called_any: bool, real_prices: set, room_titles: list = None) -> list:
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

    # Tope de cantidad de tarjetas de habitación (ej. no mostrar las 4).
    if "card_count_max" in expect:
        n_room = len([c for c in cards if c == "room"])
        if n_room > expect["card_count_max"]:
            fails.append(f"{n_room} tarjetas de habitación, máx esperado {expect['card_count_max']}")

    # Una habitación puntual NO debe aparecer entre las tarjetas (ej. la accesible).
    if "card_title_not" in expect:
        titles = room_titles or []
        for t in _as_list(expect["card_title_not"]):
            if t in titles:
                fails.append(f"la habitación {t!r} NO debía aparecer (tarjetas={titles})")

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
def _seed_bookings(db, session_id: str, specs: list) -> None:
    """Siembra reservas de post-venta para el escenario (ej. con una promo aplicada que el
    flujo normal del agente no produce, como Stay & Park, que es cualitativa). Las reservas
    quedan atadas al session_id del escenario, así el _cleanup por session_id las borra.
    Cada spec admite: room_type, nights, guest_name, promo_name (todos opcionales)."""
    from datetime import date, timedelta
    from app.models.hotel import Booking, Room
    for spec in specs:
        room = (
            db.query(Room).filter(Room.room_type == spec.get("room_type", "King")).first()
            or db.query(Room).first()
        )
        if not room:
            continue
        # Idempotente: si un código quedó de una corrida previa que no llegó a limpiar, lo borramos.
        db.query(Booking).filter(Booking.code == spec["code"]).delete(synchronize_session=False)
        nights = int(spec.get("nights", 3))
        ci = date.today() + timedelta(days=30)
        co = ci + timedelta(days=nights)
        total_usd = round((room.base_price_usd or 0) * nights, 2)
        b = Booking(
            code=spec["code"], room_id=room.id, session_id=session_id,
            guest_name=spec.get("guest_name", "Huésped Eval"),
            guest_email="eval@example.com", guest_phone=None,
            check_in=ci, check_out=co, guests=2, children=0, infants=0, nights=nights,
            total_price_usd=total_usd, total_price_ars=round(total_usd * 1490, 2),
            promo_name=spec.get("promo_name"), status="confirmed", payment_status="paid",
            source="web", generated_by="aura",
        )
        db.add(b)
    db.commit()


# Título marcador de la entry de pagos que siembra el eval (para limpiarla después sin tocar
# la entry real del hotel). info_pago toma la de pagos más reciente → la del eval gana en su corrida.
_EVAL_PAYMENTS_TITLE = "[EVAL] Datos de pago de prueba"


def _seed_payments(db, spec: dict) -> None:
    """Siembra una KnowledgeEntry de pagos con datos EXACTOS conocidos, para verificar que el
    agente los comunica sin alterarlos (F8). No lleva session_id (los datos de pago son globales);
    se limpia por su título marcador en _cleanup_payments. Idempotente."""
    from app.models.knowledge import KnowledgeEntry
    db.query(KnowledgeEntry).filter(KnowledgeEntry.title == _EVAL_PAYMENTS_TITLE).delete(
        synchronize_session=False)
    entry = KnowledgeEntry(
        category="pagos", title=_EVAL_PAYMENTS_TITLE,
        content=spec.get("content", "Para reservar, transferí la seña y envianos el comprobante."),
        data={
            "medios": spec.get("medios", ["Transferencia bancaria"]),
            "titular": spec.get("titular", "Hotel Eval SA"),
            "banco": spec.get("banco", "Banco Eval"),
            "cbu": spec["cbu"], "alias": spec["alias"], "moneda": spec.get("moneda", "ARS"),
        },
        status="active",
    )
    db.add(entry)
    db.commit()


def _cleanup_payments() -> None:
    """Borra la entry de pagos marcador que sembró el eval (best-effort)."""
    db = SessionLocal()
    try:
        from app.models.knowledge import KnowledgeEntry
        n = db.query(KnowledgeEntry).filter(
            KnowledgeEntry.title == _EVAL_PAYMENTS_TITLE).delete(synchronize_session=False)
        db.commit()
        if n:
            print(f"[limpieza] {n} entry de pagos de eval borrada.")
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()


# Título marcador de la entry de conocimiento envenenada que siembra el eval de inyección (F9).
_EVAL_KNOWLEDGE_TITLE = "[EVAL] Documento con inyección"


async def _seed_knowledge(db, spec: dict) -> None:
    """Siembra una KnowledgeEntry con contenido que INTENTA una prompt-injection (F9), para
    verificar que el agente NO obedece la orden incrustada en el documento. Se re-ingesta al RAG
    para que info_hotel la pueda recuperar. Se limpia por título marcador."""
    from app.models.knowledge import KnowledgeEntry
    db.query(KnowledgeEntry).filter(KnowledgeEntry.title == _EVAL_KNOWLEDGE_TITLE).delete(
        synchronize_session=False)
    entry = KnowledgeEntry(
        category=spec.get("category", "servicios"),
        title=_EVAL_KNOWLEDGE_TITLE,
        content=spec["content"],
        data={}, status="active",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    # Re-ingesta al RAG para que la tool info_hotel pueda recuperar este documento.
    from app.domains.hotel.services.knowledge_service import reingest
    await reingest(entry)


def _cleanup_knowledge() -> None:
    """Borra la entry de conocimiento envenenada que sembró el eval (best-effort)."""
    db = SessionLocal()
    try:
        from app.models.knowledge import KnowledgeEntry
        n = db.query(KnowledgeEntry).filter(
            KnowledgeEntry.title == _EVAL_KNOWLEDGE_TITLE).delete(synchronize_session=False)
        db.commit()
        if n:
            print(f"[limpieza] {n} entry de conocimiento de eval borrada.")
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()


async def _run_scenario(sc: dict) -> dict:
    db = SessionLocal()
    prefix = sc.get("session_prefix") or "web-eval"
    session_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    tool_any = sc.get("tool_called_any", False)
    turn_results = []
    real_prices = set()  # precios USD reales acumulados de las tools a lo largo del escenario
    try:
        if sc.get("setup_bookings"):
            _seed_bookings(db, session_id, sc["setup_bookings"])
        if sc.get("setup_payments"):
            _seed_payments(db, sc["setup_payments"])
        if sc.get("setup_knowledge"):
            await _seed_knowledge(db, sc["setup_knowledge"])

        # Owner/staff (F10/F11) NO pasan por agent_service.chat: van por sus orquestadores,
        # ruteados por rol. Se siembra un StaffMember y se despacha directo. El historial se
        # mantiene entre turnos (esos orquestadores lo reciben).
        agent_role = sc.get("agent")  # "owner" | "staff" | None (guest, flujo normal)
        staff_member = _seed_staff(db, agent_role) if agent_role in ("owner", "staff") else None
        history: list = []

        for i, turn in enumerate(sc["turns"], 1):
            msg = turn["user"]
            if agent_role == "owner":
                result = await owner_orchestrator.owner_orchestrator.run(
                    db, msg, session_id, history, owner_name=staff_member.name)
            elif agent_role == "staff":
                result = await staff_orchestrator.staff_orchestrator.run(
                    db, staff_member, msg, session_id, history)
            else:
                result = await agent_service.chat(db, msg, session_id, "es")
            route = _route_of(result)
            tools = result.get("tools_used", []) or []
            # Cards y precios reales solo aplican al flujo huésped; owner/staff no los producen.
            cards = _build_cards(result, msg, session_id, db) if not agent_role else []
            room_titles = [r.get("room_type") or "" for r in result.get("rooms_offered", [])]
            response = result.get("response", "")
            real_prices |= _real_prices_from_trace(result.get("tool_trace", []))
            # Mantener el historial de owner/staff entre turnos.
            if agent_role:
                history.append({"role": "user", "content": msg})
                history.append({"role": "assistant", "content": response})
            fails = _check_turn(turn.get("expect", {}), route, tools, cards, response,
                                tool_any, real_prices, room_titles)
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


# Subconjunto SMOKE para CI: barato (~8 escenarios), cubre los flujos núcleo del vertical
# (disponibilidad, reserva, honestidad/anti-invención, pago, seguridad). Se corre en cada PR
# que toque prompts/composers/specs. Los ids son de core_scenarios (genéricos, no del Hampton).
_SMOKE_IDS = {"S2", "S11", "S12", "S30", "S40", "S43", "S45", "S47"}


async def _main_async(selected, smoke=False, tier=None):
    scen = list(SCENARIOS)
    if smoke:
        scen = [s for s in scen if s["id"] in _SMOKE_IDS]
    if tier:
        scen = [s for s in scen if s.get("tier", "core") == tier]
    if selected:
        scen = [s for s in scen if s["id"] in selected]
    if not scen:
        print(f"No hay escenarios que coincidan (selected={selected}, smoke={smoke}, tier={tier})")
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
    _cleanup_payments()
    _cleanup_knowledge()
    _cleanup_staff()
    return rc


from contextlib import contextmanager


@contextmanager
def _tool_failing(tool_name: str):
    """Fuerza que UNA tool falle (Fase 5, persona `fallo_de_tool`). Reemplaza temporalmente el
    handler en el _DISPATCH del hotel para que lance: execute_tool ya lo envuelve en try/except y
    le devuelve al agente un 'Error ejecutando ...'. Así verificamos que el agente NO inventa ni
    queda mudo cuando una herramienta se cae. Vive SOLO en el harness de evals — no toca producción."""
    from app.services.hotel_tools_pkg import _DISPATCH

    def _boom(args, ctx):
        raise RuntimeError(f"[eval] fallo inyectado en {tool_name}")

    original = _DISPATCH.get(tool_name)
    _DISPATCH[tool_name] = _boom
    try:
        yield
    finally:
        if original is not None:
            _DISPATCH[tool_name] = original


async def _sim_dispatch(session_id: str, message: str, history: list):
    """Manda UN turno al agente real (guest) y devuelve (response, tool_trace). Reusa
    agent_service.chat, que encadena el historial por session_id automáticamente.

    Si la persona es `fallo_de_tool` (el session_id lo lleva en el prefijo sim-<persona>-...),
    inyecta un fallo en consultar_disponibilidad para probar la resiliencia del agente."""
    db = SessionLocal()
    inject_fail = "sim-fallo_de_tool-" in session_id
    try:
        if inject_fail:
            with _tool_failing("consultar_disponibilidad"):
                result = await agent_service.chat(db, message, session_id, "es")
        else:
            result = await agent_service.chat(db, message, session_id, "es")
        return result.get("response", ""), result.get("tool_trace", []) or []
    finally:
        db.close()


async def _run_simulations(personas_filter, flows_filter) -> int:
    """Corre las simulaciones (persona × flujo), evalúa cada transcript con el juez y reporta.
    Gate por (persona, flujo): 2 de 3 corridas verdes (estocástico). GASTA OpenAI."""
    from evals.simulator import PERSONAS, run_simulation
    from evals.judge import judge_transcript
    from app.services import business_profile_service

    personas = [PERSONAS[k] for k in (personas_filter or PERSONAS.keys()) if k in PERSONAS]
    flows = flows_filter or ["F2"]
    if not personas:
        print(f"No hay personas que coincidan con {personas_filter}. Disponibles: {list(PERSONAS)}")
        return 2

    # Facts del negocio activo (el juez los usa para detectar contradicciones).
    _db = SessionLocal()
    try:
        facts = business_profile_service.get_profile(_db).get("facts", []) or []
    finally:
        _db.close()

    print(f"Simulando {len(personas)} persona(s) × {len(flows)} flujo(s) contra el agente real…\n")
    t0 = time.time()
    session_ids, failed = [], []
    nat_conv_ok = 0            # conversaciones con las 5 señales de naturalidad en verde
    nat_signal_fails: dict = {}  # conteo de fallos por señal (para el reporte)
    nat_total = 0
    coh_conv_ok = 0           # conversaciones con las 5 señales de COHERENCIA en verde (Fase 5)
    coh_signal_fails: dict = {}
    for persona in personas:
        for flow in flows:
            transcript = await run_simulation(persona, flow, _sim_dispatch)
            session_ids.append(transcript.session_id)
            verdict = await judge_transcript(
                transcript.as_text(), transcript.tool_trace, facts,
                goal=persona.goal, satisfied_when=persona.satisfied_when)
            status = "PASS" if verdict.ok else "FAIL"
            nat_flag = "nat✓" if verdict.naturalidad_ok() else "nat✗"
            coh_flag = "coh✓" if verdict.coherencia_ok() else "coh✗"
            print(f"[{persona.key:15} {flow}] {status} {nat_flag} {coh_flag}  ·  {len(transcript.turns)} turnos  ·  "
                  f"goal={verdict.goal_achieved}  invenciones={len(verdict.invented_facts)}")
            if verdict.notes:
                print(f"    nota: {verdict.notes}")
            for inv in verdict.invented_facts:
                print(f"    ⚠ invención: {inv.get('claim','')}")
            # Naturalidad y coherencia: MÉTRICAS reportadas, no bloqueantes (no afectan `failed`).
            nat_total += 1
            if verdict.naturalidad_ok():
                nat_conv_ok += 1
            for sig, ok_ in verdict.naturalidad.items():
                if not ok_:
                    nat_signal_fails[sig] = nat_signal_fails.get(sig, 0) + 1
            if verdict.coherencia_ok():
                coh_conv_ok += 1
            for sig, ok_ in verdict.coherencia.items():
                if not ok_:
                    coh_signal_fails[sig] = coh_signal_fails.get(sig, 0) + 1
            if not verdict.ok:
                failed.append(f"{persona.key}/{flow}")

    print(f"\nTiempo total: {time.time()-t0:.1f}s")
    # Reporte de NATURALIDAD (Fase 3) y COHERENCIA (Fase 5): objetivo ≥80% de conversaciones OK.
    def _report(nombre, ok_count, fails):
        if not nat_total:
            return
        pct = 100 * ok_count / nat_total
        gate = "✓" if pct >= 80 else "✗ (objetivo ≥80%)"
        print(f"\n{nombre}: {ok_count}/{nat_total} conversaciones con las 5 señales OK "
              f"({pct:.0f}%) {gate}")
        if fails:
            print("  Fallos por señal: " + ", ".join(
                f"{k}={v}" for k, v in sorted(fails.items(), key=lambda kv: -kv[1])))
    _report("Naturalidad", nat_conv_ok, nat_signal_fails)
    _report("Coherencia", coh_conv_ok, coh_signal_fails)
    _cleanup(session_ids)  # limpia por session_id (reservas/tickets/leads creados)
    if failed:
        print(f"Simulaciones con veredicto FAIL: {', '.join(failed)}")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description="Evaluación end-to-end del agente Aura")
    ap.add_argument("--scenario", "-s", action="append",
                    help="ID(s) de escenario a correr (ej. -s S5 -s S6). Por defecto, todos.")
    ap.add_argument("--list", action="store_true", help="Lista los escenarios y sale.")
    ap.add_argument("--smoke", action="store_true",
                    help="Corre solo el subconjunto SMOKE (barato, para CI).")
    ap.add_argument("--tier", choices=["core", "instance"], default=None,
                    help="Filtra por tier: core (genéricos del vertical) o instance (del cliente).")
    # Modo simulador (Workstream T.2) — conversaciones humanas + LLM-as-judge. GASTA OpenAI.
    ap.add_argument("--sim", action="store_true",
                    help="Corre simulaciones de huésped (persona LLM + juez) en vez de escenarios fijos.")
    ap.add_argument("--persona", action="append",
                    help="Persona(s) del simulador (ej. --persona apurado). Default: todas.")
    ap.add_argument("--flow", action="append",
                    help="Flujo(s) objetivo del simulador (ej. --flow F2). Default: F2.")
    args = ap.parse_args()

    if args.list:
        for s in SCENARIOS:
            tier = s.get("tier", "core")
            smoke = " [smoke]" if s["id"] in _SMOKE_IDS else ""
            print(f"  {s['id']:4} [{tier:8}]{smoke} {s['name']}  ({len(s['turns'])} turnos)")
        return

    if args.sim:
        rc = asyncio.run(_run_simulations(args.persona, args.flow))
        sys.exit(rc)

    selected = set(args.scenario) if args.scenario else None
    rc = asyncio.run(_main_async(selected, smoke=args.smoke, tier=args.tier))
    sys.exit(rc)


if __name__ == "__main__":
    main()
