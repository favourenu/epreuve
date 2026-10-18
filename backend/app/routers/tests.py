from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Attempt, AttemptMode, AttemptStatus, Certificate, CertificateStatus, User
from app.question_bank import QuestionBank, TestDefinition, get_bank
from app.schemas import CertificateOut, TestSummary
from app.services.certification import certificate_out, next_certification_at

router = APIRouter(prefix="/api/tests", tags=["tests"])

# Which certificate to show when a user holds several for one test.
_CERT_RANK = {CertificateStatus.ISSUED: 0, CertificateStatus.UNDER_REVIEW: 1}


def _summary(db: Session, user: User, test: TestDefinition, attempts: list[Attempt], certs: list[Certificate]) -> TestSummary:
    s = get_settings()
    percents = [round(100 * a.score / a.max_score, 1) for a in attempts if a.max_score]
    shown = sorted(
        (c for c in certs if c.status in _CERT_RANK), key=lambda c: (_CERT_RANK[c.status], -c.percent)
    )
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
        certification_pass_percent=s.certification_pass_percent,
        certification_distinction_percent=s.certification_distinction_percent,
        certification_cooldown_days=s.certification_cooldown_days,
        certification_available_at=next_certification_at(db, user.id, test.id),
        certificate=CertificateOut(**certificate_out(shown[0])) if shown else None,
    )


def _completed(db: Session, user_id: str) -> dict[str, list[Attempt]]:
    """The user's own completed attempts (invited ones belong to the inviting company)."""
    rows = db.scalars(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.status == AttemptStatus.COMPLETED, Attempt.mode != AttemptMode.INVITE)
        .order_by(Attempt.started_at)
    ).all()
    grouped: dict[str, list[Attempt]] = {}
    for a in rows:
        grouped.setdefault(a.test_id, []).append(a)
    return grouped


def _certificates(db: Session, user_id: str) -> dict[str, list[Certificate]]:
    grouped: dict[str, list[Certificate]] = {}
    for c in db.scalars(select(Certificate).where(Certificate.user_id == user_id)):
        grouped.setdefault(c.test_id, []).append(c)
    return grouped


@router.get("", response_model=list[TestSummary])
def list_tests(
    db: Session = Depends(get_db),
    bank: QuestionBank = Depends(get_bank),
    user: User = Depends(get_current_user),
):
    completed, certs = _completed(db, user.id), _certificates(db, user.id)
    return [_summary(db, user, t, completed.get(t.id, []), certs.get(t.id, [])) for t in bank.tests.values()]


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
    return _summary(db, user, test, _completed(db, user.id).get(test_id, []), _certificates(db, user.id).get(test_id, []))
