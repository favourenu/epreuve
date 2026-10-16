import logging
from collections import defaultdict
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_ai_service, get_current_user, get_session_factory
from app.models import Attempt, AttemptStatus, FeedbackStatus, User, utcnow
from app.question_bank import QuestionBank, get_bank
from app.schemas import (
    AnswerRequest,
    AttemptListItem,
    AttemptReview,
    AttemptState,
    CategoryScore,
    ReviewItem,
    RunCodeRequest,
    StartAttemptRequest,
)
from app.services import attempts as svc
from app.services.ai.service import AIService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/attempts", tags=["attempts"])


async def run_feedback(attempt_id: str, session_factory: Callable[[], Session], ai: AIService) -> None:
    db = session_factory()
    try:
        attempt = svc.get_attempt(db, attempt_id, user_id=None)
        await svc.generate_feedback(db, attempt, ai)
    except Exception as exc:  # never leave feedback stuck in "pending"
        log.exception("Feedback task crashed for attempt %s", attempt_id)
        db.rollback()
        attempt = db.get(Attempt, attempt_id)
        if attempt is not None:
            attempt.feedback_status = FeedbackStatus.FAILED
            attempt.feedback_error = f"Unexpected error: {exc}"
            db.commit()
    finally:
        db.close()


class _Ctx:
    """Bundles what endpoints need: the signed-in user, the DB, and a way to queue
    feedback for attempts that get finished during the request."""

    def __init__(
        self,
        background: BackgroundTasks,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
        ai: AIService = Depends(get_ai_service),
        session_factory: Callable[[], Session] = Depends(get_session_factory),
    ):
        self.background, self.user, self.db = background, user, db
        self.ai, self.session_factory = ai, session_factory

    def attempt(self, attempt_id: str) -> Attempt:
        try:
            return svc.get_attempt(self.db, attempt_id, self.user.id)
        except svc.AttemptError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    def queue_feedback(self, attempt: Attempt) -> None:
        self.background.add_task(run_feedback, attempt.id, self.session_factory, self.ai)

    def enforce_deadline(self, attempt: Attempt) -> None:
        if svc.enforce_deadline(self.db, attempt):
            self.queue_feedback(attempt)

    def close_expired(self) -> None:
        for attempt in svc.close_expired(self.db, self.user.id):
            self.queue_feedback(attempt)


def _percent(a: Attempt) -> float | None:
    return round(100 * a.score / a.max_score, 1) if a.max_score and a.score is not None else None


def _list_item(a: Attempt) -> AttemptListItem:
    return AttemptListItem(
        id=a.id,
        test_id=a.test_id,
        test_title=a.test_title,
        status=a.status,
        started_at=a.started_at,
        submitted_at=a.submitted_at,
        timed_out=a.timed_out,
        score=a.score,
        max_score=a.max_score,
        percent=_percent(a),
        feedback_status=a.feedback_status,
    )


def _state(a: Attempt) -> AttemptState:
    return AttemptState(
        id=a.id,
        test_id=a.test_id,
        test_title=a.test_title,
        status=a.status,
        started_at=a.started_at,
        deadline=a.deadline,
        submitted_at=a.submitted_at,
        timed_out=a.timed_out,
        server_time=utcnow(),
        remaining_seconds=svc.remaining_seconds(a) if a.status == AttemptStatus.IN_PROGRESS else 0,
        position=a.current_index,
        total_questions=len(a.items),
        question=svc.current_question(a),
        score=a.score,
        max_score=a.max_score,
        percent=_percent(a),
        feedback_status=a.feedback_status,
    )


def _raise(exc: svc.AttemptError):
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("", response_model=AttemptState, status_code=201)
def start(body: StartAttemptRequest, response: Response, ctx: _Ctx = Depends(), bank: QuestionBank = Depends(get_bank)):
    """Start a test. If one is already running for this test, it is resumed (200)."""
    ctx.close_expired()
    try:
        attempt, created = svc.start_attempt(ctx.db, bank, body.test_id, ctx.user.id)
    except svc.AttemptError as exc:
        _raise(exc)
    if not created:
        response.status_code = 200
    return _state(attempt)


@router.get("", response_model=list[AttemptListItem])
def list_attempts(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    ctx: _Ctx = Depends(),
):
    ctx.close_expired()
    query = select(Attempt).where(Attempt.user_id == ctx.user.id).order_by(Attempt.started_at.desc()).limit(limit)
    if status:
        query = query.where(Attempt.status == status)
    return [_list_item(a) for a in ctx.db.scalars(query).all()]


