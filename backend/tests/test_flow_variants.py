"""
Fase B (Centro) — variantes del flujo de venta: plantillas, selección y coherencia.

Reglas verificadas:
- "estandar" = bloque VACÍO (paridad exacta con el comportamiento actual).
- La variante elegida inyecta su plantilla; una variante desconocida cae a estándar.
- "sin_presion" suprime la captura proactiva SALVO pedido expreso del huésped.
- El seed REFRESCA la plantilla (gana parámetros nuevos) sin pisar la instancia del cliente.
- El select solo acepta opciones declaradas; inválida → default de fábrica.
"""
from app.prompts.flow_blocks import FLOW_BLOCKS, flow_block_for
from app.services.hotel_sdk_orchestrator import HotelSDKOrchestrator
from app.services.skill_service import (
    seed_skills, get_flow_values, validate_and_clamp, invalidate_centro_cache,
    list_agent_skills,
)
from app.services.agent_directory import seed_agents
from app.models.skill import Skill, AgentSkill
from app.models.agent import Agent


# ---------------------------------------------------------------------------
# 1. Plantillas
# ---------------------------------------------------------------------------

def test_estandar_es_vacio_paridad():
    assert FLOW_BLOCKS["estandar"] == ""
    assert flow_block_for("estandar") == ""
    assert flow_block_for(None) == ""
    assert flow_block_for("variante_inexistente") == ""  # desconocida → estándar (fail-open)


def test_variantes_tienen_su_plantilla():
    assert "CAPTACIÓN PROACTIVA" in flow_block_for("proactiva")
    assert "calcular_precio_promo" in flow_block_for("proactiva")
    assert "SIN PRESIÓN" in flow_block_for("sin_presion")
    assert "NO pidas datos de contacto" in flow_block_for("sin_presion")
    # Ambas declaran que NO reemplazan las reglas de seguridad (jerarquía §10.2).
    for v in ("proactiva", "sin_presion"):
        assert "NO reemplaza tus reglas de seguridad" in flow_block_for(v)


# ---------------------------------------------------------------------------
# 2. Coherencia de "sin_presion": supresión de captura proactiva
# ---------------------------------------------------------------------------

def test_sin_presion_suprime_captura_proactiva():
    allows = HotelSDKOrchestrator._variant_allows_capture
    # Estándar / proactiva / sin config → la captura sigue como siempre (paridad).
    assert allows(None, {"contact_readiness": False}) is True
    assert allows("estandar", {"contact_readiness": False}) is True
    assert allows("proactiva", {"contact_readiness": False}) is True
    # Sin presión → suprimida…
    assert allows("sin_presion", {"contact_readiness": False}) is False
    assert allows("sin_presion", {}) is False
    # …salvo pedido EXPRESO del huésped (eso es servicio, no presión).
    assert allows("sin_presion", {"contact_readiness": True}) is True


# ---------------------------------------------------------------------------
# 3. Seed: refresh de plantilla sin pisar la instancia del cliente
# ---------------------------------------------------------------------------

def test_refresh_de_plantilla_no_pisa_instancia(db):
    seed_agents(db)
    seed_skills(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()

    # La plantilla ya trae el parámetro `variante` con sus 3 opciones descriptas.
    variante = next(p for p in flow.parameter_schema if p["key"] == "variante")
    assert {o["value"] for o in variante["options"]} == {"estandar", "proactiva", "sin_presion"}
    assert all(o.get("description") for o in variante["options"])  # lenguaje natural presente

    # El cliente edita su instancia…
    inst = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == aura.id, AgentSkill.skill_id == flow.id)
        .first()
    )
    inst.policy_values = {**inst.policy_values, "variante": "proactiva", "score_caliente": 8}
    db.commit()

    # …se simula una plantilla VIEJA (sin `variante`) y un redeploy (re-seed):
    flow.parameter_schema = [p for p in flow.parameter_schema if p["key"] != "variante"]
    db.commit()
    seed_skills(db)
    db.refresh(flow)
    db.refresh(inst)

    # La plantilla se refrescó (recuperó `variante`)…
    assert any(p["key"] == "variante" for p in flow.parameter_schema)
    # …y la instancia del cliente quedó intacta.
    assert inst.policy_values["variante"] == "proactiva"
    assert inst.policy_values["score_caliente"] == 8

    # El merge efectivo respeta la elección del cliente.
    invalidate_centro_cache()
    values = get_flow_values(db, aura.id, "flujo_preventa")
    assert values["variante"] == "proactiva"


def test_instancia_sin_variante_cae_a_estandar(db):
    """Una instancia SIN elección de variante (cliente que nunca la tocó) usa la
    estándar vía el merge de defaults. Se limpia explícitamente porque los datos
    persisten entre tests de la misma sesión."""
    seed_agents(db)
    seed_skills(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()
    inst = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == aura.id, AgentSkill.skill_id == flow.id)
        .first()
    )
    inst.policy_values = {k: v for k, v in (inst.policy_values or {}).items() if k != "variante"}
    db.commit()

    invalidate_centro_cache()
    values = get_flow_values(db, aura.id, "flujo_preventa")
    assert values["variante"] == "estandar"  # default de fábrica = paridad


# ---------------------------------------------------------------------------
# 4. Select: solo opciones declaradas
# ---------------------------------------------------------------------------

def test_cada_agente_ve_solo_sus_flujos(db):
    """Los flujos se listan solo si están ASIGNADOS al agente (instancia existente);
    las functions sí son catálogo completo. Aura NO debe ver flujo_operaciones."""
    seed_agents(db)
    seed_skills(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    ops = db.query(Agent).filter(Agent.role == "staff").first()
    asesor = db.query(Agent).filter(Agent.role == "management").first()

    aura_flows = {r["skill"]["key"] for r in list_agent_skills(db, aura.id, kind="flow")}
    assert aura_flows == {"flujo_preventa", "flujo_postventa"}
    ops_flows = {r["skill"]["key"] for r in list_agent_skills(db, ops.id, kind="flow")}
    assert ops_flows == {"flujo_operaciones"}
    assert list_agent_skills(db, asesor.id, kind="flow") == []  # sin flujos → empty state


def test_select_rechaza_opcion_invalida(db):
    seed_agents(db)
    seed_skills(db)
    flow = db.query(Skill).filter(Skill.key == "flujo_preventa").first()

    clean, notes = validate_and_clamp(flow, {"variante": "proactiva"})
    assert clean["variante"] == "proactiva" and notes == []

    clean, notes = validate_and_clamp(flow, {"variante": "turbo_ventas"})
    assert "variante" not in clean          # inválida → no se guarda…
    assert any("inválida" in n for n in notes)
    # …y el merge efectivo cae al default de fábrica.
    assert {**{"variante": "estandar"}, **clean}["variante"] == "estandar"
