import json
from dataclasses import dataclass, field
from typing import Any

from app.question_bank import CodeQuestion, McqQuestion, Question, WrittenQuestion
from app.services.code_runner import run_tests


class InvalidAnswerError(ValueError):
    pass


def normalize_answer(q: Question, answer: Any) -> Any:
    """Validate an answer's shape for its question type. None means skipped."""
    if answer is None:
        return None
    if isinstance(q, McqQuestion):
        if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(q.options):
            raise InvalidAnswerError("Answer must be the index of one of the options")
        return answer
    if isinstance(q, CodeQuestion):
        if not isinstance(answer, dict) or not isinstance(answer.get("code"), str):
            raise InvalidAnswerError('Answer must be {"code": "..."}')
        if len(answer["code"]) > 50_000:
            raise InvalidAnswerError("Code is too long")
        return {"code": answer["code"]}
    if isinstance(q, WrittenQuestion):
        if not isinstance(answer, dict) or not isinstance(answer.get("text"), str):
            raise InvalidAnswerError('Answer must be {"text": "..."}')
        text = answer["text"].strip()
        if len(text.split()) > q.max_words * 1.5:
            raise InvalidAnswerError(f"Answer is far over the {q.max_words}-word limit")
        return {"text": text}
    raise InvalidAnswerError("Unknown question type")


def _preview(value: Any, limit: int = 120) -> Any:
    """Keep stored grading details small; large values become a truncated string."""
    text = json.dumps(value)
    return value if len(text) <= limit else text[:limit] + " ...(truncated)"


def word_count(text: str) -> int:
    return len(text.split())


@dataclass
class GradeResult:
    points: float | None  # None = awaiting AI grading
    is_correct: bool | None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_ai(self) -> bool:
        return self.points is None


def grade(q: Question, answer: Any) -> GradeResult:
    if isinstance(q, McqQuestion):
        detail = {"selected": answer, "correct": q.answer}
        if answer is None:
            return GradeResult(0, False, {**detail, "skipped": True})
        points = q.option_scores[answer] if q.option_scores else (q.points if answer == q.answer else 0)
        return GradeResult(points, answer == q.answer, detail)

    if isinstance(q, CodeQuestion):
        if answer is None or not answer["code"].strip():
            return GradeResult(0, False, {"skipped": True})
        run = run_tests(answer["code"], q.function_name, [t.model_dump() for t in q.tests])
        points = round(q.points * run.passed / run.total, 2)
        detail = {
            "error": run.error,
            "timed_out": run.timed_out,
            "passed": run.passed,
            "total": run.total,
            # After submission, hidden tests are revealed so you can learn from them.
            "tests": [
                {
                    "hidden": o.hidden,
                    "passed": o.passed,
                    "args": _preview(o.args),
                    "expected": _preview(o.expected),
                    "output": _preview(o.output),
                    "error": o.error,
                }
                for o in run.outcomes
            ],
        }
        return GradeResult(points, run.passed == run.total, detail)

    if isinstance(q, WrittenQuestion):
        if answer is None or not answer["text"]:
            return GradeResult(0, False, {"skipped": True})
        words = word_count(answer["text"])
        if words < max(5, q.min_words // 4):
            return GradeResult(0, False, {"word_count": words, "feedback": "Answer too short to assess."})
        return GradeResult(None, None, {"word_count": words})

    raise TypeError(f"Unsupported question type: {type(q).__name__}")
