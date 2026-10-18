"""Confirming an email address with a 6-digit code.

New accounts get a code by email and can't use the platform until they enter
it. Only an HMAC of each code is stored. Brute force is bounded: each code allows
a few wrong guesses, lasts minutes, and only so many codes are sent per day.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailVerificationCode, User, utcnow
from app.services.auth import AuthError, TooManyAttempts, secret_key, sync_admin_role


class InvalidCode(AuthError):
    status_code = 400


def _hash(user: User, code: str) -> str:
    return hmac.new(secret_key(), f"verify:{user.id}:{code}".encode(), hashlib.sha256).hexdigest()


def _latest(db: Session, user: User) -> EmailVerificationCode | None:
    return db.scalar(
        select(EmailVerificationCode)
        .where(EmailVerificationCode.user_id == user.id, EmailVerificationCode.used_at.is_(None))
        .order_by(EmailVerificationCode.created_at.desc(), EmailVerificationCode.id.desc())
        .limit(1)
    )


def resend_wait_seconds(db: Session, user: User) -> int:
    """Seconds until another code may be sent (0 = now)."""
    latest = _latest(db, user)
    if latest is None:
        return 0
    ready = latest.created_at + timedelta(seconds=get_settings().email_code_resend_seconds)
    return max(0, int((ready - utcnow()).total_seconds() + 0.999))


def has_usable_code(db: Session, user: User) -> bool:
    latest = _latest(db, user)
    s = get_settings()
    return bool(latest and latest.expires_at > utcnow() and latest.failed_attempts < s.email_code_max_attempts)


def issue(db: Session, user: User) -> str:
    """Create a new code (replacing any older one) and return it for emailing."""
    s = get_settings()
    if wait := resend_wait_seconds(db, user):
        raise TooManyAttempts(f"Please wait {wait} seconds before requesting another code.")
    sent_today = db.scalar(
        select(func.count(EmailVerificationCode.id)).where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.created_at > utcnow() - timedelta(days=1),
        )
    )
    if sent_today >= s.email_code_max_per_day:
        raise TooManyAttempts("Too many codes requested today. Try again tomorrow, or contact support.")
    # Older codes stop working, but are kept (as used) so the daily count stays honest.
    db.query(EmailVerificationCode).filter(
        EmailVerificationCode.user_id == user.id, EmailVerificationCode.used_at.is_(None)
    ).update({EmailVerificationCode.used_at: utcnow()})
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        EmailVerificationCode(
            user_id=user.id,
            code_hash=_hash(user, code),
            expires_at=utcnow() + timedelta(minutes=s.email_code_minutes),
        )
    )
    db.commit()
    return code


def verify(db: Session, user: User, code: str) -> User:
    if user.email_verified:
        return user
    s = get_settings()
    code = "".join(ch for ch in code if ch.isdigit())
    latest = _latest(db, user)
    if latest is None or latest.expires_at <= utcnow():
        raise InvalidCode("This code has expired. Send a new one.")
    if latest.failed_attempts >= s.email_code_max_attempts:
        raise TooManyAttempts("Too many incorrect codes. Send a new one.")
    if len(code) != 6 or not hmac.compare_digest(latest.code_hash, _hash(user, code)):
        latest.failed_attempts += 1
        db.commit()
        left = s.email_code_max_attempts - latest.failed_attempts
        if left <= 0:
            raise TooManyAttempts("Too many incorrect codes. Send a new one.")
        raise InvalidCode(f"That code isn't right. {left} {'try' if left == 1 else 'tries'} left.")
    mark_verified(db, user)
    return user


def mark_verified(db: Session, user: User) -> None:
    """Confirm the address (also used after a password reset, which proves the same)."""
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.execute(delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id))
    db.commit()
    sync_admin_role(db, user)
