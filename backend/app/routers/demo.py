"""
Router de DATOS DE DEMOSTRACIÓN (control desde el backoffice).

  GET  /api/demo/status     → conteos de datos demo actuales
  POST /api/demo/populate   → regenera el dataset demo (limpia lo demo y crea fresco)
  POST /api/demo/clear      → borra solo los datos demo (is_demo=True)
  POST /api/demo/reset-all  → BORRA TODO lo operativo (real + demo); conserva la config

/clear y /populate operan sobre registros is_demo=True. /reset-all es la operación
destructiva que vacía la base de datos generados por usuarios reales además de la demo.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db, engine
from app.services import demo_data_service
from app.domains.hotel.reset_tables import reset_all
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/demo", tags=["Demo"])


@router.get("/status")
def demo_status(db: Session = Depends(get_db)):
    """Cuántos registros demo hay hoy."""
    return demo_data_service.counts(db)


@router.post("/populate", dependencies=[Depends(require_admin_key)])
def demo_populate(db: Session = Depends(get_db)):
    """Regenera el dataset demo (limpia lo demo previo y crea uno fresco con fechas de hoy).

    Acción CRÍTICA: protegida por X-Admin-Key."""
    try:
        created = demo_data_service.populate(db)
        return {"ok": True, "created": created}
    except Exception as e:
        logger.error("Demo populate failed", error=str(e))
        raise HTTPException(500, f"No se pudo generar la demo: {e}")


@router.post("/clear", dependencies=[Depends(require_admin_key)])
def demo_clear(db: Session = Depends(get_db)):
    """Borra solo los datos marcados como demo.

    Acción CRÍTICA: protegida por X-Admin-Key."""
    try:
        deleted = demo_data_service.clear(db)
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        logger.error("Demo clear failed", error=str(e))
        raise HTTPException(500, f"No se pudo limpiar la demo: {e}")


class ResetAllRequest(BaseModel):
    confirm: str


@router.post("/reset-all", dependencies=[Depends(require_admin_key)])
def demo_reset_all(payload: ResetAllRequest):
    """BORRA TODO lo operativo (reservas, huéspedes, leads, conversaciones, tickets,
    pedidos y reservas del restaurante, vouchers, equipo, snapshots, legacy turismo),
    sin importar is_demo. CONSERVA la configuración del cliente (habitaciones, carta,
    base de conocimiento, comercios amigos, promos, temas, topes del agente).

    Irreversible. Exige la palabra de confirmación "RESETEAR" en el body para evitar
    ejecuciones accidentales (barrera contra el accidente, no contra un atacante: el
    backoffice no tiene login — deuda conocida, común a todo el admin).
    """
    if payload.confirm != "RESETEAR":
        raise HTTPException(400, "Confirmación inválida. Tipeá RESETEAR para confirmar.")

    # SQL crudo en AUTOCOMMIT por sentencia: si una tabla no existe, no aborta el resto
    # (clave en Postgres/Render). Opera sobre la DB activa (en Render, producción).
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            deleted = reset_all(conn)
    except Exception as e:  # noqa: BLE001
        logger.error("Reset-all failed", error=str(e))
        raise HTTPException(500, f"No se pudo resetear: {e}")

    total = sum(deleted.values())

    # Vaciar el cache en RAM del agente: las conversaciones borradas pueden estar
    # cacheadas y revivirían en el próximo mensaje. Best-effort.
    try:
        from app.services.agent_service import agent_service
        agent_service.conversation_history.clear()
        agent_service.session_metadata.clear()
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo limpiar el cache RAM del agente tras reset-all", error=str(e))
    try:
        from app.services.conversation_state_manager import conversation_state_manager
        # Vaciar el dict de estados multi-paso si está expuesto.
        states = getattr(conversation_state_manager, "_states", None)
        if isinstance(states, dict):
            states.clear()
    except Exception:  # noqa: BLE001
        pass

    logger.warning("RESET ALL ejecutado desde el backoffice",
                   total_rows_deleted=total, tables=list(deleted.keys()))

    return {"ok": True, "deleted": deleted, "total": total}
