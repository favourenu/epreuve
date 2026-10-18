from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.question_bank import QuestionBank, get_bank
from app.routers.attempts import _Ctx, _state
from app.schemas import AttemptState
from app.services import invites
from app.services.attempts import AttemptError

router = APIRouter(prefix="/api/invites", tags=["invites"])


class StartInviteRequest(BaseModel):
    agree_to_rules: bool = False


def _raise(exc: invites.InviteError):
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/{token}")
def view_invite(token: str, db: Session = Depends(get_db), bank: QuestionBank = Depends(get_bank)):
    """The invitation page. Public: the token itself is the credential."""
    try:
        invite = invites.by_token(db, token)
    except invites.InviteError as exc:
        _raise(exc)
    invites.mark_opened(db, invite)
    return invites.public_view(db, bank, invite)


@router.post("/{token}/start", response_model=AttemptState, status_code=201)
def start_invite(token: str, body: StartInviteRequest, response: Response, ctx: _Ctx = Depends(),
                 bank: QuestionBank = Depends(get_bank)):
    if not body.agree_to_rules:
        raise HTTPException(400, "Please confirm the assessment rules before starting.")
    ctx.close_expired()
    try:
        invite = invites.by_token(ctx.db, token)
        attempt, created = invites.start(ctx.db, bank, invite, ctx.user)
    except (invites.InviteError, AttemptError) as exc:  # AttemptError: e.g. another attempt running
        raise HTTPException(exc.status_code, str(exc)) from exc
    if not created:
        response.status_code = 200
    return _state(attempt)
