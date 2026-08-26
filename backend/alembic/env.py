from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.engine.url import URL
from sqlalchemy import pool
from alembic import context
from urllib.parse import urlsplit, parse_qsl
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import settings
from backend.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    # Same fix as backend/backend/db/session.py: SQLAlchemy's own DSN
    # parser splits user:pass@host on the FIRST "@", so a password
    # containing an unescaped "@" gets misparsed into a garbage hostname
    # (the DB password does contain one). Parse leniently with urlsplit
    # (splits on the LAST "@", per RFC 3986) and rebuild via URL.create,
    # which percent-encodes each component correctly instead of
    # re-serializing an ambiguous string.
    raw_url = settings.DATABASE_URL
    parts = urlsplit(raw_url)
    url_obj = URL.create(
        "postgresql+asyncpg",
        username=parts.username,
        password=parts.password,
        host=parts.hostname,
        port=parts.port,
        database=parts.path.lstrip("/") or None,
        query=dict(parse_qsl(parts.query)),
    )
    # Return a string (matching this function's original contract) — the
    # URL object's own render_as_string percent-encodes the password
    # correctly, so this round-trip is safe unlike the original hand-built
    # string.
    return url_obj.render_as_string(hide_password=False)

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
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
