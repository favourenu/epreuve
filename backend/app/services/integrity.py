"""Integrity monitoring for proctored attempts (certification and company invites).

The browser reports what it can observe: leaving the test window, leaving full
screen, a second screen, pasting. None of this proves cheating on its own, so
events become a risk level that decides whether a certificate is issued
automatically or goes to an admin for review.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Attempt, AttemptMode, AttemptStatus, IntegrityEvent, utcnow

EventKind = Literal[
    "focus_lost",  # tab hidden or window lost focus; duration_ms = time away
    "fullscreen_exit",
    "multiple_screens",
    "paste",
    "copy",
    "context_menu",
    "reload",  # the test page was loaded again mid-attempt
]

MAX_EVENTS_PER_ATTEMPT = 1000

LABELS = {
    "focus_lost": "Left the test window",
    "fullscreen_exit": "Exited full screen",
    "multiple_screens": "Second screen detected",
    "paste": "Pasted text",
    "copy": "Copied text",
    "context_menu": "Opened the right-click menu",
    "reload": "Reloaded the test page",
}


class EventIn(BaseModel):
    kind: EventKind
    duration_ms: int | None = Field(default=None, ge=0, le=6 * 3600 * 1000)
    detail: str | None = Field(default=None, max_length=200)


class EventsIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=50)


class IntegrityConflict(Exception):
    status_code = 409


@dataclass
class IntegritySummary:
    risk: Literal["none", "low", "high"]
    counts: dict[str, int] = field(default_factory=dict)
    seconds_away: int = 0
    reasons: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return {"risk": self.risk, "counts": self.counts, "seconds_away": self.seconds_away, "reasons": self.reasons}


def record_events(db: Session, attempt: Attempt, events: list[EventIn]) -> int:
    """Store events for a proctored, in-progress attempt. Returns how many were kept."""
    if attempt.mode not in AttemptMode.PROCTORED:
        raise IntegrityConflict("Integrity events are only recorded for proctored attempts")
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise IntegrityConflict("This attempt is already completed")
    stored = db.scalar(select(func.count()).select_from(IntegrityEvent).where(IntegrityEvent.attempt_id == attempt.id))
    room = max(0, MAX_EVENTS_PER_ATTEMPT - (stored or 0))
    now = utcnow()
    for e in events[:room]:
        db.add(IntegrityEvent(attempt_id=attempt.id, kind=e.kind, occurred_at=now, duration_ms=e.duration_ms, detail=e.detail))
    db.commit()
    return min(len(events), room)


def summarize(events: list[IntegrityEvent]) -> IntegritySummary:
    counts = Counter(e.kind for e in events)
    away_ms = sum(e.duration_ms or 0 for e in events if e.kind == "focus_lost")
    seconds_away = round(away_ms / 1000)

    reasons: list[str] = []
    if counts["multiple_screens"]:
        reasons.append("A second screen was connected")
    if seconds_away >= 60:
        reasons.append(f"Spent {seconds_away} seconds outside the test window")
    if counts["focus_lost"] >= 5:
        reasons.append(f"Left the test window {counts['focus_lost']} times")
    if counts["paste"] >= 3:
        reasons.append(f"Pasted text {counts['paste']} times")
    if counts["fullscreen_exit"] >= 5:
        reasons.append(f"Exited full screen {counts['fullscreen_exit']} times")
    if counts["reload"] >= 3:
        reasons.append(f"Reloaded the test page {counts['reload']} times")

    if reasons:
        risk = "high"
    elif events:
        risk = "low"
    else:
        risk = "none"
    return IntegritySummary(risk=risk, counts=dict(counts), seconds_away=seconds_away, reasons=reasons)


def events_for(db: Session, attempt_id: str) -> list[IntegrityEvent]:
    return list(db.scalars(select(IntegrityEvent).where(IntegrityEvent.attempt_id == attempt_id).order_by(IntegrityEvent.id)))


def summaries_for(db: Session, attempt_ids: list[str]) -> dict[str, IntegritySummary]:
    """Summaries for many attempts in one query."""
    grouped: dict[str, list[IntegrityEvent]] = {a: [] for a in attempt_ids}
    if attempt_ids:
        for e in db.scalars(select(IntegrityEvent).where(IntegrityEvent.attempt_id.in_(attempt_ids))):
            grouped[e.attempt_id].append(e)
    return {a: summarize(evts) for a, evts in grouped.items()}
