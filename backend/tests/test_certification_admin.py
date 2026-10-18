import re
import uuid
from datetime import timedelta

import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.models import Attempt, utcnow
from tests.conftest import PASSWORD
from tests.test_attempts_api import correct_answer

TEST = "critical-thinking"  # multiple choice only: fast and needs no AI


def start(c, test_id=TEST, mode="certification", agree=True):
    return c.post("/api/attempts", json={"test_id": test_id, "mode": mode, "agree_to_rules": agree})


def complete(c, state, right=True):
    while state["status"] == "in_progress":
        q = state["question"]
        ans = correct_answer(q) if right else None
        state = c.post(f"/api/attempts/{state['id']}/answer", json={"position": state["position"], "answer": ans}).json()
    return state


def report(c, attempt_id, *events):
    return c.post(f"/api/attempts/{attempt_id}/integrity", json={"events": list(events)})


@pytest.fixture
def admin(make_client, monkeypatch):
    email = f"boss-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(get_settings(), "admin_emails", [email.upper()])  # matching is case-insensitive
    c = make_client(email)
    assert c.get("/api/auth/me").json()["role"] == "admin"
    return c


# ------------------------------------------------------------ certification


def test_certification_needs_the_rules_to_be_accepted(client):
    assert start(client, agree=False).status_code == 400
    r = start(client)
    assert r.status_code == 201 and r.json()["mode"] == "certification" and r.json()["proctored"]


def test_one_attempt_per_test_at_a_time_across_modes(client):
    start(client)
    r = start(client, mode="practice")
    assert r.status_code == 409 and "certification attempt" in r.json()["detail"]
    assert start(client).status_code == 200  # same mode resumes


def test_high_score_earns_an_issued_certificate_that_anyone_can_verify(client, anon):
    state = complete(client, start(client).json())
    review = client.get(f"/api/attempts/{state['id']}/review").json()
    cert = review["certificate"]
    assert cert["status"] == "issued" and cert["level"] == "distinction" and cert["percent"] == 100
    assert re.fullmatch(r"EPR-[A-Z2-9]{4}-[A-Z2-9]{4}", cert["code"])

    public = anon.get(f"/api/public/certificates/{cert['code'].lower()}").json()
    assert public["valid"] and public["holder_name"] == "Test User" and public["test_title"] == "Critical Thinking"
    assert "email" not in public

    mine = client.get("/api/certificates").json()
    assert [c["code"] for c in mine] == [cert["code"]]
    summary = next(t for t in client.get("/api/tests").json() if t["id"] == TEST)
    assert summary["certificate"]["code"] == cert["code"]


def test_low_score_earns_no_certificate(client):
    state = complete(client, start(client).json(), right=False)
    assert client.get(f"/api/attempts/{state['id']}/review").json()["certificate"] is None
    assert client.get("/api/certificates").json() == []


def test_practice_attempts_never_earn_certificates(client):
    state = complete(client, start(client, mode="practice").json())
    assert client.get(f"/api/attempts/{state['id']}/review").json()["certificate"] is None


def test_cooldown_between_certification_attempts(client):
    complete(client, start(client).json())
    r = start(client)
    assert r.status_code == 409 and "certification again on" in r.json()["detail"]
    summary = next(t for t in client.get("/api/tests").json() if t["id"] == TEST)
    assert summary["certification_available_at"] is not None
    assert start(client, mode="practice").status_code == 201  # practice is still allowed

    with SessionLocal() as db:  # pretend a week has passed
        for a in db.query(Attempt).filter_by(mode="certification").all():
            a.started_at -= timedelta(days=8)
        db.commit()
    client.post(f"/api/attempts/{start(client, mode='practice').json()['id']}/finish")
    assert start(client).status_code == 201


# ------------------------------------------------------------ integrity


def test_integrity_events_are_only_accepted_for_proctored_attempts(client):
    practice = start(client, mode="practice").json()
    assert report(client, practice["id"], {"kind": "paste"}).status_code == 409


