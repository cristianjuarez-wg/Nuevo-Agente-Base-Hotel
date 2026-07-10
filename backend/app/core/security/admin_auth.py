"""
Protección de acciones del backoffice (Fase 2.5 — FAIL-CLOSED en producción).

Antes: X-Admin-Key con fail-OPEN incondicional (si ADMIN_KEY estaba vacía, acceso libre
SIEMPRE, incluso en producción). Ahora `require_admin_key` acepta DOS credenciales:
  1. JWT válido de un AdminUser activo (Authorization: Bearer ... — mecanismo nuevo).
  2. X-Admin-Key == settings.ADMIN_KEY (legacy, solo si ADMIN_KEY está configurada; para
     scripts/curl durante la transición).

Fail-closed en PRODUCCIÓN (settings.DEBUG == False): sin JWT y sin X-Admin-Key correcta → 401.
En DEV/TEST (DEBUG == True) sin ninguna credencial configurada se permite, para no frenar el
desarrollo local ni los tests — ese es el único caso de acceso libre, y nunca en producción.

Uso (sin cambios en los routers existentes):
    from app.core.security.admin_auth import require_admin_key
    @router.post("/algo-critico", dependencies=[Depends(require_admin_key)])
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db


def require_admin_key(
    x_admin_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    """Autoriza con JWT o X-Admin-Key. Fail-closed en producción."""
    # 1) JWT (mecanismo nuevo). Import diferido para evitar ciclos.
    if authorization and authorization.lower().startswith("bearer "):
        from app.core.security.auth import require_admin
        require_admin(authorization=authorization, db=db)  # lanza 401 si es inválido
        return

    # 2) X-Admin-Key legacy — válida solo si ADMIN_KEY está configurada.
    expected = (settings.ADMIN_KEY or "").strip()
    if expected and (x_admin_key or "").strip() == expected:
        return

    # 3) Sin credencial. En DEV/TEST sin nada configurado, se permite (no frenar el desarrollo).
    #    En PRODUCCIÓN, o cuando hay ADMIN_KEY configurada, es fail-closed.
    if settings.DEBUG and not expected:
        return
    raise HTTPException(
        status_code=401,
        detail="Autenticación requerida. Iniciá sesión en el backoffice.",
    )
