from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the app importable and pull config/metadata from it.
from app.config import settings
from app.database import Base
import app.models  # noqa: F401  (register all models on Base.metadata)

config = context.config

# Inject the runtime database URL from app settings (overrides alembic.ini).
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# SQLite needs batch mode to support ALTER TABLE in migrations.
_RENDER_BATCH = settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_RENDER_BATCH,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_RENDER_BATCH,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
