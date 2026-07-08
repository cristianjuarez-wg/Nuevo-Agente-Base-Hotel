"""
Reproducción del Bug 2 (mensaje fantasma "eli nada que ver"): CARRERA por sesión.

Cada mensaje entrante de WhatsApp corre en su propio asyncio.create_task
(routers/whatsapp.py). Cuando el huésped manda dos mensajes seguidos, dos turnos corren
concurrentes sobre la misma sesión: sin serializar, cada uno lee el historial ANTES de
que el otro escriba su respuesta, así que ambos responden ciegos entre sí y se envían
dos respuestas, la segunda con contexto rancio (el mensaje descolgado de producción).

Este test verifica el FIX: el lock por session_id en agent_service.chat serializa los
turnos, de modo que el segundo espera al primero y ve su intercambio en el snapshot.

Determinista, sin OpenAI: mockeamos el LLM y el ruteo. DB en memoria (conftest).
"""
import asyncio

import pytest

from app.services.agent_service import agent_service


def _valid_history(history):
    """El historial sano alterna user→assistant y cada assistant responde al user previo.

    Devuelve (ok, motivo). Un entrelazado de dos turnos concurrentes rompe esto:
    aparecen dos 'user' seguidos, o un 'assistant' cuyo turno no sigue a su 'user'.
    """
    for i in range(0, len(history) - 1, 2):
        if history[i]["role"] != "user":
            return False, f"posición {i} debería ser 'user', es {history[i]['role']!r}"
        if history[i + 1]["role"] != "assistant":
            return False, f"posición {i+1} debería ser 'assistant', es {history[i+1]['role']!r}"
    return True, "ok"


@pytest.mark.asyncio
async def test_concurrent_whatsapp_turns_corrupt_history(db, monkeypatch):
    session_id = "wa_5493410000001"

    # Sesión arranca limpia en RAM.
    agent_service.conversation_history.pop(session_id, None)
    agent_service.session_metadata.pop(session_id, None)

    # Forzar la ruta casual para ambos turnos, sin gastar el triage real (LLM).
    from app.services import triage_sdk_orchestrator as triage_mod

    async def _fake_route(message, sid, history):
        return {"route": triage_mod.ROUTE_CASUAL, "usage": {"total_tokens": 0}}

    monkeypatch.setattr(triage_mod.triage_sdk_orchestrator, "route", _fake_route)

    # Generador casual mockeado: SLEEP en el medio para forzar el entrelazado del event
    # loop (así el turno B se cuela entre el read y el append del turno A). CLAVE: captura
    # el SNAPSHOT del historial que el turno VIO al construir su respuesta — así probamos
    # si un turno respondió sin ver el mensaje del otro (contexto rancio = síntoma real).
    seen_snapshots = {}

    async def _fake_casual(message, history, *args, **kwargs):
        # Copia defensiva del historial en el momento en que ESTE turno lo lee.
        snapshot = [dict(m) for m in history]
        await asyncio.sleep(0.05)  # cede el control → el otro turno avanza en paralelo
        seen_snapshots[message] = snapshot
        return f"respuesta-a::{message}", {"total_tokens": 1, "model": "mock"}

    monkeypatch.setattr(agent_service, "_generate_casual_response", _fake_casual)

    # Neutralizar side-effects que tocan DB/servicios no relevantes a la carrera.
    monkeypatch.setattr(agent_service, "_should_capture_lead_in_casual",
                        lambda *a, **k: _false_coro())
    monkeypatch.setattr(agent_service, "_build_casual_guest_block", lambda *a, **k: "")
    monkeypatch.setattr(agent_service, "_availability_shown_in_session", lambda *a, **k: False)
    monkeypatch.setattr(agent_service, "_preventa_channel_gate", lambda *a, **k: None)
    monkeypatch.setattr(agent_service, "_save_message_to_db", lambda *a, **k: None)
    monkeypatch.setattr(agent_service, "_is_pure_social", lambda *a, **k: False)
    monkeypatch.setattr(agent_service, "_contains_booking_code", lambda *a, **k: False)
    monkeypatch.setattr(agent_service, "_session_has_recent_booking", lambda *a, **k: False)

    # Dos mensajes del mismo huésped, casi simultáneos (como en la charla real).
    msg_a = "La conoces a Eli?"
    msg_b = "Quería reservar"

    # Disparar ambos turnos CONCURRENTES sobre la MISMA sesión (como los dos
    # asyncio.create_task del webhook).
    results = await asyncio.gather(
        agent_service.chat(db, msg_a, session_id, "es"),
        agent_service.chat(db, msg_b, session_id, "es"),
    )

    history = agent_service.conversation_history.get(session_id, [])

    # El síntoma REAL de la carrera: al menos uno de los dos turnos construyó su respuesta
    # SIN VER el mensaje del otro turno (contexto rancio). Serializados, el segundo turno
    # vería en su snapshot el intercambio del primero; concurrentes, no. Ese turno rancio
    # es el que en producción produjo el mensaje descolgado ("eli nada que ver").
    snap_a = seen_snapshots.get(msg_a, [])
    snap_b = seen_snapshots.get(msg_b, [])
    a_saw_b = any(m["content"] == msg_b for m in snap_a)
    b_saw_a = any(m["content"] == msg_a for m in snap_b)
    stale = not a_saw_b and not b_saw_a  # ninguno vio al otro → corrieron ciegos en paralelo

    # Uno de los dos turnos gana el lock y corre primero; el otro espera. El que corre
    # SEGUNDO debe ver en su snapshot el intercambio del primero (ya no corren ciegos).
    second_saw_first = a_saw_b or b_saw_a

    print("\n--- Snapshots vistos por cada turno ---")
    print(f"  Turno A ({msg_a!r}) vio {len(snap_a)} msgs; ¿vio a B? {a_saw_b}")
    print(f"  Turno B ({msg_b!r}) vio {len(snap_b)} msgs; ¿vio a A? {b_saw_a}")
    print("--- Historial final ---")
    for i, m in enumerate(history):
        print(f"  [{i}] {m['role']}: {m['content']}")
    print(f"--- ¿El 2º turno vio al 1º (serializado)? {second_saw_first} ---")

    # Con la serialización por sesión (lock en agent_service.chat), los turnos ya NO corren
    # ciegos: el segundo espera al primero y ve su intercambio. Esto es lo que evita el
    # mensaje descolgado en producción.
    assert not stale and second_saw_first, (
        "Se esperaba que el 2º turno viera el intercambio del 1º (serializado por el lock "
        "de sesión), pero corrieron ciegos entre sí. ¿Se quitó el lock de agent_service.chat?"
    )
    # El historial final igual debe quedar coherente (user→assistant en orden).
    ok, reason = _valid_history(history)
    assert ok, f"Historial incoherente tras serializar: {reason}"


async def _false_coro():
    return False
