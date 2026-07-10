"""
F0.2 — endpoint de capacidades legibles del agente.

Verifica que GET /api/agents/{id}/capabilities devuelve grupos legibles (no tool keys crudas)
para los 3 roles, que TODAS las tools quedan cubiertas (sin "Otras capacidades"), y que la
deduplicación presale/postsale funciona (Aura no muestra "ver_carta" dos veces).
"""
from app.models.agent import Agent
from app.domains.hotel.agent_capabilities import (
    capability_groups_for_role, _tool_names_for_role, _CAPABILITY_GROUPS,
)


def _seed_agent(db, role, name):
    a = db.query(Agent).filter(Agent.role == role).first()
    if a is None:
        a = Agent(name=name, role=role, status="active", channels=["whatsapp"])
        db.add(a); db.commit(); db.refresh(a)
    return a


def test_capabilities_shape_por_rol(client, db):
    for role, name in (("guest", "Aura"), ("management", "Asesor"), ("staff", "Operaciones")):
        agent = _seed_agent(db, role, name)
        r = client.get(f"/api/agents/{agent.id}/capabilities")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == role
        assert "engine" in body and body["engine"] in ("sdk", "completions")
        groups = body["capability_groups"]
        assert isinstance(groups, list) and len(groups) >= 1
        # Cada grupo es legible: tiene nombre + resumen, y NO expone keys crudas.
        for g in groups:
            assert g["group"] and g["summary"]
            assert "." not in g["group"]        # no es una tool key con prefijo
            assert "_" not in g["group"]         # los grupos son texto humano, no snake_case


def test_todas_las_tools_caen_en_un_grupo_curado(db):
    """Ninguna tool debe quedar en 'Otras capacidades' — eso delataría un grupo sin curar."""
    for role in ("guest", "management", "staff"):
        have = _tool_names_for_role(role)
        covered = set()
        for g in _CAPABILITY_GROUPS.get(role, []):
            covered |= (g["keys"] & have)
        assert have - covered == set(), f"tools sin grupo en {role}: {sorted(have - covered)}"


def test_aura_deduplica_presale_postsale(db):
    """ver_carta/reservar_mesa aparecen en presale Y postsale; para el usuario es UNA capacidad."""
    have = _tool_names_for_role("guest")
    # Son 23 nombres únicos aunque las specs sumen 28 keys con prefijo.
    assert "ver_carta" in have
    groups = capability_groups_for_role("guest")
    names = [g["group"] for g in groups]
    # "Restaurante" aparece una sola vez pese a que ver_carta viene de dos specs.
    assert names.count("Restaurante") == 1


def test_agente_inexistente_404(client):
    r = client.get("/api/agents/999999/capabilities")
    assert r.status_code == 404
