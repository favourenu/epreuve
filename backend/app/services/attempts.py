"""Attempt lifecycle: start, answer one question at a time, finish, grade, feedback.

Rules mirror real assessment platforms and are enforced server-side:
- the timer is the server's deadline, not the browser's;
- questions are answered in order and cannot be revisited;
- correct answers are never sent to the client before the attempt is completed.
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Attempt, AttemptItem, AttemptStatus, FeedbackStatus, utcnow
from app.question_bank import CodeQuestion, QuestionBank, public_question, question_from_snapshot
from app.services import grading
from app.services.ai.service import AIService, AIUnavailableError
from app.services.code_runner import run_tests
from app.services.feedback import (
    SYSTEM_PROMPT,
    FeedbackReport,
    build_user_prompt,
    make_check,
    report_to_json,
    written_items_to_grade,
)

log = logging.getLogger(__name__)


class AttemptError(Exception):
    status_code = 400


class NotFoundError(AttemptError):
    status_code = 404


class ConflictError(AttemptError):
    status_code = 409


def get_attempt(db: Session, attempt_id: str, user_id: str | None) -> Attempt:
    """Load an attempt owned by `user_id`. Another user's attempt is reported as
    not found, so its existence isn't revealed. `user_id=None` is for internal
    callers (background jobs) that already hold a trusted attempt id."""
    query = select(Attempt).where(Attempt.id == attempt_id).options(selectinload(Attempt.items))
    if user_id is not None:
        query = query.where(Attempt.user_id == user_id)
    attempt = db.scalar(query)
    if attempt is None:
        raise NotFoundError("Attempt not found")
    return attempt


def close_expired(db: Session, user_id: str) -> list[Attempt]:
    """Close the user's in-progress attempts whose time is up. Returns the ones closed,
    so the caller can queue their feedback."""
    running = db.scalars(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.status == AttemptStatus.IN_PROGRESS)
        .options(selectinload(Attempt.items))
    ).all()
    return [a for a in running if enforce_deadline(db, a)]


def active_attempt(db: Session, user_id: str, test_id: str) -> Attempt | None:
    """The user's in-progress attempt at a test. Call close_expired first."""
    return db.scalar(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.test_id == test_id, Attempt.status == AttemptStatus.IN_PROGRESS)
        .order_by(Attempt.started_at.desc())
        .options(selectinload(Attempt.items))
    )


def start_attempt(db: Session, bank: QuestionBank, test_id: str, user_id: str) -> tuple[Attempt, bool]:
    """Start a test, or resume the one already running.

    Returns (attempt, created)."""
    test = bank.tests.get(test_id)
    if test is None:
        raise NotFoundError(f"Unknown test '{test_id}'")
    if existing := active_attempt(db, user_id, test_id):
        return existing, False
    now = utcnow()
    attempt = Attempt(
        user_id=user_id,
        test_id=test.id,
        test_title=test.title,
        started_at=now,
        deadline=now + timedelta(minutes=test.time_limit_minutes),
    )
    seen = dict(
        db.execute(
            select(AttemptItem.question_id, func.count())
            .join(Attempt, Attempt.id == AttemptItem.attempt_id)
            .where(Attempt.user_id == user_id)
            .group_by(AttemptItem.question_id)
        ).all()
    )
    for position, q in enumerate(bank.pick_questions(test, times_seen=seen)):
        attempt.items.append(
            AttemptItem(
                position=position,
                question_id=q.id,
                category=q.category,
                question_json=q.model_dump_json(),
                max_points=q.points,
            )
        )
    db.add(attempt)
    db.commit()
    return attempt, True


def is_expired(attempt: Attempt) -> bool:
    grace = timedelta(seconds=get_settings().deadline_grace_seconds)
    return utcnow() > attempt.deadline + grace


def enforce_deadline(db: Session, attempt: Attempt) -> bool:
    """Close an in-progress attempt whose time is up. Returns True if it was closed now."""
    if attempt.status == AttemptStatus.IN_PROGRESS and is_expired(attempt):
        finish_attempt(db, attempt, timed_out=True)
        return True
    return False


def remaining_seconds(attempt: Attempt) -> int:
    return max(0, int((attempt.deadline - utcnow()).total_seconds()))


