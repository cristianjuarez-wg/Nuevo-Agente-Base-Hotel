"""
Fase E1 (Centro) — entrenamiento estructurado: schemas, fábrica, validación y endpoints.

Reglas verificadas:
- El data del cliente se sanea server-side (tipos, largos, cantidades, selects).
- El render produce bloques acotados (tope de largo) desde los campos.
- Fábrica: espejo (tono/política/objeciones) nace ACTIVA; adicionales DESACTIVADAS.
- No-clobber: un doc de fábrica editado por el cliente sobrevive re-seeds.
- Los default no se borran; se restauran a fábrica.
"""
from app.services import training_service as ts
from app.services.training_service import (
    validate_training_data, render_training, seed_training_defaults,
    get_training_blocks, FORM_SCHEMAS, FACTORY, CATEGORY_ORDER,
)
from app.services.agent_directory import seed_agents
from app.services.skill_service import invalidate_centro_cache
from app.models.training_document import TrainingDocument
from app.models.agent import Agent
from app.prompts.tool_agent_prompts import DEFAULT_TONO_BLOCK, DEFAULT_POLITICA_BLOCK


# ---------------------------------------------------------------------------
# 1. Validación (sanitización server-side)
# ---------------------------------------------------------------------------

def test_validate_capea_largos_y_cantidades():
    data, notes = validate_training_data("objeciones", {
        "items": [{"objecion": "x" * 999, "respuesta": "ok"} for _ in range(20)],
    })
    assert len(data["items"]) == ts._MAX_ITEMS            # filas capeadas
    assert len(data["items"][0]["objecion"]) <= ts._MAX_STR  # strings capeados
    assert any("primeras" in n for n in notes)


def test_validate_select_y_claves_extranas():
    data, notes = validate_training_data("tono_marca", {
        "trato": "che",                 # opción inválida → se ignora con nota
        "emojis": 1,                    # se coerciona a bool
        "palabras_preferidas": ["dale", "", "  bárbaro  "],
        "clave_inventada": "hack",      # no declarada → se descarta
        "notas": "línea1\nlínea2",     # saltos encajonados
    })
    assert "trato" not in data and any("inválida" in n for n in notes)
    assert data["emojis"] is True
    assert data["palabras_preferidas"] == ["dale", "bárbaro"]
    assert "clave_inventada" not in data
    assert "\n" not in data["notas"]


def test_validate_categoria_invalida():
    import pytest
    with pytest.raises(ValueError):
        validate_training_data("categoria_falsa", {})


# ---------------------------------------------------------------------------
# 2. Render (plantilla fija nuestra, acotada)
# ---------------------------------------------------------------------------

def test_render_todas_las_categorias_de_fabrica():
    for category in CATEGORY_ORDER:
        text = render_training(category, FACTORY[category]["data"])
        assert text, f"render vacío para {category}"
        assert len(text) <= ts._MAX_RENDER


def test_render_capea_el_total():
    data = {"items": [{"objecion": "o" * 300, "respuesta": "r" * 300} for _ in range(10)]}
    clean, _ = validate_training_data("objeciones", data)
    assert len(render_training("objeciones", clean)) <= ts._MAX_RENDER


# ---------------------------------------------------------------------------
# 3. Fábrica: espejo activas / adicionales desactivadas + no-clobber
# ---------------------------------------------------------------------------

def test_seed_espejo_activas_adicionales_inactivas(db):
    seed_agents(db)
    seed_training_defaults(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    docs = {
        d.category: d for d in
        db.query(TrainingDocument).filter(
            TrainingDocument.agent_id == aura.id,
            TrainingDocument.is_default == True,  # noqa: E712
        ).all()
    }
    assert set(docs) == set(CATEGORY_ORDER)  # las 6 sembradas
    # Espejo → activas (paridad); adicionales → desactivadas (el cliente revisa y activa).
    assert docs["tono_marca"].active and docs["politica_comercial"].active and docs["objeciones"].active
    assert not docs["argumentario"].active
    assert not docs["calificacion_leads"].active
    assert not docs["ejemplos"].active


def test_seed_no_clobber(db):
    seed_agents(db)
    seed_training_defaults(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.agent_id == aura.id, TrainingDocument.category == "tono_marca")
        .first()
    )
    doc.data = {**doc.data, "notas": "editado por el cliente"}
    db.commit()
    seed_training_defaults(db)   # redeploy simulado
    db.refresh(doc)
    assert doc.data["notas"] == "editado por el cliente"


# ---------------------------------------------------------------------------
# 4. Endpoints: reglas de default, restore y formularios
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 5. Inyección con sustitución (Fase E2): paridad, sustitución y aditivas
# ---------------------------------------------------------------------------

def _reset_training(db, aura_id):
    """Deja el entrenamiento del agente en estado de fábrica puro (los tests comparten DB)."""
    db.query(TrainingDocument).filter(TrainingDocument.agent_id == aura_id).delete()
    db.commit()
    seed_training_defaults(db)


