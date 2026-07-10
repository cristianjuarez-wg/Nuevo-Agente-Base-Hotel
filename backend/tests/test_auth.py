"""
Fase 2.5 — auth real del backoffice (password bcrypt + JWT + fail-closed).

Sin OpenAI. Verifica: hash/verify, emisión/decodificación de JWT, authenticate,
require_admin/require_role, y que require_admin_key ya NO es fail-open en producción.
"""
import pytest
from fastapi import HTTPException

from app.core.security import auth
from app.models.admin_user import AdminUser


# ── Passwords ────────────────────────────────────────────────────────────────

def test_hash_y_verify():
    h = auth.hash_password("secreto123")
    assert h != "secreto123"
    assert auth.verify_password("secreto123", h) is True
    assert auth.verify_password("otra", h) is False


def test_verify_password_hash_corrupto():
    assert auth.verify_password("x", "no-es-un-hash") is False


# ── JWT ──────────────────────────────────────────────────────────────────────

def _user(id=1, email="a@b.com", role="admin"):
    u = AdminUser(email=email, role=role, active=True)
    u.id = id
    u.password_hash = "x"
    return u


def test_jwt_roundtrip():
    tok = auth.create_access_token(_user(id=7, email="op@h.com", role="operador"))
    payload = auth.decode_token(tok)
    assert payload["sub"] == "7"
    assert payload["email"] == "op@h.com"
    assert payload["role"] == "operador"


def test_jwt_invalido_lanza_401():
    with pytest.raises(HTTPException) as ei:
        auth.decode_token("no.es.un.jwt")
    assert ei.value.status_code == 401


# ── authenticate ─────────────────────────────────────────────────────────────

def test_authenticate(db):
    db.add(AdminUser(email="dueño@h.com", password_hash=auth.hash_password("pw"),
                     role="admin", active=True))
    db.commit()
    # OK
    u = auth.authenticate(db, "Dueño@h.com", "pw")  # case-insensitive en email
    assert u is not None and u.role == "admin"
    # password mala
    assert auth.authenticate(db, "dueño@h.com", "mala") is None
    # inexistente
    assert auth.authenticate(db, "nope@h.com", "pw") is None


# ── require_role ─────────────────────────────────────────────────────────────

def test_require_role_rechaza_rol_insuficiente():
    dep = auth.require_role("admin")
    operador = _user(role="operador")
    with pytest.raises(HTTPException) as ei:
        dep(user=operador)
    assert ei.value.status_code == 403


def test_require_role_acepta_rol_correcto():
    dep = auth.require_role("admin")
    admin = _user(role="admin")
    assert dep(user=admin) is admin


# ── require_admin_key: fail-closed en producción ─────────────────────────────

def test_admin_key_fail_closed_en_produccion(monkeypatch):
    from app.core.security import admin_auth
    monkeypatch.setattr(admin_auth.settings, "DEBUG", False)
    monkeypatch.setattr(admin_auth.settings, "ADMIN_KEY", None)
    # Sin token ni key, en producción → 401 (antes era acceso libre).
    with pytest.raises(HTTPException) as ei:
        admin_auth.require_admin_key(x_admin_key=None, authorization=None, db=None)
    assert ei.value.status_code == 401


def test_admin_key_legacy_sigue_funcionando(monkeypatch):
    from app.core.security import admin_auth
    monkeypatch.setattr(admin_auth.settings, "DEBUG", False)
    monkeypatch.setattr(admin_auth.settings, "ADMIN_KEY", "clave-real")
    # X-Admin-Key correcta → pasa (no lanza).
    admin_auth.require_admin_key(x_admin_key="clave-real", authorization=None, db=None)
    # incorrecta → 401
    with pytest.raises(HTTPException):
        admin_auth.require_admin_key(x_admin_key="mala", authorization=None, db=None)
