from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Config del proyecto (Fase 2.4) ────────────────────────────────────────────
# 1) La URL sale de settings.DATABASE_URL (Render=PostgreSQL, local=SQLite), NO del
#    alembic.ini — así no duplicamos la config ni versionamos credenciales.
# 2) target_metadata = Base.metadata con TODOS los modelos de dominio registrados, para
#    que `alembic revision --autogenerate` vea el esquema completo.
from app.config import settings  # noqa: E402
from app.models.database import Base  # noqa: E402

# Importar TODOS los modelos ANTES de configurar mappers: así todas las Table están en
# Base.metadata y las FKs por string resuelven. staff antes que hotel (hotel referencia
# staff_members). Luego el barrido del paquete cubre el resto.
import app.models.staff  # noqa: E402,F401
import app.models.contact  # noqa: E402,F401
import app.models.restaurant  # noqa: E402,F401
import app.models.hotel  # noqa: E402,F401
import importlib, pkgutil  # noqa: E402
import app.models as _models_pkg  # noqa: E402
for _m in pkgutil.iter_modules(_models_pkg.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from sqlalchemy.orm import configure_mappers  # noqa: E402
configure_mappers()

_db_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
