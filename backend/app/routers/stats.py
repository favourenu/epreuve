from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_ai_service, get_current_user
from app.models import Attempt, AttemptMode, AttemptStatus, User
from app.routers.attempts import _list_item
from app.schemas import AIStatus, CategoryStat, StatsResponse
from app.services.ai.service import AIService

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempts = db.scalars(
        select(Attempt)
        # Invited attempts belong to the inviting company, not the candidate's own stats.
        .where(Attempt.user_id == user.id, Attempt.status == AttemptStatus.COMPLETED, Attempt.mode != AttemptMode.INVITE)
        .order_by(Attempt.started_at)
        .options(selectinload(Attempt.items))
    ).all()

    cats: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for a in attempts:
        for item in a.items:
            if item.points is None:  # still awaiting AI grading
                continue
            c = cats[item.category]
            c[0] += 1
            c[1] += item.points
            c[2] += item.max_points

    history = [_list_item(a) for a in attempts]
    percents = [h.percent for h in history if h.percent is not None]
    return StatsResponse(
        completed_attempts=len(attempts),
        average_percent=round(sum(percents) / len(percents), 1) if percents else None,
        categories=sorted(
            (
                CategoryStat(
                    category=name,
                    questions=int(n),
                    points=round(p, 2),
                    max_points=m,
                    percent=round(100 * p / m, 1) if m else 0,
                )
                for name, (n, p, m) in cats.items()
            ),
            key=lambda s: s.percent,
        ),
        history=history,
    )


@router.get("/ai/status", response_model=AIStatus)
def ai_status(ai: AIService = Depends(get_ai_service), _user: User = Depends(get_current_user)):
    return AIStatus(
        providers=[{"name": p.name, "model": getattr(p, "model", "")} for p in ai.providers]
    )
