"""Practice attempt limits: a rolling 24-hour allowance per user.

Each finished attempt costs one AI request, and free AI tiers allow only so many
per day for the whole site, so practice is rationed. Certification has its own
cooldown, company invites are never limited, and admins can change any user's
allowance (or make it unlimited).
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UNLIMITED, Attempt, AttemptMode, User, utcnow

WINDOW = timedelta(hours=24)


def effective_limit(user: User) -> int | None:
    """Practice attempts allowed per 24 hours; None means unlimited."""
    if user.is_admin or user.attempt_limit == UNLIMITED:
        return None
    if user.attempt_limit is None:
        return get_settings().practice_daily_limit
    return max(0, user.attempt_limit)


def quota(db: Session, user: User) -> dict:
    limit = effective_limit(user)
    since = utcnow() - WINDOW
    started = list(db.scalars(
        select(Attempt.started_at)
        .where(Attempt.user_id == user.id, Attempt.mode == AttemptMode.PRACTICE, Attempt.started_at > since)
        .order_by(Attempt.started_at)
    ))
    used = len(started)
    resets_at: datetime | None = None
    if limit is not None and used >= limit and started:
        # The next slot frees up when the oldest attempt that counts leaves the window.
        resets_at = started[used - limit] + WINDOW if limit > 0 else None
    return {
        "limit": limit,
        "used": used,
        "remaining": None if limit is None else max(0, limit - used),
        "resets_at": resets_at,
        "custom": user.attempt_limit is not None,
    }
