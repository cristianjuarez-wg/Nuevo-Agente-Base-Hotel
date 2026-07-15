"""
Fase F (Centro) — canales por flujo: el flujo de pre-venta trabaja SOLO en sus
canales asignados. Canal no asignado → NO se atiende (decisión del usuario):
WhatsApp/Instagram en silencio; web con un aviso breve (el widget no puede
quedar colgado). Post-venta NUNCA pasa por el gate. Default (3 canales) = paridad.
"""
from app.services.agent_service import agent_service
from app.services.skill_service import (
    seed_skills, validate_and_clamp, invalidate_centro_cache, get_centro_config,
)
from app.services.agent_directory import seed_agents
from app.models.skill import Skill, AgentSkill
from app.models.agent import Agent


def _set_canales(db, canales):
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()
    inst = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == aura.id, AgentSkill.skill_id == flow.id)
        .first()
    )
    inst.policy_values = {**(inst.policy_values or {}), "canales": canales}
    db.commit()
    invalidate_centro_cache()


def test_multiselect_valida_subconjunto(db):
    seed_agents(db)
    seed_skills(db)
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()
    clean, notes = validate_and_clamp(flow, {"canales": ["whatsapp", "tiktok", "web", "web"]})
    assert clean["canales"] == ["whatsapp", "web"]     # inválido descartado + dedupe
    assert any("descartaron" in n for n in notes)


def test_default_todos_los_canales_paridad(db):
    """Sin tocar nada, el flujo trabaja en los 3 canales: el gate no corta (paridad)."""
    seed_agents(db)
    seed_skills(db)
    _set_canales(db, ["whatsapp", "web", "instagram"])
    for sid in ("wa_5493411111111", "ig_12345", "web-abc123"):
        assert agent_service._preventa_channel_gate(db, sid) is None


def test_canal_no_asignado_corta(db):
    seed_agents(db)
    seed_skills(db)
    _set_canales(db, ["whatsapp"])  # solo WhatsApp asignado

    # Instagram → silencio (respuesta vacía + flag para que el webhook no envíe).
    gate_ig = agent_service._preventa_channel_gate(db, "ig_12345")
    assert gate_ig is not None and gate_ig["channel_blocked"] is True
    assert gate_ig["response"] == ""

    # Web → aviso breve (el widget no puede quedar colgado).
    gate_web = agent_service._preventa_channel_gate(db, "web-abc123")
    assert gate_web is not None and gate_web["channel_blocked"] is True
    assert "no está atendiendo" in gate_web["response"]

    # WhatsApp asignado → se atiende normal.
    assert agent_service._preventa_channel_gate(db, "wa_5493411111111") is None

    # Restaurar para no ensuciar otros tests (la DB se comparte en la sesión).
    _set_canales(db, ["whatsapp", "web", "instagram"])


def test_lista_vacia_es_fail_open(db):
    """Una lista de canales VACÍA no debe bloquear a TODOS (config incompleta ≠ 'bloqueá todo').
    Fail-open: se atiende en cualquier canal."""
    seed_agents(db)
    seed_skills(db)
    _set_canales(db, [])  # lista vacía

    for sid in ("wa_5493411111111", "ig_12345", "web-abc123"):
        assert agent_service._preventa_channel_gate(db, sid) is None, \
            "lista vacía no debe dejar sin atención"

    _set_canales(db, ["whatsapp", "web", "instagram"])  # restaurar


def test_kill_switch_apaga_el_gate(db):
    """Con la capa del Centro apagada, el gate no corta nada (fail-open: se atiende)."""
    seed_agents(db)
    seed_skills(db)
    _set_canales(db, ["whatsapp"])
    config = get_centro_config(db)
    config.use_agent_config = False
    db.commit()
    invalidate_centro_cache()

    assert agent_service._preventa_channel_gate(db, "ig_12345") is None

    config.use_agent_config = True
    db.commit()
    invalidate_centro_cache()
    _set_canales(db, ["whatsapp", "web", "instagram"])
