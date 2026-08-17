"""Alembic muhiti — async SQLAlchemy bilan."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import settings
from src.core.database import Base

# Barcha modellar ro'yxatga olinishi uchun import qilinadi
from src.modules.agents.infrastructure import models as _agents  # noqa: F401
from src.modules.calls.infrastructure import models as _calls  # noqa: F401
from src.modules.clients.infrastructure import models as _clients  # noqa: F401
from src.modules.scoring.infrastructure import models as _scoring  # noqa: F401
from src.modules.scoring.infrastructure import rubric_models as _rubric  # noqa: F401
from src.modules.settings.infrastructure import models as _settings  # noqa: F401
from src.modules.surveys.infrastructure import models as _surveys  # noqa: F401
from src.modules.users.infrastructure import models as _users  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
