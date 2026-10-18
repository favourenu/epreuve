import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import EmailVerificationCode, User, utcnow
from tests.conftest import PASSWORD, latest_code


def new_email():
    return f"new-{uuid.uuid4().hex[:8]}@example.com"


def signup(c, email):
    r = c.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "name": "Ngozi Okafor"})
    assert r.status_code == 201, r.text
    return r.json()


def verify(c, code):
    return c.post("/api/auth/email/verify", json={"code": code})


def age_codes(email, **delta):
    """Move this user's codes into the past (to pass cooldowns or expire them)."""
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).one()
        for code in db.query(EmailVerificationCode).filter_by(user_id=user.id):
            code.created_at -= timedelta(**delta)
            code.expires_at -= timedelta(**delta)
        db.commit()


def test_signup_needs_the_emailed_code_before_anything_else(anon, outbox):
    email = new_email()
    me = signup(anon, email)
    assert me["email_verified"] is False
    mail = outbox.sent[-1]
    code = latest_code(outbox, email)
    assert mail.to == email and code in mail.text and code in mail.html

    assert anon.get("/api/auth/me").status_code == 200  # signed in...
    blocked = anon.get("/api/stats")
    assert blocked.status_code == 403 and "confirm your email" in blocked.json()["detail"]  # ...but nothing else

    wrong = "000000" if code != "000000" else "111111"
    r = verify(anon, wrong)
    assert r.status_code == 400 and "4 tries left" in r.json()["detail"]

    r = verify(anon, f" {code[:3]} {code[3:]} ")  # spaces are forgiven
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert anon.get("/api/stats").status_code == 200
    assert verify(anon, code).status_code == 200  # confirming again is harmless


def test_codes_are_stored_hashed(anon, outbox):
    email = new_email()
    signup(anon, email)
    code = latest_code(outbox, email)
    with SessionLocal() as db:
        stored = db.query(EmailVerificationCode).all()
        assert stored and all(code not in row.code_hash for row in stored)


def test_too_many_wrong_codes_lock_that_code(anon, outbox):
    email = new_email()
    signup(anon, email)
    code = latest_code(outbox, email)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(get_settings().email_code_max_attempts - 1):
        assert verify(anon, wrong).status_code == 400
    assert verify(anon, wrong).status_code == 429
    r = verify(anon, code)  # even the right code no longer works
    assert r.status_code == 429 and "Send a new one" in r.json()["detail"]

    age_codes(email, seconds=61)
    assert anon.post("/api/auth/email/resend").status_code == 202
    assert verify(anon, latest_code(outbox, email)).status_code == 200


def test_resend_waits_and_replaces_the_old_code(anon, outbox):
    email = new_email()
    signup(anon, email)
    first = latest_code(outbox, email)

    r = anon.post("/api/auth/email/resend")
    assert r.status_code == 429 and "seconds" in r.json()["detail"]
    assert 0 < anon.get("/api/auth/email/status").json()["resend_after_seconds"] <= 60

    age_codes(email, seconds=61)
    r = anon.post("/api/auth/email/resend")
    assert r.status_code == 202 and r.json()["resend_after_seconds"] == 60
    second = latest_code(outbox, email)
    if second != first:
        assert verify(anon, first).status_code == 400  # the old code stopped working
    assert verify(anon, second).status_code == 200
    assert anon.post("/api/auth/email/resend").status_code == 409  # already confirmed


def test_expired_codes_and_the_daily_cap(anon, outbox, monkeypatch):
    email = new_email()
    signup(anon, email)
    code = latest_code(outbox, email)
    age_codes(email, minutes=16)
    r = verify(anon, code)
    assert r.status_code == 400 and "expired" in r.json()["detail"]

    monkeypatch.setattr(get_settings(), "email_code_max_per_day", 3)
    for _ in range(2):
        age_codes(email, seconds=61)
        assert anon.post("/api/auth/email/resend").status_code == 202
    age_codes(email, seconds=61)
    r = anon.post("/api/auth/email/resend")
    assert r.status_code == 429 and "today" in r.json()["detail"]


def test_logging_in_later_sends_a_fresh_code_only_when_needed(anon, outbox):
    email = new_email()
    signup(anon, email)
    anon.post("/api/auth/logout")
    sent = len(outbox.sent)

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["email_verified"] is False
        assert len(outbox.sent) == sent  # the first code is still valid

        age_codes(email, minutes=20)
        c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert len(outbox.sent) == sent + 1
        assert verify(c, latest_code(outbox, email)).status_code == 200


def test_admin_emails_are_promoted_only_after_confirming(anon, outbox, monkeypatch):
    email = new_email()
    monkeypatch.setattr(get_settings(), "admin_emails", [email])
    me = signup(anon, email)
    assert me["role"] == "user"
    assert anon.get("/api/auth/me").json()["role"] == "user"
    assert anon.get("/api/admin/overview").status_code == 403
    r = verify(anon, latest_code(outbox, email))
    assert r.json()["role"] == "admin"
    assert anon.get("/api/admin/overview").status_code == 200


def test_password_reset_also_confirms_the_email(anon, outbox):
    import re

    email = new_email()
    signup(anon, email)
    anon.post("/api/auth/logout")
    anon.post("/api/auth/password/forgot", json={"email": email})
    token = re.search(r"token=([\w-]+)", outbox.sent[-1].text).group(1)
    r = anon.post("/api/auth/password/reset", json={"token": token, "password": "another-good-pass-9"})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert anon.get("/api/stats").status_code == 200


def test_existing_accounts_keep_working(client):
    me = client.get("/api/auth/me").json()
    assert me["email_verified"] is True
    with SessionLocal() as db:
        assert db.query(User).filter_by(email=client.email).one().email_verified_at <= utcnow()
