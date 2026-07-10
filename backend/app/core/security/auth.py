"""
Autenticación real del backoffice (Fase 2.5): password bcrypt + sesión JWT.

Reemplaza el X-Admin-Key fail-open. Expone:
  - hash_password / verify_password (bcrypt).
  - create_access_token / decode_token (JWT HS256).
  - authenticate(db, email, password) → AdminUser | None.
  - ensure_bootstrap_admin(db) → crea el primer admin desde BOOTSTRAP_ADMIN_* si la tabla
    está vacía (idempotente).
  - require_admin / require_role("admin") → dependencias FastAPI (fail-CLOSED).
"""
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.models.admin_user import AdminUser
from app.core.observability.logging_config import get_logger
from app.utils.timezone_utils import utcnow_naive

logger = get_logger(__name__)


# ── Passwords (bcrypt) ────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:  # noqa: BLE001 — hash corrupto/legacy → no autentica
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────
def create_access_token(user: AdminUser) -> str:
    now = utcnow_naive()
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Devuelve el payload o lanza HTTPException 401 si es inválido/expirado."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada. Volvé a iniciar sesión.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")


# ── Autenticación ─────────────────────────────────────────────────────────────
def authenticate(db: Session, email: str, password: str) -> Optional[AdminUser]:
    user = db.query(AdminUser).filter(
        AdminUser.email == (email or "").strip().lower(),
        AdminUser.active == True,  # noqa: E712
    ).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def ensure_bootstrap_admin(db: Session) -> None:
    """Crea el primer admin desde BOOTSTRAP_ADMIN_EMAIL/PASSWORD si la tabla está vacía.

    Idempotente: si ya hay algún admin, no hace nada. Si no hay bootstrap configurado y la
    tabla está vacía, deja un warning (el login no funcionará hasta crear un usuario).
    """
    try:
        if db.query(AdminUser).first() is not None:
            return
        email = (settings.BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
        pwd = settings.BOOTSTRAP_ADMIN_PASSWORD or ""
        if not email or not pwd:
            logger.warning("Backoffice sin admin: seteá BOOTSTRAP_ADMIN_EMAIL/PASSWORD "
                           "para crear el primer usuario, o creá uno por el endpoint /api/auth/users")
            return
        db.add(AdminUser(email=email, password_hash=hash_password(pwd), role="admin", active=True))
        db.commit()
        logger.info("Admin bootstrap creado", email=email)
    except Exception as e:  # noqa: BLE001 — nunca tumbar el arranque
        logger.warning("No se pudo crear el admin bootstrap", error=str(e))
        db.rollback()


# ── Dependencias FastAPI (fail-CLOSED) ────────────────────────────────────────
def _extract_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta el token de autenticación.")
    return authorization.split(" ", 1)[1].strip()


def require_admin(authorization: Optional[str] = Header(default=None),
                  db: Session = Depends(get_db)) -> AdminUser:
    """Exige un JWT válido de un AdminUser activo. Fail-closed: sin token → 401."""
    payload = decode_token(_extract_token(authorization))
    user = db.query(AdminUser).filter(
        AdminUser.id == int(payload.get("sub", 0)),
        AdminUser.active == True,  # noqa: E712
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no válido o desactivado.")
    return user


def require_role(role: str):
    """Dependencia que además exige un rol específico (ej. 'admin')."""
    def _dep(user: AdminUser = Depends(require_admin)) -> AdminUser:
        if user.role != role:
            raise HTTPException(status_code=403,
                                detail=f"Requiere rol '{role}'. Tu rol: '{user.role}'.")
        return user
    return _dep
