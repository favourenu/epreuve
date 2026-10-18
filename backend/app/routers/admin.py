"""Admin API: platform overview, users, attempts, leaderboards, certificates, invites."""

import csv
import io
from collections import defaultdict
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.deps import get_admin_user
from app.models import (
    Attempt,
    AttemptMode,
    AttemptStatus,
    Certificate,
    CertificateStatus,
    Invite,
    Role,
    User,
    UserSession,
    utcnow,
)
from app.question_bank import QuestionBank, get_bank
from app.routers.attempts import _list_item, _percent, build_review
from app.services import certification, integrity, invites
from app.services.email import EmailSender, get_email_sender, invite_email

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


def _pct(a: Attempt) -> float | None:
    return _percent(a)


def _user_row(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "disabled": u.disabled_at is not None,
        "created_at": u.created_at,
    }


def _attempt_row(a: Attempt, summary: integrity.IntegritySummary | None) -> dict:
    return {
        **_list_item(a, as_admin=True).model_dump(),
        "user": {"id": a.user.id, "name": a.user.name, "email": a.user.email},
        "risk": summary.risk if summary and a.mode in AttemptMode.PROCTORED else None,
    }


# ---------------------------------------------------------------- overview


@router.get("/overview")
def overview(db: Session = Depends(get_db), bank: QuestionBank = Depends(get_bank)):
    now = utcnow()
    week = now - timedelta(days=7)
    count = lambda q: db.scalar(q) or 0  # noqa: E731

    days = 14
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = {(start + timedelta(days=i)).date().isoformat(): {"started": 0, "completed": 0} for i in range(days)}
    recent = db.execute(select(Attempt.started_at, Attempt.status).where(Attempt.started_at >= start)).all()
    for started_at, status in recent:
        day = started_at.date().isoformat()
        if day in daily:
            daily[day]["started"] += 1
            daily[day]["completed"] += status == AttemptStatus.COMPLETED

    by_test: dict[str, list[float]] = defaultdict(list)
    for a in db.scalars(select(Attempt).where(Attempt.status == AttemptStatus.COMPLETED)):
        if (p := _pct(a)) is not None:
            by_test[a.test_id].append(p)

    open_invites = 0
    for inv in db.scalars(select(Invite)):
        if invites.status(inv, invites.attempt_for(db, inv)) in ("sent", "opened", "in_progress"):
            open_invites += 1

    return {
        "users_total": count(select(func.count(User.id))),
        "users_new_7d": count(select(func.count(User.id)).where(User.created_at >= week)),
        "users_active_7d": count(select(func.count(func.distinct(Attempt.user_id))).where(Attempt.started_at >= week)),
        "attempts_total": count(select(func.count(Attempt.id))),
        "attempts_completed_7d": count(
            select(func.count(Attempt.id)).where(Attempt.status == AttemptStatus.COMPLETED, Attempt.submitted_at >= week)
        ),
        # Still within their time limit; abandoned attempts are closed lazily, so exclude expired ones.
        "attempts_in_progress": count(
            select(func.count(Attempt.id)).where(Attempt.status == AttemptStatus.IN_PROGRESS, Attempt.deadline > now)
        ),
        "certificates_issued": count(select(func.count(Certificate.id)).where(Certificate.status == CertificateStatus.ISSUED)),
        "certificates_pending_review": count(
            select(func.count(Certificate.id)).where(Certificate.status == CertificateStatus.UNDER_REVIEW)
        ),
        "invites_open": open_invites,
        "daily": [{"date": d, **v} for d, v in daily.items()],
        "by_test": sorted(
            (
                {
                    "test_id": tid,
                    "title": bank.tests[tid].title if tid in bank.tests else tid,
                    "attempts": len(ps),
                    "average_percent": round(sum(ps) / len(ps), 1),
                }
                for tid, ps in by_test.items()
            ),
            key=lambda r: -r["attempts"],
        ),
    }


# ---------------------------------------------------------------- users