def test_unknown_event_kinds_are_rejected(client):
    cert = start(client).json()
    assert report(client, cert["id"], {"kind": "made_up"}).status_code == 422


def test_suspicious_attempt_goes_to_review_and_admin_decides(make_client, admin, anon):
    user = make_client()
    state = start(user).json()
    assert report(user, state["id"], {"kind": "multiple_screens"}, {"kind": "focus_lost", "duration_ms": 90_000}).status_code == 202
    state = complete(user, state)
    cert = user.get(f"/api/attempts/{state['id']}/review").json()["certificate"]
    assert cert["status"] == "under_review"
    assert anon.get(f"/api/public/certificates/{cert['code']}").status_code == 404  # not public yet

    queue = admin.get("/api/admin/certificates?status=under_review").json()
    item = next(c for c in queue if c["code"] == cert["code"])
    assert item["integrity"]["risk"] == "high"
    assert "A second screen was connected" in item["integrity"]["reasons"]

    detail = admin.get(f"/api/admin/attempts/{state['id']}").json()
    assert {e["kind"] for e in detail["events"]} == {"multiple_screens", "focus_lost"}

    r = admin.post(f"/api/admin/certificates/{item['id']}/review", json={"action": "approve", "note": "Explained: docked laptop"})
    assert r.status_code == 200 and r.json()["status"] == "issued"
    assert anon.get(f"/api/public/certificates/{cert['code']}").json()["valid"] is True

    admin.post(f"/api/admin/certificates/{item['id']}/review", json={"action": "revoke"})
    assert anon.get(f"/api/public/certificates/{cert['code']}").json()["valid"] is False


def test_minor_events_still_issue_automatically(client):
    state = start(client).json()
    report(client, state["id"], {"kind": "focus_lost", "duration_ms": 3000})
    state = complete(client, state)
    assert client.get(f"/api/attempts/{state['id']}/review").json()["certificate"]["status"] == "issued"


# ------------------------------------------------------------ admin access and users


def test_admin_api_is_admins_only(client, anon):
    assert anon.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/overview").status_code == 403


def test_overview_users_and_leaderboard(make_client, admin):
    strong, weak = make_client(), make_client()
    complete(strong, start(strong, mode="practice").json())
    complete(weak, start(weak, mode="practice").json(), right=False)

    ov = admin.get("/api/admin/overview").json()
    assert ov["users_total"] >= 3 and ov["attempts_total"] >= 2 and len(ov["daily"]) == 14

    users = admin.get(f"/api/admin/users?q={strong.email}").json()
    assert users["total"] == 1 and users["users"][0]["average_percent"] == 100

    board = admin.get(f"/api/admin/leaderboard?test_id={TEST}").json()
    ranked = [r["user"]["email"] for r in board]
    assert ranked.index(strong.email) < ranked.index(weak.email)


def test_suspending_a_user_signs_them_out_and_blocks_login(make_client, admin, anon):
    user = make_client()
    uid = user.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"disabled": True}).json()["disabled"] is True
    assert user.get("/api/auth/me").status_code == 401
    r = anon.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 403 and "suspended" in r.json()["detail"]

    admin.patch(f"/api/admin/users/{uid}", json={"disabled": False})
    assert anon.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 200


def test_admin_cannot_demote_or_suspend_themselves(admin):
    me = admin.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/admin/users/{me}", json={"disabled": True}).status_code == 409


def test_admin_can_promote_another_user(make_client, admin):
    user = make_client()
    uid = user.get("/api/auth/me").json()["id"]
    admin.patch(f"/api/admin/users/{uid}", json={"role": "admin"})
    assert user.get("/api/admin/overview").status_code == 200


# ------------------------------------------------------------ company invites


