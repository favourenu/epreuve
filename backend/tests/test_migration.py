import tempfile
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db import init_db, make_engine
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
