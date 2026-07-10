"""
Fase 1.3 — timezone parametrizado desde el BusinessProfile.

now_business()/iso_business() usan la zona del perfil; now_argentina()/iso_argentina()
quedan como alias delegantes (paridad). Deterministas, sin LLM.
"""
from datetime import datetime

import app.utils.timezone_utils as tz


def test_alias_delegan_en_business():
    # Los alias históricos deben devolver lo mismo que las nuevas funciones.
    assert tz.now_argentina.__doc__  # existe
    a = tz.now_argentina()
    b = tz.now_business()
    # Ambos son naive y del mismo minuto (mismo tz por defecto).
    assert a.tzinfo is None and b.tzinfo is None
    assert abs((a - b).total_seconds()) < 5


def test_iso_business_pone_offset():
    dt = datetime(2026, 1, 1, 12, 0, 0)  # naive, tratado como UTC por defecto
    out = tz.iso_business(dt)
    assert out is not None
    # Con la zona de Argentina (fallback), el offset es -03:00.
    assert out.endswith("-03:00")


def test_tz_lee_del_perfil(monkeypatch):
    """Si el perfil declara otra zona, now_business la usa."""
    tz.invalidate_tz_cache()

    class _FakeSession:
        def close(self):
            pass

    monkeypatch.setattr("app.models.database.SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        "app.services.business_profile_service.get_profile",
        lambda db: {"timezone": "America/Cancun"},
    )
    got = tz._business_tz()
    assert "Cancun" in str(got)
    tz.invalidate_tz_cache()  # no contaminar otros tests


def test_tz_fallback_a_argentina_si_falla(monkeypatch):
    tz.invalidate_tz_cache()

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("app.models.database.SessionLocal", _boom)
    got = tz._business_tz()
    assert "Argentina" in str(got)
    tz.invalidate_tz_cache()