def invite(admin, email, outbox):
    r = admin.post("/api/admin/invites", json={
        "email": email, "candidate_name": "Chidi Okeke", "company": "Acme Ltd", "test_id": TEST,
        "message": "Good luck!",
    })
    assert r.status_code == 201, r.text
    token = re.search(r"/invite/([\w-]+)", outbox.sent[-1].text).group(1)
    return r.json(), token


def test_invite_flow_hides_results_from_candidate_and_shows_them_to_admin(make_client, admin, outbox, anon):
    candidate = make_client()
    row, token = invite(admin, candidate.email, outbox)
    assert outbox.sent[-1].to == candidate.email and "Acme Ltd" in outbox.sent[-1].subject
    assert row["status"] == "sent" and row["link"].endswith(token)

    page = anon.get(f"/api/invites/{token}").json()
    assert page["company"] == "Acme Ltd" and page["status"] == "opened" and page["email"] == candidate.email

    stranger = make_client()
    r = stranger.post(f"/api/invites/{token}/start", json={"agree_to_rules": True})
    assert r.status_code == 409 and candidate.email in r.json()["detail"]
    assert candidate.post(f"/api/invites/{token}/start", json={"agree_to_rules": False}).status_code == 400

    state = candidate.post(f"/api/invites/{token}/start", json={"agree_to_rules": True}).json()
    assert state["mode"] == "invite" and state["company"] == "Acme Ltd"
    report(candidate, state["id"], {"kind": "paste"})
    state = complete(candidate, state)
    assert state["percent"] is None and state["score"] is None  # hidden from the candidate
    assert candidate.get(f"/api/attempts/{state['id']}/review").status_code == 403
    assert candidate.get("/api/certificates").json() == []  # invites don't earn certificates
    assert candidate.get("/api/stats").json()["completed_attempts"] == 0
    history = candidate.get("/api/attempts").json()
    assert history[0]["company"] == "Acme Ltd" and history[0]["percent"] is None

    again = candidate.post(f"/api/invites/{token}/start", json={"agree_to_rules": True})
    assert again.status_code == 409 and "already completed" in again.json()["detail"]

    rows = admin.get("/api/admin/invites?company=acme ltd").json()
    done = next(r for r in rows if r["email"] == candidate.email)
    assert done["status"] == "completed" and done["percent"] == 100 and done["risk"] == "low"
    detail = admin.get(f"/api/admin/attempts/{done['attempt_id']}").json()
    assert detail["review"]["attempt"]["percent"] == 100 and detail["invite"]["company"] == "Acme Ltd"

    csv = admin.get("/api/admin/invites.csv").text
    assert "Chidi Okeke" in csv and candidate.email in csv and "100" in csv


def test_cancelled_and_expired_invites_cannot_be_started(make_client, admin, outbox):
    candidate = make_client()
    row, token = invite(admin, candidate.email, outbox)
    admin.post(f"/api/admin/invites/{row['id']}/cancel")
    r = candidate.post(f"/api/invites/{token}/start", json={"agree_to_rules": True})
    assert r.status_code == 409 and "withdrawn" in r.json()["detail"]

    row, token = invite(admin, candidate.email, outbox)
    from app.models import Invite

    with SessionLocal() as db:
        db.get(Invite, row["id"]).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    r = candidate.post(f"/api/invites/{token}/start", json={"agree_to_rules": True})
    assert r.status_code == 409 and "expired" in r.json()["detail"]


def test_unknown_invite_token_is_404(anon):
    assert anon.get("/api/invites/not-a-real-token").status_code == 404


def test_certificate_waits_for_ai_grading_of_written_answers(client, ai):
    from tests.conftest import FakeProvider
    from tests.test_attempts_api import feedback_reply  # grades every written answer 7.5/10

    ai.providers = [FakeProvider(reply=feedback_reply)]
    state = complete(client, start(client, test_id="written-communication").json())
    review = client.get(f"/api/attempts/{state['id']}/review").json()
    assert review["attempt"]["percent"] == 75.0
    assert review["certificate"]["level"] == "pass" and review["certificate"]["status"] == "issued"
