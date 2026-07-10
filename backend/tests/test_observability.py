"""
Fase 3.4 — dashboard de observabilidad (sin OpenAI).

Verifica la agregación del audit por agente + containment + errores, mockeando read_entries.
"""
from app.services import observability_service as obs


_FAKE_AUDIT = [
    {"ts": "2026-07-10T10:00:00", "agent_key": "hotel_presale", "tokens": 1000, "model": "gpt-4o", "error": False},
    {"ts": "2026-07-10T10:05:00", "agent_key": "hotel_presale", "tokens": 2000, "model": "gpt-4o", "error": False},
    {"ts": "2026-07-10T11:00:00", "agent_key": "hotel_postsale", "tokens": 500, "model": "gpt-4o",
     "error": True, "error_type": "guardrail"},
    {"ts": "2026-07-10T12:00:00", "agent_key": "hotel_postsale", "tokens": 800, "model": "gpt-4o",
     "error": False, "route": "escalacion"},
]


def test_summary_agrega_por_agente(monkeypatch):
    monkeypatch.setattr(obs, "read_entries", lambda limit=5000: list(_FAKE_AUDIT))
    s = obs.summary()
    assert s["total_turns"] == 4
    assert s["by_agent"]["hotel_presale"]["turns"] == 2
    assert s["by_agent"]["hotel_presale"]["tokens"] == 3000
    assert s["by_agent"]["hotel_postsale"]["errors"] == 1


def test_summary_containment_y_errores(monkeypatch):
    monkeypatch.setattr(obs, "read_entries", lambda limit=5000: list(_FAKE_AUDIT))
    s = obs.summary()
    # 4 turnos: 1 con error + 1 escalado → 2 contenidos → 0.5
    assert s["errors"] == 1
    assert s["escalated"] == 1
    assert s["guardrail_turns"] == 1
    assert s["containment_rate"] == 0.5
    assert s["errors_by_type"] == {"guardrail": 1}


def test_summary_costo_estimado(monkeypatch):
    monkeypatch.setattr(obs, "read_entries", lambda limit=5000: list(_FAKE_AUDIT))
    s = obs.summary()
    # el costo por agente debe ser > 0 con tokens y modelo conocidos
    assert s["by_agent"]["hotel_presale"]["cost_usd"] > 0


def test_summary_audit_vacio(monkeypatch):
    monkeypatch.setattr(obs, "read_entries", lambda limit=5000: [])
    s = obs.summary()
    assert s["total_turns"] == 0
    assert s["containment_rate"] is None
