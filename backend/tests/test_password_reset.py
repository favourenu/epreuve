import re
from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import PasswordResetToken, utcnow
from app.services.email import password_reset_email
from tests.conftest import PASSWORD

NEW_PASSWORD = "brand-new-password-42"


def forgot(c, email):
    return c.post("/api/auth/password/forgot", json={"email": email})


def token_from(outbox) -> str:
    assert outbox.sent, "no email was sent"
    return re.search(r"reset-password\?token=([\w-]+)", outbox.sent[-1].text).group(1)


def test_reset_email_is_sent_with_a_working_link(client, outbox):
    r = forgot(client, client.email.upper())
    assert r.status_code == 202
    assert len(outbox.sent) == 1
    email = outbox.sent[0]
    assert email.to == client.email and "Reset your" in email.subject
    assert f"{get_settings().app_base_url}/reset-password?token=" in email.text
    assert email.html.count(token_from(outbox)) == 3  # button href, fallback link href and its text


def test_unknown_email_gets_the_same_reply_and_no_email(client, outbox):
    known = forgot(client, client.email)
    unknown = forgot(client, "nobody-here@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(outbox.sent) == 1


def test_reset_changes_password_signs_in_and_signs_out_other_sessions(make_client, outbox, anon):
    user = make_client()
    forgot(anon, user.email)
    token = token_from(outbox)

    assert anon.post("/api/auth/password/reset/check", json={"token": token}).json() == {"email": user.email}
    r = anon.post("/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == user.email
    assert anon.get("/api/auth/me").status_code == 200  # signed in by the reset

    assert user.get("/api/auth/me").status_code == 401  # the old session was revoked
    with TestClient(app) as fresh:
        assert fresh.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 401
        assert fresh.post("/api/auth/login", json={"email": user.email, "password": NEW_PASSWORD}).status_code == 200


def test_links_are_single_use(client, outbox, anon):
    forgot(anon, client.email)
    token = token_from(outbox)
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 200
    again = anon.post("/api/auth/password/reset", json={"token": token, "password": "another-password-9"})
    assert again.status_code == 400 and "invalid or has expired" in again.json()["detail"]


def test_requesting_again_invalidates_the_previous_link(client, outbox, anon):
    forgot(anon, client.email)
    first = token_from(outbox)
    forgot(anon, client.email)
    second = token_from(outbox)
    assert first != second
    assert anon.post("/api/auth/password/reset/check", json={"token": first}).status_code == 400
    assert anon.post("/api/auth/password/reset/check", json={"token": second}).status_code == 200


def test_expired_links_are_rejected(client, outbox, anon):
    forgot(anon, client.email)
    token = token_from(outbox)
    with SessionLocal() as db:
        for t in db.query(PasswordResetToken).all():
            t.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 400


def test_weak_new_password_is_rejected_and_link_still_works(client, outbox, anon):
    forgot(anon, client.email)
    token = token_from(outbox)
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": "short"}).status_code == 400
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 200


def test_made_up_token_is_rejected(anon):
    assert anon.post("/api/auth/password/reset/check", json={"token": "not-a-real-token-123"}).status_code == 400


def test_token_is_not_stored_in_plain_text(client, outbox):
    forgot(client, client.email)
    token = token_from(outbox)
    with SessionLocal() as db:
        assert token not in [t.token_hash for t in db.query(PasswordResetToken).all()]


def test_reset_requests_are_throttled(client, outbox, anon):
    limit = get_settings().password_reset_max_requests
    for _ in range(limit):
        assert forgot(anon, client.email).status_code == 202
    assert forgot(anon, client.email).status_code == 429
    assert len(outbox.sent) == limit


def test_email_escapes_the_users_name():
    email = password_reset_email("a@example.com", "<script>alert(1)</script>", "https://x/reset?token=abc", 60)
    assert "<script>" not in email.html and "&lt;script&gt;" in email.html
