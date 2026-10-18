"""Company invitations: an admin invites a candidate to take one proctored assessment.

The candidate must use the invited email address, gets one attempt, and doesn't
see the results; the admin does.
"""

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Attempt, AttemptMode, AttemptStatus, Invite, User, utcnow
from app.question_bank import QuestionBank
from app.services.auth import _token_hash, normalize_email


class InviteError(Exception):
    status_code = 400


class InviteNotFound(InviteError):
    status_code = 404

    def __init__(self):
        super().__init__("This invitation link is invalid.")


class InviteConflict(InviteError):
    status_code = 409


def create(db: Session, bank: QuestionBank, admin: User, *, email: str, candidate_name: str, company: str,
           test_id: str, message: str | None, valid_days: int | None) -> tuple[Invite, str]:
    test = bank.tests.get(test_id)
    if test is None:
        raise InviteError(f"Unknown test '{test_id}'")
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token_hash=_token_hash(token),
        email=normalize_email(email),
        candidate_name=candidate_name.strip(),
        company=company.strip(),
        test_id=test.id,
        test_title=test.title,
        message=(message or "").strip() or None,
        created_by=admin.id,
        expires_at=utcnow() + timedelta(days=valid_days or get_settings().invite_valid_days),
    )
    db.add(invite)
    db.commit()
    return invite, token


def by_token(db: Session, token: str) -> Invite:
    invite = db.scalar(select(Invite).where(Invite.token_hash == _token_hash(token)))
    if invite is None:
        raise InviteNotFound()
    return invite


def attempt_for(db: Session, invite: Invite) -> Attempt | None:
    return db.scalar(select(Attempt).where(Attempt.invite_id == invite.id).order_by(Attempt.started_at.desc()))


def status(invite: Invite, attempt: Attempt | None) -> str:
    if attempt is not None:
        return "completed" if attempt.status == AttemptStatus.COMPLETED else "in_progress"
    if invite.cancelled_at:
        return "cancelled"
    if invite.expires_at < utcnow():
        return "expired"
    return "opened" if invite.opened_at else "sent"


def mark_opened(db: Session, invite: Invite) -> None:
    if invite.opened_at is None:
        invite.opened_at = utcnow()
        db.commit()


def start(db: Session, bank: QuestionBank, invite: Invite, user: User) -> tuple[Attempt, bool]:
    from app.services.attempts import start_attempt

    if user.email != invite.email:
        raise InviteConflict(
            f"This invitation was sent to {invite.email}. Log in with that email address to take the assessment."
        )
    existing = attempt_for(db, invite)
    if existing is not None and existing.status == AttemptStatus.COMPLETED:
        raise InviteConflict("You've already completed this assessment. Your results were sent to " + invite.company + ".")
    if existing is None:
        state = status(invite, None)
        if state == "cancelled":
            raise InviteConflict("This invitation has been withdrawn.")
        if state == "expired":
            raise InviteConflict(f"This invitation expired. Ask {invite.company} to send a new one.")
    mark_opened(db, invite)
    return start_attempt(db, bank, invite.test_id, user.id, mode=AttemptMode.INVITE, invite_id=invite.id)


def public_view(db: Session, bank: QuestionBank, invite: Invite) -> dict:
    test = bank.tests.get(invite.test_id)
    attempt = attempt_for(db, invite)
    return {
        "company": invite.company,
        "candidate_name": invite.candidate_name,
        "email": invite.email,
        "test_id": invite.test_id,
        "test_title": invite.test_title,
        "time_limit_minutes": test.time_limit_minutes if test else None,
        "question_count": test.question_count if test else None,
        "message": invite.message,
        "expires_at": invite.expires_at,
        "status": status(invite, attempt),
        "attempt_id": attempt.id if attempt else None,
    }