@router.get("/users")
def list_users(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(User)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(User.email).like(like), func.lower(User.name).like(like)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    users = db.scalars(query.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()

    ids = [u.id for u in users]
    stats: dict[str, dict] = {i: {"completed": 0, "percents": [], "last_active": None} for i in ids}
    if ids:
        for a in db.scalars(select(Attempt).where(Attempt.user_id.in_(ids))):
            s = stats[a.user_id]
            s["last_active"] = max(filter(None, [s["last_active"], a.submitted_at or a.started_at]))
            if a.status == AttemptStatus.COMPLETED:
                s["completed"] += 1
                if (p := _pct(a)) is not None:
                    s["percents"].append(p)
    cert_counts = dict(
        db.execute(
            select(Certificate.user_id, func.count())
            .where(Certificate.user_id.in_(ids), Certificate.status == CertificateStatus.ISSUED)
            .group_by(Certificate.user_id)
        ).all()
    ) if ids else {}

    rows = []
    for u in users:
        s = stats[u.id]
        rows.append({
            **_user_row(u),
            "attempts_completed": s["completed"],
            "average_percent": round(sum(s["percents"]) / len(s["percents"]), 1) if s["percents"] else None,
            "certificates": cert_counts.get(u.id, 0),
            "last_active": s["last_active"],
        })
    return {"total": total, "users": rows}


@router.get("/users/{user_id}")
def user_detail(user_id: str, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user_id).order_by(Attempt.started_at.desc())).all()
    summaries = integrity.summaries_for(db, [a.id for a in attempts if a.mode in AttemptMode.PROCTORED])
    certs = db.scalars(select(Certificate).where(Certificate.user_id == user_id).order_by(Certificate.created_at.desc()))
    return {
        "user": _user_row(user),
        "attempts": [_attempt_row(a, summaries.get(a.id)) for a in attempts],
        "certificates": [certification.certificate_out(c) for c in certs],
    }


class UserUpdate(BaseModel):
    role: Literal["user", "admin"] | None = None
    disabled: bool | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(409, "You can't change your own role or suspend yourself.")
    if body.role is not None:
        user.role = Role.ADMIN if body.role == "admin" else Role.USER
    if body.disabled is not None:
        user.disabled_at = utcnow() if body.disabled else None
        if body.disabled:  # sign them out everywhere now
            db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return _user_row(user)


# ---------------------------------------------------------------- attempts


@router.get("/attempts")
def list_attempts(
    mode: Literal["practice", "certification", "invite"] | None = None,
    status: Literal["in_progress", "completed"] | None = None,
    test_id: str | None = None,
    risk: Literal["high"] | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(Attempt)
    if mode:
        query = query.where(Attempt.mode == mode)
    if status:
        query = query.where(Attempt.status == status)
    if test_id:
        query = query.where(Attempt.test_id == test_id)
    if risk:
        query = query.where(Attempt.mode.in_(AttemptMode.PROCTORED))
    attempts = db.scalars(query.order_by(Attempt.started_at.desc())).all()
    summaries = integrity.summaries_for(db, [a.id for a in attempts if a.mode in AttemptMode.PROCTORED])
    if risk:
        attempts = [a for a in attempts if summaries[a.id].risk == risk]
    page = attempts[offset : offset + limit]
    return {"total": len(attempts), "attempts": [_attempt_row(a, summaries.get(a.id)) for a in page]}


@router.get("/attempts/{attempt_id}")
def attempt_detail(attempt_id: str, db: Session = Depends(get_db)):
    attempt = db.scalar(select(Attempt).where(Attempt.id == attempt_id).options(selectinload(Attempt.items)))
    if attempt is None:
        raise HTTPException(404, "Attempt not found")
    events = integrity.events_for(db, attempt.id)
    review = build_review(db, attempt, as_admin=True).model_dump() if attempt.status == AttemptStatus.COMPLETED else None
    return {
        "attempt": _attempt_row(attempt, integrity.summarize(events)),
        "review": review,
        "progress": {"position": attempt.current_index, "total": len(attempt.items)},
        "integrity": integrity.summarize(events).public() if attempt.mode in AttemptMode.PROCTORED else None,
        "events": [
            {"kind": e.kind, "label": integrity.LABELS.get(e.kind, e.kind), "occurred_at": e.occurred_at,
             "duration_ms": e.duration_ms, "detail": e.detail}
            for e in events
        ],
        "invite": {"company": attempt.invite.company, "email": attempt.invite.email} if attempt.invite else None,
    }


# ---------------------------------------------------------------- leaderboard


@router.get("/leaderboard")
def leaderboard(
    test_id: str | None = None,
    period: Literal["7d", "30d", "all"] = "all",
    mode: Literal["all", "certification"] = "all",
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Best score per user (for one test) or average of each user's best per test (overall).
    Invited attempts are excluded: they belong to the company that sent them."""
    query = select(Attempt).where(Attempt.status == AttemptStatus.COMPLETED, Attempt.mode != AttemptMode.INVITE)
    if test_id:
        query = query.where(Attempt.test_id == test_id)
    if mode == "certification":
        query = query.where(Attempt.mode == AttemptMode.CERTIFICATION)
    if period != "all":
        query = query.where(Attempt.submitted_at >= utcnow() - timedelta(days=7 if period == "7d" else 30))

    best: dict[str, dict[str, float]] = defaultdict(dict)  # user -> test -> best %
    attempts_count: dict[str, int] = defaultdict(int)
    users: dict[str, User] = {}
    for a in db.scalars(query):
        if (p := _pct(a)) is None:
            continue
        users[a.user_id] = a.user
        attempts_count[a.user_id] += 1
        best[a.user_id][a.test_id] = max(p, best[a.user_id].get(a.test_id, 0))

    rows = []
    for uid, per_test in best.items():
        score = per_test[test_id] if test_id else sum(per_test.values()) / len(per_test)
        rows.append({
            "user": {"id": uid, "name": users[uid].name, "email": users[uid].email},
            "score": round(score, 1),
            "tests_taken": len(per_test),
            "attempts": attempts_count[uid],
        })
    rows.sort(key=lambda r: (-r["score"], -r["tests_taken"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows[:limit]


# ---------------------------------------------------------------- certificates


@router.get("/certificates")
def list_certificates(
    status: Literal["issued", "under_review", "rejected", "revoked"] | None = None,
    db: Session = Depends(get_db),
):
    query = select(Certificate).order_by(Certificate.created_at.desc())
    if status:
        query = query.where(Certificate.status == status)
    certs = db.scalars(query).all()
    summaries = integrity.summaries_for(db, [c.attempt_id for c in certs])
    return [
        {
            **certification.certificate_out(c),
            "user": {"id": c.user.id, "name": c.user.name, "email": c.user.email},
            "integrity": summaries[c.attempt_id].public(),
        }
        for c in certs
    ]


class CertificateReview(BaseModel):
    action: Literal["approve", "reject", "revoke", "reinstate"]
    note: str | None = Field(default=None, max_length=1000)


@router.post("/certificates/{cert_id}/review")
def review_certificate(cert_id: str, body: CertificateReview, db: Session = Depends(get_db),
                       admin: User = Depends(get_admin_user)):
    cert = db.get(Certificate, cert_id)
    if cert is None:
        raise HTTPException(404, "Certificate not found")
    try:
        cert = certification.review(db, cert, body.action, admin, body.note)
    except certification.ReviewError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return certification.certificate_out(cert)


# ---------------------------------------------------------------- invites


def _invite_row(db: Session, inv: Invite) -> dict:
    attempt = invites.attempt_for(db, inv)
    summary = integrity.summarize(integrity.events_for(db, attempt.id)) if attempt else None
    done = attempt is not None and attempt.status == AttemptStatus.COMPLETED
    return {
        "id": inv.id,
        "email": inv.email,
        "candidate_name": inv.candidate_name,
        "company": inv.company,
        "test_id": inv.test_id,
        "test_title": inv.test_title,
        "message": inv.message,
        "created_at": inv.created_at,
        "expires_at": inv.expires_at,
        "status": invites.status(inv, attempt),
        "attempt_id": attempt.id if attempt else None,
        "percent": _pct(attempt) if done else None,
        "submitted_at": attempt.submitted_at if attempt else None,
        "risk": summary.risk if summary else None,
    }


@router.get("/invites")
def list_invites(company: str | None = None, db: Session = Depends(get_db)):
    query = select(Invite).order_by(Invite.created_at.desc())
    if company:
        query = query.where(func.lower(Invite.company) == company.strip().lower())
    return [_invite_row(db, inv) for inv in db.scalars(query)]


class InviteCreate(BaseModel):
    email: EmailStr
    candidate_name: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=120)
    test_id: str
    message: str | None = Field(default=None, max_length=1000)
    valid_days: int | None = Field(default=None, ge=1, le=90)


def _send_invite(sender: EmailSender, email) -> None:
    import logging

    from app.services.email import EmailError

    try:
        sender.send(email)
    except EmailError:
        logging.getLogger(__name__).exception("Could not send invite email")


@router.post("/invites", status_code=201)
def create_invite(body: InviteCreate, background: BackgroundTasks, db: Session = Depends(get_db),
                  bank: QuestionBank = Depends(get_bank), admin: User = Depends(get_admin_user),
                  sender: EmailSender = Depends(get_email_sender)):
    try:
        inv, token = invites.create(
            db, bank, admin, email=body.email, candidate_name=body.candidate_name, company=body.company,
            test_id=body.test_id, message=body.message, valid_days=body.valid_days,
        )
    except invites.InviteError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    link = f"{get_settings().app_base_url.rstrip('/')}/invite/{token}"
    test = bank.tests[inv.test_id]
    background.add_task(_send_invite, sender, invite_email(
        inv.email, inv.candidate_name, inv.company, inv.test_title, test.time_limit_minutes, link,
        f"{inv.expires_at:%d %B %Y}", inv.message,
    ))
    # The link is returned once so it can also be shared another way; only its hash is stored.
    return {**_invite_row(db, inv), "link": link}


@router.post("/invites/{invite_id}/cancel")
def cancel_invite(invite_id: str, db: Session = Depends(get_db)):
    inv = db.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404, "Invite not found")
    if invites.attempt_for(db, inv) is not None:
        raise HTTPException(409, "The candidate has already started this assessment.")
    inv.cancelled_at = inv.cancelled_at or utcnow()
    db.commit()
    return _invite_row(db, inv)


@router.get("/invites.csv")
def export_invites(company: str | None = None, db: Session = Depends(get_db)):
    """Candidate results as a spreadsheet, e.g. to send to the hiring company."""
    rows = list_invites(company, db)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Candidate", "Email", "Company", "Assessment", "Status", "Score %", "Integrity risk", "Submitted (UTC)", "Invited (UTC)"])
    for r in rows:
        w.writerow([
            r["candidate_name"], r["email"], r["company"], r["test_title"], r["status"],
            "" if r["percent"] is None else r["percent"], r["risk"] or "",
            f"{r['submitted_at']:%Y-%m-%d %H:%M}" if r["submitted_at"] else "", f"{r['created_at']:%Y-%m-%d %H:%M}",
        ])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="epreuve-candidates.csv"'},
    )
