"""
Endpoints de autenticación del backoffice (Fase 2.5).

  POST /api/auth/login      → {access_token, user}  (email + password)
  GET  /api/auth/me         → datos del usuario logueado (valida el token)
  GET  /api/auth/users      → lista de admins (solo admin)
  POST /api/auth/users      → alta de admin/operador (solo admin)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.admin_user import AdminUser
from app.core.security import auth
from app.core.observability.logging_config import get_logger
from app.utils.timezone_utils import now_business

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginPayload(BaseModel):
    email: str
    password: str


class NewUserPayload(BaseModel):
    email: EmailStr
    password: str
    role: str = "operador"  # admin | operador


@router.post("/login")
async def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = auth.authenticate(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos.")
    user.last_login_at = now_business()
    db.commit()
    token = auth.create_access_token(user)
    logger.info("Backoffice login OK", email=user.email, role=user.role)
    return {"access_token": token, "token_type": "bearer", "user": user.to_dict()}


@router.get("/me")
async def me(user: AdminUser = Depends(auth.require_admin)):
    return user.to_dict()


@router.get("/users")
async def list_users(_: AdminUser = Depends(auth.require_role("admin")),
                     db: Session = Depends(get_db)) -> List[dict]:
    return [u.to_dict() for u in db.query(AdminUser).order_by(AdminUser.created_at.asc()).all()]


@router.post("/users")
async def create_user(payload: NewUserPayload,
                      _: AdminUser = Depends(auth.require_role("admin")),
                      db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.query(AdminUser).filter(AdminUser.email == email).first():
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email.")
    if payload.role not in ("admin", "operador"):
        raise HTTPException(status_code=400, detail="Rol inválido (admin | operador).")
    u = AdminUser(email=email, password_hash=auth.hash_password(payload.password),
                  role=payload.role, active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    logger.info("Admin user creado", email=email, role=payload.role)
    return u.to_dict()
