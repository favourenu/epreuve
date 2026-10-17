from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
# The schema as it was when migrations were introduced (see migrations/versions/0001_*).
BASELINE_REVISION = "0001"
BASELINE_TABLES = ("users", "sessions", "attempts", "attempt_items")


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    """Hosted Postgres providers (Neon, Render, Supabase) hand out postgres:// URLs;
    point SQLAlchemy at the psycopg 3 driver we ship."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str, **kwargs) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False}, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn, _record):  # pragma: no cover - driver hook
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    # Serverless Postgres (e.g. Neon) closes idle connections, so check before use
    # and recycle them regularly instead of failing on a stale one.
    kwargs.setdefault("pool_pre_ping", True)
    kwargs.setdefault("pool_recycle", 300)
    return create_engine(url, **kwargs)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate(bind: Engine | None = None) -> None:
    """Bring the database schema up to date. Safe to run on every startup."""
    from alembic import command
    from alembic.config import Config

    from app import models  # noqa: F401  (registers tables)

    bind = bind or engine
    with bind.begin() as conn:
        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and tables & set(BASELINE_TABLES):
            # Created before migrations existed: complete the baseline schema, then
            # record it as revision 0001 so later migrations apply on top.
            _upgrade_pre_migration_db(conn)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


# Kept for callers and tests that predate migrations.
init_db = migrate


def _baseline_metadata():
    """users and sessions exactly as at revision 0001 (frozen: never use the current models
    here, or later migrations would try to add columns that already exist)."""
    from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table

    md = MetaData()
    Table(
        "users", md,
        Column("id", String(36), primary_key=True),
        Column("email", String(320), nullable=False, unique=True, index=True),
        Column("name", String(100), nullable=False),
        Column("password_hash", String(255), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "sessions", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("token_hash", String(64), nullable=False, unique=True, index=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=False),
    )
    return md


def _upgrade_pre_migration_db(conn: Connection) -> None:
    # Databases from before accounts existed have attempts tables but no users/sessions.
    _baseline_metadata().create_all(conn)
    _migrate_attempt_owner(conn)


def _migrate_attempt_owner(conn: Connection) -> None:
    """Databases created before accounts existed have no attempts.user_id column.

    Add it (nullable, as SQLite can't add a NOT NULL column to existing rows).
    Rows without an owner stay hidden until the first account signs up and claims
    them (see services.auth.signup).
    """
    columns = {c["name"] for c in inspect(conn).get_columns("attempts")}
    if "user_id" not in columns:
        conn.execute(text("ALTER TABLE attempts ADD COLUMN user_id VARCHAR(36) REFERENCES users(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_attempts_user_id ON attempts (user_id)"))