@router.get("/{attempt_id}", response_model=AttemptState)
def get_state(attempt_id: str, ctx: _Ctx = Depends()):
    attempt = ctx.attempt(attempt_id)
    ctx.enforce_deadline(attempt)
    return _state(attempt)


@router.post("/{attempt_id}/answer", response_model=AttemptState)
def answer(attempt_id: str, body: AnswerRequest, ctx: _Ctx = Depends()):
    attempt = ctx.attempt(attempt_id)
    try:
        finished = svc.submit_answer(ctx.db, attempt, body.position, body.answer)
    except svc.AttemptError as exc:
        if attempt.status == AttemptStatus.COMPLETED and attempt.feedback_status == FeedbackStatus.PENDING:
            ctx.queue_feedback(attempt)  # the deadline closed it during this request
        _raise(exc)
    if finished:
        ctx.queue_feedback(attempt)
    return _state(attempt)


@router.post("/{attempt_id}/run")
def run(attempt_id: str, body: RunCodeRequest, ctx: _Ctx = Depends()):
    attempt = ctx.attempt(attempt_id)
    try:
        return svc.run_code(ctx.db, attempt, body.position, body.code)
    except svc.AttemptError as exc:
        if attempt.status == AttemptStatus.COMPLETED and attempt.feedback_status == FeedbackStatus.PENDING:
            ctx.queue_feedback(attempt)
        _raise(exc)


@router.post("/{attempt_id}/finish", response_model=AttemptState)
def finish(attempt_id: str, ctx: _Ctx = Depends()):
    """Submit now; unanswered questions score zero."""
    attempt = ctx.attempt(attempt_id)
    try:
        svc.finish_attempt(ctx.db, attempt, timed_out=svc.is_expired(attempt))
    except svc.AttemptError as exc:
        _raise(exc)
    ctx.queue_feedback(attempt)
    return _state(attempt)


@router.post("/{attempt_id}/feedback/retry", response_model=AttemptState)
def retry_feedback(attempt_id: str, ctx: _Ctx = Depends()):
    attempt = ctx.attempt(attempt_id)
    if attempt.status != AttemptStatus.COMPLETED:
        raise HTTPException(409, "Finish the attempt first")
    if attempt.feedback_status != FeedbackStatus.FAILED:
        raise HTTPException(409, f"Feedback is {attempt.feedback_status}; only failed feedback can be retried")
    attempt.feedback_status = FeedbackStatus.PENDING
    attempt.feedback_error = None
    ctx.db.commit()
    ctx.queue_feedback(attempt)
    return _state(attempt)


@router.get("/{attempt_id}/review", response_model=AttemptReview)
def review(attempt_id: str, ctx: _Ctx = Depends()):
    attempt = ctx.attempt(attempt_id)
    ctx.enforce_deadline(attempt)
    if attempt.status != AttemptStatus.COMPLETED:
        raise HTTPException(409, "The review is available once the attempt is completed")

    cats: dict[str, list] = defaultdict(lambda: [0.0, 0.0, False])
    items: list[ReviewItem] = []
    previous = attempt.started_at
    for item in attempt.items:
        c = cats[item.category]
        c[0] += item.points or 0
        c[1] += item.max_points
        c[2] = c[2] or item.points is None
        spent = None
        if item.answered_at:
            spent = int((item.answered_at - previous).total_seconds())
            previous = item.answered_at
        items.append(
            ReviewItem(
                position=item.position,
                question=item.question,
                answer=item.answer,
                points=item.points,
                max_points=item.max_points,
                is_correct=item.is_correct,
                grading=item.grading,
                time_spent_seconds=spent,
            )
        )

    return AttemptReview(
        attempt=_list_item(attempt),
        duration_seconds=int((attempt.submitted_at - attempt.started_at).total_seconds())
        if attempt.submitted_at
        else None,
        categories=[
            CategoryScore(
                category=name,
                points=round(p, 2),
                max_points=m,
                percent=round(100 * p / m, 1) if m else 0,
                pending=pending,
            )
            for name, (p, m, pending) in cats.items()
        ],
        items=items,
        feedback=attempt.feedback,
        feedback_provider=attempt.feedback_provider,
        feedback_error=attempt.feedback_error,
    )
