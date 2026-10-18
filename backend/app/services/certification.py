"""Certificates: earned by scoring highly on a proctored certification attempt.

A certificate is decided once an attempt's score is final (written answers can
need AI grading first). A clean or low-risk integrity report issues it straight
away; a high-risk one puts it in the admin review queue instead.
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Attempt, AttemptMode, AttemptStatus, Certificate, CertificateStatus, User, utcnow
from app.services import integrity

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I lookalikes


def new_code(db: Session) -> str:
    while True:
        part = lambda: "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))  # noqa: E731
        code = f"EPR-{part()}-{part()}"
        if not db.scalar(select(Certificate.id).where(Certificate.code == code)):
            return code


def normalize_code(code: str) -> str:
    return code.strip().upper()


def level_for(percent: float) -> str | None:
    s = get_settings()
    if percent >= s.certification_distinction_percent:
        return "distinction"
    if percent >= s.certification_pass_percent:
        return "pass"
    return None


def next_certification_at(db: Session, user_id: str, test_id: str) -> datetime | None:
    """When the user may next take a certification attempt at this test (None = now)."""
    last = db.scalar(
        select(Attempt.started_at)
        .where(Attempt.user_id == user_id, Attempt.test_id == test_id, Attempt.mode == AttemptMode.CERTIFICATION)
        .order_by(Attempt.started_at.desc())
        .limit(1)
    )
    if last is None:
        return None
    available = last + timedelta(days=get_settings().certification_cooldown_days)
    return available if available > utcnow() else None


def evaluate(db: Session, attempt: Attempt) -> Certificate | None:
    """Create a certificate for a finished certification attempt, if it earned one.

    Safe to call more than once: it does nothing until the score is final, and
    never creates a second certificate for the same attempt.
    """
    if attempt.mode != AttemptMode.CERTIFICATION or attempt.status != AttemptStatus.COMPLETED:
        return None
    if any(i.points is None for i in attempt.items) or not attempt.max_score:
        return None  # written answers still waiting for AI grading
    if db.scalar(select(Certificate.id).where(Certificate.attempt_id == attempt.id)):
        return None
    percent = round(100 * (attempt.score or 0) / attempt.max_score, 1)
    level = level_for(percent)
    if level is None:
        return None

    summary = integrity.summarize(integrity.events_for(db, attempt.id))
    flagged = summary.risk == "high"
    cert = Certificate(
        code=new_code(db),
        user_id=attempt.user_id,
        attempt_id=attempt.id,
        test_id=attempt.test_id,
        test_title=attempt.test_title,
        percent=percent,
        level=level,
        status=CertificateStatus.UNDER_REVIEW if flagged else CertificateStatus.ISSUED,
        issued_at=None if flagged else utcnow(),
    )
    db.add(cert)
    db.commit()
    return cert


def certificate_out(c: Certificate) -> dict:
    """The owner's (and admins') view of a certificate."""
    return {
        "id": c.id,
        "code": c.code,
        "test_id": c.test_id,
        "test_title": c.test_title,
        "percent": c.percent,
        "level": c.level,
        "status": c.status,
        "attempt_id": c.attempt_id,
        "created_at": c.created_at,
        "issued_at": c.issued_at,
        "review_note": c.review_note,
    }


def public_view(db: Session, code: str) -> dict | None:
    """What anyone with the code can see. Only issued or revoked certificates are public."""
    cert = db.scalar(select(Certificate).where(Certificate.code == normalize_code(code)))
    if cert is None or cert.status not in (CertificateStatus.ISSUED, CertificateStatus.REVOKED):
        return None
    holder = db.get(User, cert.user_id)
    return {
        "code": cert.code,
        "holder_name": holder.name if holder else "Former user",
        "test_title": cert.test_title,
        "level": cert.level,
        "percent": round(cert.percent),
        "issued_at": cert.issued_at,
        "valid": cert.status == CertificateStatus.ISSUED,
        "proctored": True,
    }


class ReviewError(Exception):
    status_code = 409


def review(db: Session, cert: Certificate, action: str, admin: User, note: str | None) -> Certificate:
    allowed = {
        "approve": (CertificateStatus.UNDER_REVIEW, CertificateStatus.REJECTED),
        "reject": (CertificateStatus.UNDER_REVIEW,),
        "revoke": (CertificateStatus.ISSUED,),
        "reinstate": (CertificateStatus.REVOKED,),
    }
    if action not in allowed:
        raise ReviewError(f"Unknown action '{action}'")
    if cert.status not in allowed[action]:
        raise ReviewError(f"Can't {action} a certificate that is {cert.status.replace('_', ' ')}")
    if action in ("approve", "reinstate"):
        cert.status = CertificateStatus.ISSUED
        cert.issued_at = cert.issued_at or utcnow()
    elif action == "reject":
        cert.status = CertificateStatus.REJECTED
    else:
        cert.status = CertificateStatus.REVOKED
    cert.reviewed_by = admin.id
    cert.review_note = (note or "").strip() or None
    db.commit()
    return cert
