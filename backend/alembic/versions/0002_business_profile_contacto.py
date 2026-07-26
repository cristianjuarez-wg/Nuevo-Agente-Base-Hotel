"""business_profile: columnas de contacto público (aditivas).

Por qué existe esta revisión (hallazgo I5 — triple fuente de verdad del esquema):

`contact_phone` y `contact_email` (Fase 3.5) y `contact_address` / `instagram` (identidad
pública servida a la landing) se venían agregando SOLO con el bloque `ensure_column` de
`app/models/business_profile.py`, que **únicamente corre en SQLite**. En una DB Postgres ya
existente (Render, marcada con `alembic stamp 0001_baseline`) esas columnas NO se crean, y
el endpoint que las lee falla.

Esta revisión las agrega por el canal correcto: Alembic, idempotente (chequea el catálogo
antes de alterar), y funciona igual en Postgres y SQLite.

Revision ID: 0002_bp_contacto
Revises: 0001_baseline
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_bp_contacto"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "business_profile"
_COLUMNS = ("contact_phone", "contact_email", "contact_address", "instagram")


def _existing_columns(bind) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    """Agrega las columnas que falten (idempotente: la DB puede tener algunas ya)."""
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return  # instancia nueva: el baseline ya creó la tabla con todas las columnas
    existing = _existing_columns(bind)
    for col in _COLUMNS:
        if col not in existing:
            op.add_column(_TABLE, sa.Column(col, sa.String(), nullable=True))


def downgrade() -> None:
    """Quita las columnas de contacto (solo las que existan)."""
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    existing = _existing_columns(bind)
    for col in reversed(_COLUMNS):
        if col in existing:
            op.drop_column(_TABLE, col)
