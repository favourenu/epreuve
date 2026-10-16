import json
from datetime import timedelta

from app.db import SessionLocal
from app.models import Attempt, utcnow
from app.question_bank import get_bank
from app.services.ai.providers import ProviderError
from tests.conftest import FakeProvider

bank = get_bank()


def correct_answer(question: dict):
    q = bank.questions[question["id"]]
    if q.type == "mcq":
        return q.answer
    if q.type == "code":
        return {"code": q.reference_solution}
    return {"text": "A clear professional answer " * 20}


def start(client, test_id):
    r = client.post("/api/attempts", json={"test_id": test_id})
    assert r.status_code == 201, r.text
    return r.json()


def answer(client, state, value):
    return client.post(
        f"/api/attempts/{state['id']}/answer", json={"position": state["position"], "answer": value}
    )


def feedback_reply(user_prompt: str) -> str:
    ids = [line.split(": ", 1)[1] for line in user_prompt.splitlines() if line.startswith("question_id: ")]
    return json.dumps(
        {
            "written_grades": [{"question_id": i, "score": 7.5, "feedback": "Good structure."} for i in ids],
            "summary": "Solid attempt.",
            "strengths": ["Clear"],
            "weaknesses": ["Pacing"],
            "study_plan": [{"topic": "SQL", "priority": "high", "why": "missed", "how_to_practice": "drill"}],
            "test_taking_tips": ["Read carefully"],
        }
    )


def test_full_mcq_attempt_scores_perfectly_and_hides_answers_until_done(client, ai):
    ai.providers = [FakeProvider(reply=feedback_reply)]
    state = start(client, "critical-thinking")
    assert state["total_questions"] == 8 and state["remaining_seconds"] > 590

    while state["status"] == "in_progress":
        assert "answer" not in state["question"] and "explanation" not in state["question"]
        r = answer(client, state, correct_answer(state["question"]))
        assert r.status_code == 200, r.text
        state = r.json()

    assert state["percent"] == 100.0
    review = client.get(f"/api/attempts/{state['id']}/review").json()
    assert all(i["is_correct"] for i in review["items"])
    assert "explanation" in review["items"][0]["question"]
    assert review["feedback"]["summary"] == "Solid attempt."
    assert review["attempt"]["feedback_status"] == "ready"


def test_cannot_skip_ahead_or_go_back(client):
    state = start(client, "critical-thinking")
    r = client.post(f"/api/attempts/{state['id']}/answer", json={"position": 1, "answer": 0})
    assert r.status_code == 409
    answer(client, state, 0)
    r = client.post(f"/api/attempts/{state['id']}/answer", json={"position": 0, "answer": 1})
    assert r.status_code == 409


def test_invalid_answer_shape_is_rejected(client):
    state = start(client, "critical-thinking")
    assert answer(client, state, 99).status_code == 400
    assert answer(client, state, "A").status_code == 400
    assert answer(client, state, True).status_code == 400


def test_skipped_answers_score_zero(client):
    state = start(client, "attention-to-detail")
    while state["status"] == "in_progress":
        state = answer(client, state, None).json()
    assert state["score"] == 0 and state["max_score"] == 6


def test_finish_early_scores_unanswered_as_zero(client):
    state = start(client, "critical-thinking")
    state = answer(client, state, correct_answer(state["question"])).json()
    state = client.post(f"/api/attempts/{state['id']}/finish").json()
    assert state["status"] == "completed" and state["score"] == 1 and not state["timed_out"]
    assert client.post(f"/api/attempts/{state['id']}/finish").status_code == 409


def test_deadline_is_enforced_server_side(client):
    state = start(client, "critical-thinking")
    with SessionLocal() as db:
        db.get(Attempt, state["id"]).deadline = utcnow() - timedelta(minutes=1)
        db.commit()
    r = answer(client, state, 0)
    assert r.status_code == 409 and "Time is up" in r.json()["detail"]
    state = client.get(f"/api/attempts/{state['id']}").json()
    assert state["status"] == "completed" and state["timed_out"]


