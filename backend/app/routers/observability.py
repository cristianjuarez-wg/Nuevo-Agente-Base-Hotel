"""
Endpoint del dashboard de observabilidad por instancia (Fase 3.4).

GET /api/observability/summary?days=N → tokens/costo por agente, containment, errores.
Protegido con la auth de admin del backoffice.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from app.services import observability_service
from app.core.security.admin_auth import require_admin_key

router = APIRouter(prefix="/api/observability", tags=["Observability"])


@router.get("/summary", dependencies=[Depends(require_admin_key)])
def get_summary(days: Optional[int] = None):
    return observability_service.summary(days=days)
