"""
Fase 3.3 — versionado de la configuración de prompts (sin OpenAI).

Verifica el ciclo de vida: guardar snapshot → listar → activar (a lo sumo una activa) →
restaurar una versión previa.
"""
import pytest

from app.services import prompt_config_version_service as svc
from app.models.prompt_config_version import PromptConfigVersion
from app.models.training_document import TrainingDocument


def test_save_crea_version_activa(db):
    v = svc.save_version(db, author="admin@h.com", label="v1")
    assert v["id"] is not None
    assert v["active"] is True
    assert v["author"] == "admin@h.com"
    assert "training" in v["payload"] and "facts" in v["payload"]


def test_a_lo_sumo_una_activa(db):
    svc.save_version(db, label="v1")
    svc.save_version(db, label="v2")
    activas = db.query(PromptConfigVersion).filter(PromptConfigVersion.active == True).count()  # noqa: E712
    assert activas == 1
    # la activa es la última guardada
    active = svc.get_active(db)
    assert active["label"] == "v2"


def test_list_ordena_mas_nueva_primero(db):
    svc.save_version(db, label="vieja")
    svc.save_version(db, label="nueva")
    versions = svc.list_versions(db)
    assert versions[0]["label"] == "nueva"


def test_restore_reactiva_version_previa(db):
    v1 = svc.save_version(db, label="v1")
    svc.save_version(db, label="v2")
    assert svc.get_active(db)["label"] == "v2"
    # rollback a v1
    svc.restore_version(db, v1["id"])
    assert svc.get_active(db)["label"] == "v1"


def test_restore_version_inexistente(db):
    with pytest.raises(ValueError):
        svc.restore_version(db, 99999)


def test_snapshot_captura_training_activo(db):
    # Un training doc activo del cliente debe entrar al snapshot.
    db.add(TrainingDocument(agent_id=1, title="tono propio", category="tono_marca",
                            data={"trato": "usted"}, active=True, is_default=False))
    db.commit()
    v = svc.save_version(db, label="con-training")
    cats = [t["category"] for t in v["payload"]["training"]]
    assert "tono_marca" in cats
