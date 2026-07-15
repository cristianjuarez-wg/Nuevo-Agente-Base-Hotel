"""
Fase B — captura de contacto en la derivación DEFERRED (web anónimo).

Cuando NO hay atención humana y se deriva, el equipo necesita a quién llamar. El carril
automático de lead_service (extracción por regex + Contact + link a la conversación) debe
persistir el teléfono que el huésped escriba en el turno siguiente, y la bandeja debe
mostrarlo — sin tocar conversations.py (el phone sale del Contact vinculado).

Se mockean SOLO los sub-helpers que llaman al LLM (análisis de intención, nombre por IA,
fallback LLM de contacto): la extracción de teléfono es regex real y la persistencia
(Lead + Contact + link) es el código real bajo prueba.
"""
import asyncio

from app.models.conversation import Conversation
from app.models.lead import Lead
from app.models.contact import Contact
from app.services import human_attention_service as has
from app.services import conversation_control_service as ctrl
from app.services.hotel_tools_pkg.misc import _handle_derivar_a_humano
from app.services.lead_service import lead_service
from app.services.lead_analyzer import lead_analyzer


def _run(coro):
    # asyncio.run crea un loop fresco: robusto al orden de la suite (otro test puede haber
    # cerrado el loop por defecto del thread).
    return asyncio.run(coro)


def test_deferred_luego_datos_persisten_y_bandeja_muestra_phone(client, db, monkeypatch):
    has.update_config(db, {"enabled": False, "on_call": False})  # atención APAGADA
    sid = "web-defer-cap-1"
    db.add(Conversation(session_id=sid, channel="web"))
    db.commit()

    # 1) Pedido de humano → deferred deja rastro accionable.
    out = _handle_derivar_a_humano({"motivo": "quiere una persona"}, {"db": db, "session_id": sid})
    assert out["handoff"] == "deferred"
    assert ctrl.get_needs_human(db, sid)["status"] == "deferred"

    # 2) Turno siguiente: el huésped deja su teléfono → el carril automático lo persiste.
    async def _fake_intent(*_a, **_k):
        return {"lead_type": "TIBIO", "interest_score": 5, "contact_readiness": True,
                "obstacle": "ninguno", "suggested_response_tone": "cálido",
                "next_action": "solicitar_contacto", "reasoning": ""}
    monkeypatch.setattr(lead_analyzer, "analyze_lead_intent", _fake_intent)

    async def _no_name(*_a, **_k):
        return None
    monkeypatch.setattr(lead_service, "_extract_name_with_ai", _no_name)

    async def _no_llm_contact(*_a, **_k):
        return {}
    monkeypatch.setattr(lead_service, "_extract_contact_with_llm", _no_llm_contact)

    history = [
        {"role": "user", "content": "quiero hablar con una persona"},
        {"role": "assistant", "content": "No hay atención en vivo ahora. ¿Me dejás tu nombre y un teléfono?"},
    ]
    _run(lead_service.process_message_for_lead(
        db, "dale. mi teléfono es 1122334455", sid, history, "", {},
    ))

    lead = db.query(Lead).filter(Lead.session_id == sid).first()
    assert lead is not None and lead.phone, "el teléfono no se persistió en el Lead"
    assert lead.contact_id, "no se creó/vinculó el Contact desde el teléfono capturado"
    contact = db.query(Contact).filter(Contact.id == lead.contact_id).first()
    assert contact and contact.phone_number

    # 3) La bandeja muestra el phone (del Contact vinculado) y el estado deferred.
    r = client.get("/api/conversations?channel=all")
    assert r.status_code == 200
    item = next(c for c in r.json()["conversations"] if c["session_id"] == sid)
    assert item["phone"], "la bandeja no muestra el teléfono capturado"
    assert item["needs_human"] and item["needs_human"]["status"] == "deferred"
