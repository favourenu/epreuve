import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import auth
from app.services.email import EmailError, EmailSender, get_email_sender, password_reset_email

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)
    name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetTokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordRequest(ResetTokenRequest):
    password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)


FORGOT_REPLY = {"detail": "If an account exists for that email, we've sent a link to reset your password."}


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role)


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_days * 86400,
        httponly=True,
        secure=s.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _raise(exc: auth.AuthError):
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupRequest, response: Response, db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(422, "Please enter your name")
    try:
        user = auth.signup(db, body.email, body.password, body.name)
    except auth.AuthError as exc:
        _raise(exc)
    _set_cookie(response, auth.create_session(db, user, get_settings()))
    return _out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    try:
        user = auth.authenticate(db, body.email, body.password, client_ip)
    except auth.AuthError as exc:
        _raise(exc)
    _set_cookie(response, auth.create_session(db, user, get_settings()))
    return _out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    if token := request.cookies.get(s.session_cookie_name):
        auth.end_session(db, token)
    response.delete_cookie(s.session_cookie_name, path="/", httponly=True, samesite="lax", secure=s.session_cookie_secure)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _out(user)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _send_reset_email(sender: EmailSender, to: str, name: str, link: str, minutes: int) -> None:
    try:
        sender.send(password_reset_email(to, name, link, minutes))
    except EmailError:
        log.exception("Could not send password reset email")


@router.post("/password/forgot", status_code=202)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    """Email a reset link if the account exists. The reply is identical either way,
    so this can't be used to discover which emails are registered."""
    s = get_settings()
    try:
        found = auth.request_password_reset(db, body.email, _client_ip(request), s)
    except auth.AuthError as exc:
        _raise(exc)
    if found:
        user, token = found
        link = f"{s.app_base_url.rstrip('/')}/reset-password?token={token}"
        # Sent after the response, so response time doesn't reveal whether the account exists.
        background.add_task(_send_reset_email, sender, user.email, user.name, link, s.password_reset_minutes)
    return FORGOT_REPLY


@router.post("/password/reset/check")
def check_reset_token(body: ResetTokenRequest, db: Session = Depends(get_db)):
    """Lets the reset page say early if a link is invalid or expired."""
    try:
        user = auth.check_reset_token(db, body.token)
    except auth.AuthError as exc:
        _raise(exc)
    return {"email": user.email}


@router.post("/password/reset", response_model=UserOut)
def reset_password(body: ResetPasswordRequest, response: Response, db: Session = Depends(get_db)):
    """Set a new password, sign out every existing session, and sign in here."""
    try:
        user = auth.reset_password(db, body.token, body.password)
    except auth.AuthError as exc:
        _raise(exc)
    _set_cookie(response, auth.create_session(db, user, get_settings()))
    return _out(user)