def test_coding_run_uses_visible_tests_and_grades_with_hidden(client, ai):
    ai.providers = [FakeProvider(reply=feedback_reply)]
    state = start(client, "python-coding")
    q = bank.questions[state["question"]["id"]]

    run = client.post(
        f"/api/attempts/{state['id']}/run", json={"position": 0, "code": q.reference_solution}
    ).json()
    assert run["total"] == len(state["question"]["examples"]) and run["passed"] == run["total"]

    state = answer(client, state, {"code": q.starter_code}).json()
    state = answer(client, state, correct_answer(state["question"])).json()
    review = client.get(f"/api/attempts/{state['id']}/review").json()
    first, second = review["items"]
    assert first["points"] < first["max_points"] and second["points"] == second["max_points"]
    assert any(t["hidden"] for t in second["grading"]["tests"])


def test_written_answers_are_graded_by_ai(client, ai):
    provider = FakeProvider(reply=feedback_reply)
    ai.providers = [provider]
    state = start(client, "written-communication")
    while state["status"] == "in_progress":
        state = answer(client, state, correct_answer(state["question"])).json()

    review = client.get(f"/api/attempts/{state['id']}/review").json()
    assert [i["points"] for i in review["items"]] == [7.5, 7.5]
    assert review["items"][0]["grading"]["feedback"] == "Good structure."
    assert review["attempt"]["score"] == 15
    # Candidate text is fenced off as data in the prompt.
    assert "<candidate_answer>" in provider.calls[0][1]
    assert len(provider.calls) == 1, "one AI request per attempt"


def test_ai_failure_leaves_written_pending_then_retry_succeeds(client, ai):
    ai.providers = [FakeProvider(error=ProviderError("fake: down"))]
    state = start(client, "written-communication")
    while state["status"] == "in_progress":
        state = answer(client, state, correct_answer(state["question"])).json()

    review = client.get(f"/api/attempts/{state['id']}/review").json()
    assert review["attempt"]["feedback_status"] == "failed"
    assert "fake: down" in review["feedback_error"]
    assert all(i["points"] is None for i in review["items"])
    assert all(c["pending"] for c in review["categories"])

    ai.providers = [FakeProvider(reply=feedback_reply)]
    assert client.post(f"/api/attempts/{state['id']}/feedback/retry").status_code == 200
    review = client.get(f"/api/attempts/{state['id']}/review").json()
    assert review["attempt"]["feedback_status"] == "ready"
    assert review["attempt"]["score"] == 15


def test_ai_scores_are_clamped_to_max(client, ai):
    def overgenerous(user_prompt):
        data = json.loads(feedback_reply(user_prompt))
        for g in data["written_grades"]:
            g["score"] = 50
        return json.dumps(data)

    ai.providers = [FakeProvider(reply=overgenerous)]
    state = start(client, "written-communication")
    while state["status"] == "in_progress":
        state = answer(client, state, correct_answer(state["question"])).json()
    assert client.get(f"/api/attempts/{state['id']}").json()["score"] == 20


def test_stats_and_test_list_reflect_history(client, ai):
    ai.providers = [FakeProvider(reply=feedback_reply)]
    state = start(client, "attention-to-detail")
    while state["status"] == "in_progress":
        state = answer(client, state, correct_answer(state["question"])).json()

    tests = {t["id"]: t for t in client.get("/api/tests").json()}
    assert tests["attention-to-detail"]["best_percent"] == 100.0
    stats = client.get("/api/stats").json()
    assert stats["completed_attempts"] >= 1
    assert any(c["category"] == "attention_to_detail" for c in stats["categories"])


def test_unknown_ids_return_404(client):
    assert client.post("/api/attempts", json={"test_id": "nope"}).status_code == 404
    assert client.get("/api/attempts/nope").status_code == 404
    assert client.get("/api/tests/nope").status_code == 404
