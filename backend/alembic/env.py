"""Alembic 환경. SYNC-STD-004#DEV-7 — 리비전 하나 = ERD 변경 하나."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# 모델 12개 전부 metadata에 올린다 (import 부작용)
import app.core.account.models  # noqa: E402, F401
import app.core.collab.models  # noqa: E402, F401
import app.core.project.models  # noqa: E402, F401
import app.core.reference.models  # noqa: E402, F401
import app.core.spec.models  # noqa: E402, F401
import app.core.tracking.models  # noqa: E402, F401
from alembic import context
from app.config import settings
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
