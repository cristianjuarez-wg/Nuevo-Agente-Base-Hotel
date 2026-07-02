"""
Fase A (Centro de Empleados Digitales) — tests de PARIDAD y de los 5 tratamientos.

La regla de la fase: con valores de fábrica (criteria=None / mapa de tools vacío /
kill switch en su estado), el comportamiento debe ser EXACTAMENTE el histórico.
Estos tests son deterministas (no llaman al LLM): prueban la lógica de decisión.
"""
import pytest

from app.services.lead_analyzer import lead_analyzer
from app.services import skill_service
from app.services.skill_service import (
    filter_tools, defaults_from_schema, seed_skills, get_flow_values,
    invalidate_centro_cache,
)
from app.services.agent_directory import seed_agents
from app.models.skill import Skill, AgentSkill
from app.models.agent import Agent


# ---------------------------------------------------------------------------
# 1. PARIDAD de should_request_contact (criteria=None == comportamiento histórico)
# ---------------------------------------------------------------------------

def _analysis(lead_type="FRIO", score=0, readiness=False, obstacle=None, next_action=None):
    return {
        "lead_type": lead_type,
        "interest_score": score,
        "contact_readiness": readiness,
        "obstacle": obstacle,
        "next_action": next_action,
    }


PARITY_MATRIX = [
    # (analysis, conv_len, message, expected) — valores históricos exactos
    (_analysis("CALIENTE", 9, readiness=True), 1, "", False),   # nunca en el 1er mensaje
    (_analysis(readiness=True), 2, "", True),                    # pidió ser contactado
    (_analysis("CALIENTE", 7), 2, "", True),                     # caliente en el umbral
    (_analysis("CALIENTE", 6), 2, "", False),                    # caliente bajo el umbral
    (_analysis("TIBIO", 6), 4, "", True),                        # tibio en umbrales
    (_analysis("TIBIO", 6), 3, "", False),                       # tibio con pocos mensajes
    (_analysis("TIBIO", 5), 4, "", False),                       # tibio bajo score
    (_analysis("FRIO", 3), 3, "muy caro", True),                 # cierre por precio con interés
    (_analysis("FRIO", 3, obstacle="precio"), 3, "", True),      # cierre semántico del LLM
    (_analysis("FRIO", 2), 3, "muy caro", False),                # sin interés real (turno+piso fríos)
]


@pytest.mark.parametrize("analysis,length,message,expected", PARITY_MATRIX)
def test_parity_should_request_contact(analysis, length, message, expected):
    """Sin criteria (None) el resultado es el histórico, caso por caso."""
    assert lead_analyzer.should_request_contact(analysis, length, message) is expected


def test_defaults_son_los_historicos():
    """Los defaults del analizador son exactamente los valores que estaban hardcodeados."""
    assert lead_analyzer.CONTACT_CRITERIA_DEFAULTS == {
        "min_msgs": 2, "score_caliente": 7, "score_tibio": 6, "msgs_tibio": 4,
    }


def test_criteria_cambia_el_comportamiento():
    """Las perillas del flujo efectivamente mueven la decisión (no son decorativas)."""
    hot7 = _analysis("CALIENTE", 7)
    # Subir el umbral a 9 → un caliente de 7 ya no dispara la captura.
    assert lead_analyzer.should_request_contact(hot7, 2, "", criteria={"score_caliente": 9}) is False
    # min_msgs=3 corta ANTES que cualquier otra señal (incluso readiness).
    ready = _analysis(readiness=True)
    assert lead_analyzer.should_request_contact(ready, 2, "", criteria={"min_msgs": 3}) is False
    assert lead_analyzer.should_request_contact(ready, 3, "", criteria={"min_msgs": 3}) is True


# ---------------------------------------------------------------------------
# 2. Filtrado de tools (tratamiento 1: tool no mapeada = siempre activa)
# ---------------------------------------------------------------------------

class _FakeTool:
    def __init__(self, name):
        self.name = name


def test_filter_tools_mapa_vacio_paridad():
    tools = [_FakeTool("a"), _FakeTool("b")]
    assert filter_tools(tools, set(), tool_map={}) == tools


def test_filter_tools_gobernadas():
    tools = [_FakeTool("libre"), _FakeTool("gobernada")]
    tmap = {"mi_skill": ["gobernada"]}
    # Skill deshabilitada → la tool gobernada desaparece; la libre queda.
    out = filter_tools(tools, set(), tool_map=tmap)
    assert [t.name for t in out] == ["libre"]
    # Skill habilitada → las dos quedan.
    out = filter_tools(tools, {"mi_skill"}, tool_map=tmap)
    assert [t.name for t in out] == ["libre", "gobernada"]


# ---------------------------------------------------------------------------
# 3. Seed de flujos: defaults del schema, instancias habilitadas, no-clobber
# ---------------------------------------------------------------------------

def test_seed_flujos_paridad_y_no_clobber(db):
    seed_agents(db)
    seed_skills(db)

    aura = db.query(Agent).filter(Agent.role == "guest").first()
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()
    assert flow is not None and flow.kind == "flow"

    # Los defaults del flujo de pre-venta son los históricos (paridad).
    assert defaults_from_schema(flow) == {
        "min_msgs": 2, "score_caliente": 7, "score_tibio": 6, "msgs_tibio": 4,
    }

    inst = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == aura.id, AgentSkill.skill_id == flow.id)
        .first()
    )
    assert inst is not None and inst.enabled is True
    assert inst.policy_values["score_caliente"] == 7

    # No-clobber: una edición del cliente sobrevive a un re-seed (redeploy).
    inst.policy_values = {**inst.policy_values, "score_caliente": 9}
    db.commit()
    seed_skills(db)
    db.refresh(inst)
    assert inst.policy_values["score_caliente"] == 9

    # get_flow_values devuelve la config mergeada (kill switch nace encendido).
    invalidate_centro_cache()
    values = get_flow_values(db, aura.id, "flujo_preventa")
    assert values is not None and values["score_caliente"] == 9 and values["min_msgs"] == 2


def test_kill_switch_apaga_la_capa(db):
    seed_agents(db)
    seed_skills(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()

    config = skill_service.get_centro_config(db)
    assert config.use_agent_config is True  # nace encendido de fábrica

    config.use_agent_config = False
    db.commit()
    invalidate_centro_cache()
    assert get_flow_values(db, aura.id, "flujo_preventa") is None  # capa ignorada → defaults

    config.use_agent_config = True
    db.commit()
    invalidate_centro_cache()
    assert get_flow_values(db, aura.id, "flujo_preventa") is not None


# ---------------------------------------------------------------------------
# 4. Los flujos no son toggles (tratamiento 4)
# ---------------------------------------------------------------------------

def test_flujo_no_se_apaga_por_endpoint(db, client):
    seed_agents(db)
    seed_skills(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()

    r = client.put(f"/api/agents/{aura.id}/skills/{flow.id}", json={"enabled": False})
    assert r.status_code == 400
    assert "no se apagan" in r.json()["detail"]

    # Sus policy_values SÍ se editan (eso ES configurar el flujo) y respetan el techo.
    r2 = client.put(
        f"/api/agents/{aura.id}/skills/{flow.id}",
        json={"policy_values": {"score_caliente": 99}},  # techo: 9
    )
    assert r2.status_code == 200
    assert r2.json()["policy_values"]["score_caliente"] == 9


def test_skills_tab_no_lista_flujos(db):
    seed_agents(db)
    seed_skills(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    kinds = {row["skill"]["kind"] for row in skill_service.list_agent_skills(db, aura.id)}
    assert kinds <= {"function"}  # ningún flow en la pestaña Skills
