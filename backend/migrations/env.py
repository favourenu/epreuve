"""Alembic environment: uses the app's own settings and models.

The app runs migrations itself at startup (app.db.migrate); this file is also
used by the `alembic` command line for creating new revisions.
"""
from alembic import context
from sqlalchemy import pool

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import get_settings
from app.db import Base, make_engine, normalize_url

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=normalize_url(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # When called from app.db.migrate, reuse its connection (tests, startup).
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        _run(conn)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode rebuilds tables when needed.
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
