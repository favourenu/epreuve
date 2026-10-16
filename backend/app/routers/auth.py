from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)
    name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: str
    email: str
    name: str


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name)


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
