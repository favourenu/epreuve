import os
import tempfile
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import pytest

from app.db import init_db, make_engine, migrate
from app.models import Attempt
from app.services import auth


def test_pre_account_database_is_migrated_and_claimed_by_first_user():
    path = Path(tempfile.mkdtemp()) / "legacy.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as conn:  # the attempts table as it was before accounts existed
        conn.execute(text(
            "CREATE TABLE attempts (id VARCHAR(36) PRIMARY KEY, test_id VARCHAR(100), test_title VARCHAR(200), "
            "status VARCHAR(20), started_at DATETIME, deadline DATETIME, submitted_at DATETIME, timed_out BOOLEAN, "
            "current_index INTEGER, score FLOAT, max_score FLOAT, feedback_status VARCHAR(20), feedback_json TEXT, "
            "feedback_provider VARCHAR(100), feedback_error TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO attempts (id, test_id, test_title, status, started_at, deadline, timed_out, current_index) "
            "VALUES ('old-1', 'critical-thinking', 'Critical Thinking', 'completed', '2026-10-01', '2026-10-01', 0, 8)"
        ))

    init_db(engine)
    init_db(engine)  # idempotent

    with sessionmaker(bind=engine)() as db:
        first = auth.signup(db, "first@example.com", "a-good-password", "First")
        second = auth.signup(db, "second@example.com", "a-good-password", "Second")
        assert db.get(Attempt, "old-1").user_id == first.id != second.id


def _fresh_sqlite():
    return make_engine(f"sqlite:///{(Path(tempfile.mkdtemp()) / 'm.db').as_posix()}")


def _schema_diff(engine):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db import Base

    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


def test_migrations_produce_exactly_the_models_schema():
    """If this fails, a model changed without a migration: run
    `alembic revision --autogenerate -m "..."` from backend/."""
    engine = _fresh_sqlite()
    migrate(engine)
    assert _schema_diff(engine) == []


def test_migrate_is_safe_to_run_on_every_startup():
    engine = _fresh_sqlite()
    migrate(engine)
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003"


def test_database_from_before_migrations_keeps_its_data():
    """A database made by the old create_all() startup (accounts era, no alembic_version)."""
    from alembic import command
    from alembic.config import Config

    from app.db import MIGRATIONS_DIR

    engine = _fresh_sqlite()
    with engine.begin() as conn:  # build the 0001 schema, then forget it was migrated
        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
        conn.execute(text("DROP TABLE alembic_version"))
        conn.execute(text("INSERT INTO users (id, email, name, password_hash, created_at) "
                          "VALUES ('u1', 'old@example.com', 'Old', 'x', '2026-01-01')"))
    uid = "u1"
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003"
        assert conn.execute(text("SELECT id FROM users")).scalar() == uid
    assert _schema_diff(engine) == []


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL to run against Postgres")
def test_postgres_migrations_and_round_trip():
    """Run with e.g. TEST_POSTGRES_URL=postgresql://postgres:pw@localhost:5432/postgres"""
    from datetime import timedelta

    from app.models import UserSession, utcnow

    engine = make_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    migrate(engine)
    migrate(engine)
    assert _schema_diff(engine) == []
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        user = auth.signup(db, "pg@example.com", "a-good-password", "Pg")
        db.add(UserSession(user_id=user.id, token_hash="x" * 64, expires_at=utcnow() + timedelta(days=1)))
        db.commit()
        stored = db.query(UserSession).filter_by(user_id=user.id).one()
        assert stored.expires_at.tzinfo is not None


def test_upgrading_keeps_every_row_in_child_tables():
    """Regression: SQLite rebuilds tables during migrations; with foreign keys on, that
    used to cascade-delete every saved answer (attempt_items) when going 0002 -> 0003."""
    from alembic import command
    from alembic.config import Config

    from app.db import MIGRATIONS_DIR

    engine = _fresh_sqlite()
    with engine.begin() as conn:
        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0002")
        conn.execute(text("INSERT INTO users (id, email, name, password_hash, created_at) VALUES ('u1', 'a@example.com', 'A', 'x', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO attempts (id, user_id, test_id, test_title, status, started_at, deadline, timed_out, current_index) "
            "VALUES ('a1', 'u1', 't', 'T', 'completed', '2026-01-01', '2026-01-01', 0, 2)"
        ))
        for i in range(2):
            conn.execute(text(
                "INSERT INTO attempt_items (attempt_id, position, question_id, category, question_json, max_points) "
                f"VALUES ('a1', {i}, 'q{i}', 'c', '{{}}', 1)"
            ))
        conn.execute(text("INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES ('u1', 'h', '2026-01-01', '2027-01-01')"))

    migrate(engine)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM attempt_items")).scalar() == 2
        assert conn.execute(text("SELECT count(*) FROM sessions")).scalar() == 1
        assert conn.execute(text("SELECT mode FROM attempts")).scalar() == "practice"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1  # switched back on
