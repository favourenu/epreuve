from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn, _record):  # pragma: no cover - driver hook
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind: Engine | None = None) -> None:
    from app import models  # noqa: F401  (registers tables)

    bind = bind or engine
    Base.metadata.create_all(bind=bind)
    _migrate_attempt_owner(bind)


def _migrate_attempt_owner(bind: Engine) -> None:
    """Databases created before accounts existed have no attempts.user_id column.

    Add it (nullable, as SQLite can't add a NOT NULL column to existing rows).
    Rows without an owner stay hidden until the first account signs up and claims
    them (see services.auth.signup).
    """
    columns = {c["name"] for c in inspect(bind).get_columns("attempts")}
    if "user_id" not in columns:
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE attempts ADD COLUMN user_id VARCHAR(36) REFERENCES users(id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_attempts_user_id ON attempts (user_id)"))
