"""baseline: esquema actual del hotel single-property (Fase 2.4).

Revisión BASELINE. Representa el esquema COMPLETO tal como está hoy (36 tablas, creadas
históricamente con Base.metadata.create_all + run_light_migrations).

Dos usos, ambos idempotentes:

1. **DB de producción existente (Render)** — las tablas YA existen. NO se recrean: se marca
   esta revisión como aplicada con `alembic stamp 0001_baseline`. A partir de ahí, TODO
   cambio de esquema va por una revisión Alembic nueva. Ver RUNBOOK_ALEMBIC.md.

2. **Instancia nueva desde cero** — `alembic upgrade head` crea el esquema desde
   Base.metadata (checkfirst=True: solo lo que falte; idempotente).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea el esquema completo desde Base.metadata (solo lo ausente; idempotente)."""
    # Importar todos los modelos ANTES de create_all: staff/contact/restaurant/hotel primero
    # (relationships por string), luego el barrido del paquete.
    import app.models.staff  # noqa: F401
    import app.models.contact  # noqa: F401
    import app.models.restaurant  # noqa: F401
    import app.models.hotel  # noqa: F401
    import importlib
    import pkgutil
    import app.models as _models_pkg
    for _m in pkgutil.iter_modules(_models_pkg.__path__):
        importlib.import_module(f"app.models.{_m.name}")
    from sqlalchemy.orm import configure_mappers
    configure_mappers()

    from app.models.database import Base
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """El baseline no se revierte (dropearía todo el esquema del negocio)."""
    raise NotImplementedError("El baseline no tiene downgrade — dropearía toda la base.")