def test_e2_paridad_estado_fabrica(db):
    """Con SOLO las plantillas de fábrica (sin ediciones), los bloques son los del código
    byte a byte y no se inyecta nada aditivo — el prompt queda idéntico al histórico."""
    seed_agents(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    _reset_training(db, aura.id)
    invalidate_centro_cache()

    blocks = get_training_blocks(db, aura.id)
    assert blocks["tono_block"] == DEFAULT_TONO_BLOCK
    assert blocks["politica_block"] == DEFAULT_POLITICA_BLOCK
    assert blocks["training_block"] == ""


def test_e2_sustitucion_tono_del_cliente(db):
    """El cliente edita SU tono (activo) → el bloque es el SUYO y NO el del código."""
    seed_agents(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    _reset_training(db, aura.id)
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.agent_id == aura.id, TrainingDocument.category == "tono_marca")
        .first()
    )
    doc.data = {**doc.data, "trato": "usted", "notas": "Formalidad británica."}
    db.commit()
    invalidate_centro_cache()

    blocks = get_training_blocks(db, aura.id)
    assert blocks["tono_block"] != DEFAULT_TONO_BLOCK
    assert "TONO DE MARCA" in blocks["tono_block"] and "usted" in blocks["tono_block"]
    assert "QUIÉN SOS" not in blocks["tono_block"]  # un solo tono, sin competencia


def test_e2_aditiva_activada_se_inyecta(db):
    """Activar una aditiva (decisión explícita) la inyecta aunque conserve el contenido
    sugerido; la objeciones de fábrica SIN editar no se inyecta (ya está en el cerebro)."""
    seed_agents(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    _reset_training(db, aura.id)
    arg = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.agent_id == aura.id, TrainingDocument.category == "argumentario")
        .first()
    )
    arg.active = True
    db.commit()
    invalidate_centro_cache()

    blocks = get_training_blocks(db, aura.id)
    assert "QUÉ DESTACAR" in blocks["training_block"]           # aditiva activada
    assert "INAMOVIBLES" in blocks["training_block"]            # preámbulo de jerarquía
    assert "MANEJO DE OBJECIONES" not in blocks["training_block"]  # espejo sin editar, fuera


def test_e2_kill_switch_apaga_entrenamiento(db):
    from app.services.skill_service import get_centro_config
    seed_agents(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    _reset_training(db, aura.id)
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.agent_id == aura.id, TrainingDocument.category == "tono_marca")
        .first()
    )
    doc.data = {**doc.data, "notas": "editado"}
    db.commit()

    config = get_centro_config(db)
    config.use_agent_config = False
    db.commit()
    invalidate_centro_cache()
    blocks = get_training_blocks(db, aura.id)
    assert blocks["tono_block"] == DEFAULT_TONO_BLOCK   # capa apagada → defaults

    config.use_agent_config = True
    db.commit()
    invalidate_centro_cache()
    assert get_training_blocks(db, aura.id)["tono_block"] != DEFAULT_TONO_BLOCK


def test_e2_prompt_ensambla_con_defaults(db):
    """El prompt armado con defaults contiene el carácter histórico intacto."""
    from app.services.hotel_sdk_orchestrator import hotel_sdk_orchestrator
    text = hotel_sdk_orchestrator._build_instructions("", "es")
    assert "QUIÉN SOS (tu carácter" in text
    assert "herramienta de cierre" in text          # política default en la regla 8
    assert "TONO DE MARCA" not in text              # nada del cliente


def test_endpoints_default_restore_y_schemas(db, client):
    seed_agents(db)
    seed_training_defaults(db)
    aura = db.query(Agent).filter(Agent.role == "guest").first()
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.agent_id == aura.id, TrainingDocument.category == "argumentario")
        .first()
    )

    # Los formularios se sirven al frontend (única fuente de verdad).
    r = client.get("/api/agents/training-schemas")
    assert r.status_code == 200 and r.json()["order"] == CATEGORY_ORDER

    # Un default NO se borra…
    r = client.delete(f"/api/agents/{aura.id}/training/{doc.id}")
    assert r.status_code == 400 and "no se eliminan" in r.json()["detail"]

    # …pero se edita (activar la adicional, cambiar campos)…
    r = client.put(f"/api/agents/{aura.id}/training/{doc.id}",
                   json={"active": True, "data": {"items": [{"tipo_huesped": "Esquiador", "puntos": ["Guardaesquís"]}]}})
    assert r.status_code == 200 and r.json()["active"] is True
    assert r.json()["data"]["items"][0]["tipo_huesped"] == "Esquiador"

    # …y se restaura a fábrica (contenido Y estado).
    r = client.post(f"/api/agents/{aura.id}/training/{doc.id}/restore")
    assert r.status_code == 200
    assert r.json()["active"] is False                      # la adicional vuelve a inactiva
    assert r.json()["data"] == FACTORY["argumentario"]["data"]

    # Crear entrada nueva del cliente: categoría inválida → 400; válida → creada y borrable.
    r = client.post(f"/api/agents/{aura.id}/training/entry",
                    json={"category": "inventada", "data": {}})
    assert r.status_code == 400
    r = client.post(f"/api/agents/{aura.id}/training/entry",
                    json={"category": "objeciones", "data": {"items": [{"objecion": "no hay estacionamiento", "respuesta": "ofrecé el garaje aliado"}]}})
    assert r.status_code == 200 and r.json()["is_default"] is False
    new_id = r.json()["id"]
    r = client.delete(f"/api/agents/{aura.id}/training/{new_id}")
    assert r.status_code == 200
