import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores UTC and always returns timezone-aware datetimes (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use UTC-aware datetimes")
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Stored lower-cased; uniqueness is case-insensitive in practice.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class UserSession(Base):
    """A logged-in browser. Only a keyed hash of the cookie token is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())

    user: Mapped[User] = relationship()


class AttemptStatus:
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class FeedbackStatus:
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[str] = mapped_column(String(100), index=True)
    test_title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default=AttemptStatus.IN_PROGRESS, index=True)

    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    deadline: Mapped[datetime] = mapped_column(UTCDateTime())
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set when the attempt was closed by the deadline rather than by the user.
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)

    current_index: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float | None] = mapped_column(Float)

    feedback_status: Mapped[str | None] = mapped_column(String(20))
    feedback_json: Mapped[str | None] = mapped_column(Text)
    feedback_provider: Mapped[str | None] = mapped_column(String(100))
    feedback_error: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["AttemptItem"]] = relationship(
        back_populates="attempt",
        order_by="AttemptItem.position",
        cascade="all, delete-orphan",
    )

    @property
    def feedback(self) -> dict[str, Any] | None:
        return json.loads(self.feedback_json) if self.feedback_json else None


class AttemptItem(Base):
    """One question within an attempt, with a snapshot of the question as served."""

    __tablename__ = "attempt_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    # Snapshot so past attempts stay reviewable even if the question bank changes.
    question_json: Mapped[str] = mapped_column(Text)

    answer_json: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    points: Mapped[float | None] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    grading_json: Mapped[str | None] = mapped_column(Text)

    attempt: Mapped[Attempt] = relationship(back_populates="items")

    @property
    def question(self) -> dict[str, Any]:
        return json.loads(self.question_json)

    @property
    def answer(self) -> Any:
        return json.loads(self.answer_json) if self.answer_json is not None else None

    @property
    def grading(self) -> dict[str, Any] | None:
        return json.loads(self.grading_json) if self.grading_json else None
