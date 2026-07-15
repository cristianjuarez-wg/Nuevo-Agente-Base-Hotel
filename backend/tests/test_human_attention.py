"""
Fase 4a — atención humana: disponibilidad (horario/guardia), flag needs_human, bloque de handoff.
"""
from datetime import datetime

from app.services import human_attention_service as has
from app.services import conversation_control_service as ctrl
from app.domains.hotel.prompts.base_blocks import handoff_block


def test_disabled_nunca_disponible(db):
    has.update_config(db, {"enabled": False, "on_call": True})
    assert has.is_human_available(db) is False


def test_guardia_siempre_disponible(db):
    has.update_config(db, {"enabled": True, "on_call": True})
    assert has.is_human_available(db) is True


def test_dentro_de_franja_disponible(db):
    # Lunes 10:00, franja lun 09-18 activa → disponible.
    has.update_config(db, {"enabled": True, "on_call": False,
                           "schedule": {"0": {"active": True, "from": "09:00", "to": "18:00"}}})
    lunes_10 = datetime(2026, 7, 6, 10, 0)  # 2026-07-06 es lunes
    assert has.is_human_available(db, now=lunes_10) is True


def test_fuera_de_franja_no_disponible(db):
    has.update_config(db, {"enabled": True, "on_call": False,
                           "schedule": {"0": {"active": True, "from": "09:00", "to": "18:00"}}})
    lunes_20 = datetime(2026, 7, 6, 20, 0)  # 20:00, fuera de 09-18
    assert has.is_human_available(db, now=lunes_20) is False


def test_dia_inactivo_no_disponible(db):
    # Domingo cerrado.
    has.update_config(db, {"enabled": True, "on_call": False,
                           "schedule": {"6": {"active": False, "from": "09:00", "to": "18:00"}}})
    domingo = datetime(2026, 7, 12, 12, 0)  # 2026-07-12 es domingo
    assert has.is_human_available(db, now=domingo) is False


def test_flag_needs_human_marca_y_limpia(db):
    from app.models.conversation import Conversation
    conv = Conversation(session_id="wa_needs1", channel="whatsapp")
    db.add(conv); db.commit()
    assert ctrl.flag_needs_human(db, "wa_needs1", motivo="quiere cancelar", summary="pide humano") is True
    state = ctrl.get_needs_human(db, "wa_needs1")
    assert state and state["active"] and state["motivo"] == "quiere cancelar"
    assert state["summary"] == "pide humano"
    ctrl.clear_needs_human(db, "wa_needs1")
    assert ctrl.get_needs_human(db, "wa_needs1") is None


def test_takeover_limpia_needs_human(db):
    """Al tomar el control, la marca needs_human se limpia (ya la atendió una persona)."""
    from app.models.conversation import Conversation
    conv = Conversation(session_id="wa_needs2", channel="whatsapp")
    db.add(conv); db.commit()
    ctrl.flag_needs_human(db, "wa_needs2", motivo="x")
    ctrl.take_over(db, "wa_needs2", staff_id=None, staff_name="Ana")
    assert ctrl.get_needs_human(db, "wa_needs2") is None  # limpiada por el takeover


def test_flag_needs_human_status_default_y_explicito(db):
    """El status distingue live/deferred. Default 'live' (retrocompatible)."""
    from app.models.conversation import Conversation
    db.add(Conversation(session_id="wa_st1", channel="whatsapp"))
    db.add(Conversation(session_id="wa_st2", channel="whatsapp"))
    db.commit()
    # Sin status → "live".
    ctrl.flag_needs_human(db, "wa_st1", motivo="x")
    assert ctrl.get_needs_human(db, "wa_st1")["status"] == "live"
    # Explícito "deferred".
    ctrl.flag_needs_human(db, "wa_st2", motivo="x", status="deferred")
    assert ctrl.get_needs_human(db, "wa_st2")["status"] == "deferred"


def test_derivar_a_humano_apagada_deja_rastro_deferred(db):
    """Con atención APAGADA, derivar_a_humano igual marca la conversación (status='deferred')
    para que quede accionable en la bandeja — antes NO dejaba rastro y el pedido se perdía."""
    from app.models.conversation import Conversation
    from app.services.hotel_tools_pkg.misc import _handle_derivar_a_humano
    has.update_config(db, {"enabled": False, "on_call": False})  # apagada
    db.add(Conversation(session_id="wa_defer1", channel="whatsapp"))
    db.commit()
    out = _handle_derivar_a_humano({"motivo": "quiere hablar con alguien"},
                                   {"db": db, "session_id": "wa_defer1"})
    assert out["handoff"] == "deferred"
    state = ctrl.get_needs_human(db, "wa_defer1")
    assert state and state["active"] and state["status"] == "deferred"


def test_derivar_a_humano_disponible_marca_live(db):
    """Con atención DISPONIBLE (guardia), derivar_a_humano marca status='live'."""
    from app.models.conversation import Conversation
    from app.services.hotel_tools_pkg.misc import _handle_derivar_a_humano
    has.update_config(db, {"enabled": True, "on_call": True})  # disponible ya
    db.add(Conversation(session_id="wa_live1", channel="whatsapp"))
    db.commit()
    out = _handle_derivar_a_humano({"motivo": "necesita ayuda"},
                                   {"db": db, "session_id": "wa_live1"})
    assert out["handoff"] == "live"
    state = ctrl.get_needs_human(db, "wa_live1")
    assert state and state["status"] == "live"


def test_handoff_block_cambia_por_disponibilidad():
    disp = handoff_block(True)
    no = handoff_block(False)
    assert "disponible ahora" in disp
    assert "NO hay una persona" in no
    assert disp != no


def test_endpoint_get(client, db):
    r = client.get("/api/human-attention")
    assert r.status_code == 200
    body = r.json()
    assert "config" in body and "available_now" in body
    assert "schedule" in body["config"]
