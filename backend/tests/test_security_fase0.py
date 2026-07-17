"""
Fase 0 — endurecimiento de seguridad (pre-producción).

Sin OpenAI. Verifica:
  (a) POST /api/auth/login: el rate-limit (5/min por IP) devuelve 429 al superarlo y no
      rompe el login válido.
  (b) Webhook de Instagram: con INSTAGRAM_APP_SECRET configurado, firma inválida → 403 y
      firma válida (HMAC-SHA256 del body crudo) → pasa.
  (c) Routers de backoffice: sin credencial → 401 en producción (DEBUG=False); con JWT → OK.
"""
import hashlib
import hmac

from app.config import settings


# ── (a) Rate limit en login ──────────────────────────────────────────────────

def test_login_valido_no_se_rompe_con_rate_limit(client, db):
    from app.models.admin_user import AdminUser
    from app.core.security import auth

    db.add(AdminUser(email="rl-ok@h.com", password_hash=auth.hash_password("pw"),
                     role="admin", active=True))
    db.commit()
    r = client.post("/api/auth/login", json={"email": "rl-ok@h.com", "password": "pw"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_429_al_superar_el_limite(client):
    # Límite: 5/minuto por IP (el test anterior suma 1 desde el mismo host de test).
    # Enviamos logins malos hasta que el limiter corte: alguna respuesta debe ser 429.
    statuses = [
        client.post("/api/auth/login", json={"email": "x@h.com", "password": "mala"}).status_code
        for _ in range(8)
    ]
    assert 429 in statuses
    assert all(s in (401, 429) for s in statuses)


# ── (b) Firma del webhook de Instagram ───────────────────────────────────────

def _post_ig(client, body: bytes, secret: str | None):
    headers = {}
    if secret is not None:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={sig}"
    return client.post("/api/instagram/webhook", content=body, headers=headers)


def test_instagram_firma_invalida_403(client, monkeypatch):
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", "app-secret-real")
    body = b'{"object": "instagram", "entry": []}'
    r = _post_ig(client, body, "otro-secret")  # firma calculada con una clave distinta
    assert r.status_code == 403
    # Sin header de firma también se rechaza.
    assert _post_ig(client, body, None).status_code == 403


def test_instagram_firma_valida_pasa(client, monkeypatch):
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", "app-secret-real")
    body = b'{"object": "instagram", "entry": []}'  # sin eventos → no invoca al agente
    assert _post_ig(client, body, "app-secret-real").status_code == 200


def test_instagram_sin_secret_fail_open(client, monkeypatch):
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", "")
    body = b'{"object": "instagram", "entry": []}'
    assert _post_ig(client, body, None).status_code == 200


# ── (c) Routers de backoffice: fail-closed en producción ─────────────────────

def test_backoffice_sin_credencial_401_en_produccion(client, monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_KEY", "clave-real")
    for path in ("/api/leads/active", "/api/conversations", "/api/chat-themes/",
                 "/api/restaurant/menu", "/api/restaurant/stats", "/api/reservations/bookings"):
        r = client.get(path)
        assert r.status_code == 401, f"{path} debería exigir autenticación (got {r.status_code})"


def test_backoffice_con_jwt_no_es_401(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_KEY", "clave-real")
    r = client.get("/api/conversations", headers=admin_headers)
    assert r.status_code != 401
    r = client.get("/api/chat-themes/", headers=admin_headers)
    assert r.status_code == 200


def test_endpoints_publicos_siguen_abiertos_en_produccion(client, monkeypatch):
    """Los endpoints del sitio/widget del huésped NO deben pedir credencial."""
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_KEY", "clave-real")
    assert client.get("/api/chat/theme").status_code == 200
    assert client.get("/api/restaurant/menu/public").status_code == 200
    assert client.get("/api/reservations/rooms").status_code == 200
