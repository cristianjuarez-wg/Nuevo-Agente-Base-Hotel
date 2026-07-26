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

import pytest

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


def test_instagram_sin_secret_permisivo_en_dev(client, monkeypatch):
    """En DEBUG (dev/local) se acepta sin firma, para poder probar con curl/ngrok."""
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", "")
    monkeypatch.setattr(settings, "DEBUG", True)
    body = b'{"object": "instagram", "entry": []}'
    assert _post_ig(client, body, None).status_code == 200


def test_instagram_sin_secret_fail_closed_en_produccion(client, monkeypatch):
    """M6: en producción, sin App Secret NO se puede verificar el origen → 403.

    Un webhook abierto deja que cualquiera con la URL inyecte mensajes falsos al agente.
    """
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", "")
    monkeypatch.setattr(settings, "DEBUG", False)
    body = b'{"object": "instagram", "entry": []}'
    assert _post_ig(client, body, None).status_code == 403


def test_whatsapp_sin_token_fail_closed_en_produccion(client, monkeypatch):
    """M6: idem WhatsApp — sin TWILIO_AUTH_TOKEN el webhook rechaza en producción."""
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "DEBUG", False)
    r = client.post("/api/whatsapp/webhook",
                    data={"From": "whatsapp:+5491100000000", "Body": "hola"})
    assert r.status_code == 403


def test_whatsapp_sin_token_permisivo_en_dev(client, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "DEBUG", True)
    r = client.post("/api/whatsapp/webhook",
                    data={"From": "whatsapp:+5491100000000", "Body": ""})  # sin body → ignora
    assert r.status_code == 200


def test_public_url_usa_los_headers_del_proxy():
    """La firma de Twilio se valida contra la URL PÚBLICA, no la interna del contenedor.

    Detrás del proxy de Render, request.url reporta http://host-interno; si firmáramos contra
    eso, los POST legítimos de Twilio fallarían. Debe reconstruirse con X-Forwarded-*.
    """
    from types import SimpleNamespace
    from app.routers.whatsapp import _public_url

    req = SimpleNamespace(
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "api.hotel.com"},
        url=SimpleNamespace(path="/api/whatsapp/webhook", query=""),
    )
    assert _public_url(req) == "https://api.hotel.com/api/whatsapp/webhook"

    # Sin headers de proxy (dev local) cae a str(request.url), la URL tal cual la ve la app.
    class _Url(str):
        path = "/api/whatsapp/webhook"
        query = ""

    req_local = SimpleNamespace(
        headers={}, url=_Url("http://localhost:8010/api/whatsapp/webhook"),
    )
    assert _public_url(req_local) == "http://localhost:8010/api/whatsapp/webhook"


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


# ── (d) GETs de backoffice que estaban ABIERTOS (hallazgo C2 de la auditoría) ──
# El agujero no fueron 3 endpoints puntuales sino el patrón implícito de montar routers
# sin decidir qué es público. Estos tests fijan la decisión: todo lo de abajo exige
# credencial, y la whitelist de `test_superficie_publica_completa` es la única excepción.

# GETs que exponían datos de negocio (costos, entrenamiento, config) o PII sin auth.
_GETS_QUE_DEBEN_EXIGIR_CREDENCIAL = (
    "/api/usage/summary",              # gasto en USD
    "/api/usage/config",               # topes de gasto
    "/api/business-profile",           # perfil COMPLETO (contacto + facts internos)
    "/api/agents",                     # catálogo de agentes
    "/api/agents/centro-config",
    "/api/agents/training-schemas",
    "/api/agents/1",                   # config/prompts del agente
    "/api/agents/1/capabilities",
    "/api/agents/1/performance",       # costo de IA por agente
    "/api/agents/1/daily-report",
    "/api/agents/1/training",          # corpus de entrenamiento del cliente
    "/api/agents/1/skills",
    "/api/exchange-rate",              # config de cotización
    "/api/human-attention",            # horarios de guardia
    "/api/demo/status",                # conteos de la instancia
    "/api/chat/stats",                 # estado interno del servicio
    "/api/checkin/HTL-TEST",           # PII de pre-check-in (documento, nombre)
)


@pytest.mark.parametrize("path", _GETS_QUE_DEBEN_EXIGIR_CREDENCIAL)
def test_gets_de_backoffice_exigen_credencial(client, monkeypatch, path):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_KEY", "clave-real")
    r = client.get(path)
    assert r.status_code == 401, f"{path} debería exigir credencial (got {r.status_code})"


@pytest.mark.parametrize("path", _GETS_QUE_DEBEN_EXIGIR_CREDENCIAL)
def test_gets_de_backoffice_pasan_con_jwt(client, admin_headers, monkeypatch, path):
    """Con JWT del backoffice NO deben dar 401 (404/422 es aceptable: el recurso puede no existir)."""
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_KEY", "clave-real")
    r = client.get(path, headers=admin_headers)
    assert r.status_code != 401, f"{path} rechaza un JWT válido"


def test_superficie_publica_completa(client, monkeypatch):
    """WHITELIST: lo ÚNICO que puede responder sin credencial (ver main.py).

    Si un endpoint nuevo necesita entrar acá, es una decisión explícita — no un descuido.
    """
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_KEY", "clave-real")
    publicos = (
        "/",                                   # health
        "/api/chat/health",
        "/api/chat/theme",                     # tema del widget
        "/api/public/business-profile",        # identidad pública de la landing
        "/api/restaurant/menu/public",         # carta pública
        "/api/reservations/rooms",             # habitaciones que muestra la landing
    )
    for path in publicos:
        r = client.get(path)
        assert r.status_code == 200, f"{path} debe seguir siendo público (got {r.status_code})"