def current_question(attempt: Attempt) -> dict[str, Any] | None:
    if attempt.status != AttemptStatus.IN_PROGRESS or attempt.current_index >= len(attempt.items):
        return None
    item = attempt.items[attempt.current_index]
    return public_question(question_from_snapshot(item.question))


def _require_current(db: Session, attempt: Attempt, position: int) -> AttemptItem:
    if enforce_deadline(db, attempt):
        raise ConflictError("Time is up. Your attempt has been submitted.")
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise ConflictError("This attempt is already completed")
    if position != attempt.current_index:
        raise ConflictError(
            "You can only answer the current question; previous questions cannot be revisited"
        )
    return attempt.items[position]


def submit_answer(db: Session, attempt: Attempt, position: int, answer: Any) -> bool:
    """Save an answer and advance. Returns True if this completed the attempt."""
    item = _require_current(db, attempt, position)
    q = question_from_snapshot(item.question)
    try:
        normalized = grading.normalize_answer(q, answer)
    except grading.InvalidAnswerError as exc:
        raise AttemptError(str(exc)) from exc

    item.answer_json = json.dumps(normalized) if normalized is not None else None
    item.answered_at = utcnow()
    attempt.current_index += 1
    if attempt.current_index >= len(attempt.items):
        finish_attempt(db, attempt, timed_out=False)
        return True
    db.commit()
    return False


def run_code(db: Session, attempt: Attempt, position: int, code: str) -> dict[str, Any]:
    """Run the current coding question against its visible example tests only."""
    item = _require_current(db, attempt, position)
    q = question_from_snapshot(item.question)
    if not isinstance(q, CodeQuestion):
        raise AttemptError("This question is not a coding question")
    if len(code) > 50_000:
        raise AttemptError("Code is too long")
    visible = [t.model_dump() for t in q.tests if not t.hidden]
    return run_tests(code, q.function_name, visible).public()


def recompute_score(attempt: Attempt) -> None:
    attempt.score = round(sum(i.points or 0 for i in attempt.items), 2)
    attempt.max_score = round(sum(i.max_points for i in attempt.items), 2)


def finish_attempt(db: Session, attempt: Attempt, timed_out: bool) -> None:
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise ConflictError("This attempt is already completed")
    attempt.status = AttemptStatus.COMPLETED
    attempt.timed_out = timed_out
    attempt.submitted_at = min(utcnow(), attempt.deadline) if timed_out else utcnow()

    for item in attempt.items:
        q = question_from_snapshot(item.question)
        result = grading.grade(q, item.answer)
        item.points = result.points
        item.is_correct = result.is_correct
        item.grading_json = json.dumps(result.detail)

    recompute_score(attempt)
    attempt.feedback_status = FeedbackStatus.PENDING
    db.commit()


async def generate_feedback(db: Session, attempt: Attempt, ai: AIService) -> None:
    """Grade pending written answers and write the study report in one AI request."""
    expected = written_items_to_grade(attempt)
    try:
        report, provider = await ai.generate(
            SYSTEM_PROMPT, build_user_prompt(attempt), FeedbackReport, check=make_check(expected)
        )
    except AIUnavailableError as exc:
        log.warning("Feedback failed for attempt %s: %s", attempt.id, exc)
        attempt.feedback_status = FeedbackStatus.FAILED
        attempt.feedback_error = str(exc)
        db.commit()
        return

    grades = {g.question_id: g for g in report.written_grades}
    for item in attempt.items:
        if item.points is None and item.question_id in grades:
            g = grades[item.question_id]
            item.points = round(min(max(g.score, 0.0), item.max_points), 2)
            item.is_correct = item.points >= 0.7 * item.max_points
            detail = item.grading or {}
            detail["feedback"] = g.feedback
            item.grading_json = json.dumps(detail)

    recompute_score(attempt)
    attempt.feedback_json = report_to_json(report)
    attempt.feedback_provider = provider
    attempt.feedback_status = FeedbackStatus.READY
    attempt.feedback_error = None
    db.commit()


def recover_interrupted_feedback(db: Session) -> int:
    """Mark feedback left 'pending' by a server restart as failed so it can be retried."""
    stuck = db.scalars(select(Attempt).where(Attempt.feedback_status == FeedbackStatus.PENDING)).all()
    for attempt in stuck:
        attempt.feedback_status = FeedbackStatus.FAILED
        attempt.feedback_error = "Feedback generation was interrupted by a server restart. Retry it."
    db.commit()
    return len(stuck)
