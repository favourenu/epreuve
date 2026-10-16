from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Attempt, AttemptStatus, User
from app.question_bank import QuestionBank, TestDefinition, get_bank
from app.schemas import TestSummary

router = APIRouter(prefix="/api/tests", tags=["tests"])


def _summary(test: TestDefinition, attempts: list[Attempt]) -> TestSummary:
    percents = [round(100 * a.score / a.max_score, 1) for a in attempts if a.max_score]
    return TestSummary(
        id=test.id,
        title=test.title,
        description=test.description,
        skill_area=test.skill_area,
        time_limit_minutes=test.time_limit_minutes,
        question_count=test.question_count,
        instructions=test.instructions,
        attempts=len(attempts),
        best_percent=max(percents) if percents else None,
        last_percent=percents[-1] if percents else None,
    )


def _completed(db: Session, user_id: str) -> dict[str, list[Attempt]]:
    rows = db.scalars(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.status == AttemptStatus.COMPLETED)
        .order_by(Attempt.started_at)
    ).all()
    grouped: dict[str, list[Attempt]] = {}
    for a in rows:
        grouped.setdefault(a.test_id, []).append(a)
    return grouped


@router.get("", response_model=list[TestSummary])
def list_tests(
    db: Session = Depends(get_db),
    bank: QuestionBank = Depends(get_bank),
    user: User = Depends(get_current_user),
):
    completed = _completed(db, user.id)
    return [_summary(t, completed.get(t.id, [])) for t in bank.tests.values()]


@router.get("/{test_id}", response_model=TestSummary)
def get_test(
    test_id: str,
    db: Session = Depends(get_db),
    bank: QuestionBank = Depends(get_bank),
    user: User = Depends(get_current_user),
):
    test = bank.tests.get(test_id)
    if test is None:
        raise HTTPException(404, f"Unknown test '{test_id}'")
    return _summary(test, _completed(db, user.id).get(test_id, []))
