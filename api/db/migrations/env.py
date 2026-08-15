from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from api.core.config import get_settings
from api.db.base import Base
import api.models  # noqa: F401  确保所有模型注册到 Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从项目 Settings 取 database_url；Alembic 是同步引擎，需转同步驱动
_db_url = get_settings().database_url
_db_url = _db_url.replace("postgresql+asyncpg://", "postgresql://").replace("sqlite+aiosqlite://", "sqlite://")
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
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
