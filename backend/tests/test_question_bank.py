import random

import pytest

from app.question_bank import CodeQuestion, McqQuestion, QuestionBank, load_bank, public_question
from app.services.code_runner import run_tests

bank = load_bank()
code_questions = [q for q in bank.questions.values() if isinstance(q, CodeQuestion)]


def test_bank_loads_with_every_test_satisfiable():
    assert len(bank.questions) >= 80
    for test in bank.tests.values():
        picked = bank.pick_questions(test, random.Random(0))
        assert len(picked) == test.question_count
        assert len({q.id for q in picked}) == len(picked), "no duplicate questions in one attempt"


@pytest.mark.parametrize("q", code_questions, ids=lambda q: q.id)
def test_reference_solutions_pass_all_tests(q: CodeQuestion):
    result = run_tests(q.reference_solution, q.function_name, [t.model_dump() for t in q.tests])
    assert result.error is None, result.error
    failing = [o for o in result.outcomes if not o.passed]
    assert not failing, failing


@pytest.mark.parametrize("q", code_questions, ids=lambda q: q.id)
def test_starter_code_does_not_pass(q: CodeQuestion):
    result = run_tests(q.starter_code, q.function_name, [t.model_dump() for t in q.tests])
    assert result.passed < result.total


def test_public_question_never_leaks_answers():
    for q in bank.questions.values():
        data = public_question(q)
        for secret in ("answer", "option_scores", "explanation", "reference_solution", "tests", "rubric", "model_answer"):
            assert secret not in data, f"{q.id} leaks {secret}"
        if isinstance(q, CodeQuestion):
            assert len(data["examples"]) == sum(not t.hidden for t in q.tests)


def test_sjt_answer_must_carry_top_score():
    with pytest.raises(ValueError):
        McqQuestion(
            id="x", category="c", topic="t", difficulty="easy", prompt="p",
            options=["a", "b"], answer=0, option_scores=[1, 2],
        )


def test_bank_rejects_unsatisfiable_tests():
    from app.question_bank import TestDefinition

    q = McqQuestion(id="q1", category="c", topic="t", difficulty="easy", prompt="p", options=["a", "b"], answer=0)
    test = TestDefinition(
        id="t", title="t", description="d", skill_area="s", time_limit_minutes=1,
        sections=[{"category": "c", "count": 2}],
    )
    with pytest.raises(ValueError, match="needs 2"):
        QuestionBank([q], [test])


def test_unseen_questions_are_served_before_repeats():
    test = bank.tests["critical-thinking"]
    pool = [q.id for q in bank.questions.values() if q.category == "critical_thinking"]
    seen = {qid: 1 for qid in pool[: len(pool) - test.question_count]}
    picked = {q.id for q in bank.pick_questions(test, random.Random(1), times_seen=seen)}
    assert picked == set(pool) - set(seen)


def test_least_seen_questions_come_first_once_all_are_seen():
    test = bank.tests["critical-thinking"]
    pool = [q.id for q in bank.questions.values() if q.category == "critical_thinking"]
    seen = {qid: 3 for qid in pool}
    fresh = pool[: test.question_count]
    for qid in fresh:
        seen[qid] = 1
    picked = {q.id for q in bank.pick_questions(test, random.Random(2), times_seen=seen)}
    assert picked == set(fresh)
