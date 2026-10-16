from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import User, UserSession, utcnow
from tests.conftest import PASSWORD

COOKIE = get_settings().session_cookie_name


def signup(c: TestClient, email="ada@example.com", password=PASSWORD, name="Ada"):
    return c.post("/api/auth/signup", json={"email": email, "password": password, "name": name})


def login(c: TestClient, email, password=PASSWORD):
    return c.post("/api/auth/login", json={"email": email, "password": password})


# --- sign-up ---------------------------------------------------------------


def test_signup_creates_account_and_logs_in(anon):
    r = signup(anon, email="Signup.Case@Example.com")
    assert r.status_code == 201
    assert r.json()["email"] == "signup.case@example.com"  # normalised
    assert "password" not in r.text and "hash" not in r.text

    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert anon.get("/api/auth/me").json()["name"] == "Ada"


def test_password_is_stored_hashed_with_argon2(anon):
    signup(anon, email="hash@example.com")
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="hash@example.com").one()
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash


def test_session_token_is_not_stored_in_plain_text(anon):
    r = signup(anon, email="token@example.com")
    token = r.cookies[COOKIE]
    with SessionLocal() as db:
        hashes = [s.token_hash for s in db.query(UserSession).all()]
    assert token not in hashes


def test_duplicate_email_is_rejected_case_insensitively(anon):
    assert signup(anon, email="dupe@example.com").status_code == 201
    r = signup(anon, email="DUPE@example.com")
    assert r.status_code == 409


def test_signup_validates_input(anon):
    assert signup(anon, email="not-an-email").status_code == 422
    assert signup(anon, email="short@example.com", password="abc").status_code == 400
    assert signup(anon, email="simple@example.com", password="aaaaaaaa").status_code == 400
    assert signup(anon, email="noname@example.com", name="   ").status_code == 422


# --- log in / log out ------------------------------------------------------


def test_login_with_correct_password(anon):
    signup(anon, email="login@example.com")
    anon.post("/api/auth/logout")
    r = login(anon, "LOGIN@example.com")
    assert r.status_code == 200 and r.json()["email"] == "login@example.com"
    assert anon.get("/api/auth/me").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_error(anon):
    signup(anon, email="wrongpw@example.com")
    anon.post("/api/auth/logout")
    wrong = login(anon, "wrongpw@example.com", "not-the-password")
    unknown = login(anon, "nobody@example.com", "not-the-password")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Incorrect email or password"}
    assert COOKIE not in anon.cookies


def test_repeated_failed_logins_are_throttled(anon):
    signup(anon, email="throttle@example.com")
    anon.post("/api/auth/logout")
    limit = get_settings().login_max_failures
    for _ in range(limit):
        assert login(anon, "throttle@example.com", "wrong-password").status_code == 401
    r = login(anon, "throttle@example.com", PASSWORD)  # even the right password
    assert r.status_code == 429


def test_logout_revokes_the_session_server_side(anon):
    signup(anon, email="logout@example.com")
    token = anon.cookies[COOKIE]
    assert anon.post("/api/auth/logout").status_code == 204
    assert anon.get("/api/auth/me").status_code == 401
    # Replaying the old cookie must not work either.
    with TestClient(app) as other:
        other.cookies.set(COOKIE, token)
        assert other.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(anon):
    signup(anon, email="expired@example.com")
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="expired@example.com").one()
        for s in db.query(UserSession).filter_by(user_id=user.id):
            s.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert anon.get("/api/auth/me").status_code == 401


def test_forged_cookie_is_rejected(anon):
    anon.cookies.set(COOKIE, "made-up-token")
    assert anon.get("/api/auth/me").status_code == 401


# --- access control --------------------------------------------------------


def test_logged_out_visitors_cannot_use_the_api(anon):
    for method, path in [
        ("get", "/api/tests"),
        ("get", "/api/tests/critical-thinking"),
        ("get", "/api/stats"),
        ("get", "/api/attempts"),
        ("get", "/api/ai/status"),
        ("post", "/api/attempts"),
    ]:
        r = getattr(anon, method)(path, **({"json": {"test_id": "critical-thinking"}} if method == "post" else {}))
        assert r.status_code == 401, (method, path)


def test_users_cannot_see_or_touch_each_others_attempts(make_client):
    alice, bob = make_client(), make_client()
    state = alice.post("/api/attempts", json={"test_id": "critical-thinking"}).json()
    alice.post(f"/api/attempts/{state['id']}/finish")
    aid = state["id"]

    # Bob gets "not found" for every endpoint on Alice's attempt: not even its existence leaks.
    assert bob.get(f"/api/attempts/{aid}").status_code == 404
    assert bob.get(f"/api/attempts/{aid}/review").status_code == 404
    assert bob.post(f"/api/attempts/{aid}/answer", json={"position": 0, "answer": 0}).status_code == 404
    assert bob.post(f"/api/attempts/{aid}/run", json={"position": 0, "code": "x"}).status_code == 404
    assert bob.post(f"/api/attempts/{aid}/finish").status_code == 404
    assert bob.post(f"/api/attempts/{aid}/feedback/retry").status_code == 404

    # Bob's lists and stats contain none of Alice's data.
    assert bob.get("/api/attempts").json() == []
    assert bob.get("/api/stats").json()["completed_attempts"] == 0
    tests = {t["id"]: t for t in bob.get("/api/tests").json()}
    assert tests["critical-thinking"]["attempts"] == 0

    # Alice still sees her own.
    assert [a["id"] for a in alice.get("/api/attempts").json()] == [aid]
    assert alice.get(f"/api/attempts/{aid}/review").status_code == 200


def test_starting_a_running_test_resumes_it(client):
    first = client.post("/api/attempts", json={"test_id": "critical-thinking"})
    second = client.post("/api/attempts", json={"test_id": "critical-thinking"})
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_cross_site_writes_are_blocked(client):
    r = client.post("/api/attempts", json={"test_id": "critical-thinking"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ok = client.post("/api/attempts", json={"test_id": "critical-thinking"}, headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 201
