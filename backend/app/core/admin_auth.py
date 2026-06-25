"""
Protección de acciones CRÍTICAS del backoffice mediante una clave de administración.

El backoffice del prototipo es de acceso libre (el cliente explora todo), PERO las
acciones sensibles/destructivas —cambiar los topes de gasto, la cotización, o resetear
la base— se protegen con una clave compartida (header `X-Admin-Key`).

Diseño:
- Si `settings.ADMIN_KEY` está vacío (None/"") → NO se exige clave. Así dev/local y los
  tests siguen funcionando sin fricción.
- Si está seteado (Render/producción) → la request debe traer el header `X-Admin-Key`
  con el mismo valor; si falta o no coincide, 403.

Uso:
    from app.core.admin_auth import require_admin_key
    @router.post("/algo-critico", dependencies=[Depends(require_admin_key)])
    ...
"""
from fastapi import Header, HTTPException
from typing import Optional

from app.config import settings


def require_admin_key(x_admin_key: Optional[str] = Header(default=None)) -> None:
    """Dependencia FastAPI: valida el header X-Admin-Key contra settings.ADMIN_KEY.

    No exige nada si ADMIN_KEY no está configurada (dev/local). En producción, rechaza
    con 403 si la clave falta o no coincide.
    """
    expected = (settings.ADMIN_KEY or "").strip()
    if not expected:
        return  # sin clave configurada → acceso libre (dev/local)
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(
            status_code=403,
            detail="Clave de administración inválida. Esta acción está protegida.",
        )
