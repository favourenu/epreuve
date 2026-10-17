"""Loads and validates the question bank and test definitions from app/data.

Questions live in JSON files under app/data/questions (one file per category) so
they can be reviewed and versioned like code. Everything is validated at startup;
a malformed file fails fast instead of surfacing mid-test.
"""

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator

DATA_DIR = Path(__file__).resolve().parent / "data"

Difficulty = Literal["easy", "medium", "hard"]


class _QuestionBase(BaseModel):
    id: str
    category: str
    topic: str
    difficulty: Difficulty
    prompt: str
    explanation: str = ""


class McqQuestion(_QuestionBase):
    type: Literal["mcq"] = "mcq"
    options: list[str] = Field(min_length=2)
    answer: int
    # Optional partial credit per option (used for situational judgement questions).
    option_scores: list[float] | None = None
    points: float = 1

    @model_validator(mode="after")
    def _check(self) -> "McqQuestion":
        if not 0 <= self.answer < len(self.options):
            raise ValueError(f"{self.id}: answer index out of range")
        if self.option_scores is not None:
            if len(self.option_scores) != len(self.options):
                raise ValueError(f"{self.id}: option_scores must match options")
            if max(self.option_scores) != self.option_scores[self.answer]:
                raise ValueError(f"{self.id}: the answer must carry the highest score")
            self.points = max(self.option_scores)
        return self


class CodeTest(BaseModel):
    args: list[Any]
    expected: Any
    hidden: bool = False


class CodeQuestion(_QuestionBase):
    type: Literal["code"] = "code"
    language: Literal["python"] = "python"
    function_name: str
    starter_code: str
    reference_solution: str
    tests: list[CodeTest] = Field(min_length=1)
    points: float = 10

    @model_validator(mode="after")
    def _check(self) -> "CodeQuestion":
        if not any(not t.hidden for t in self.tests):
            raise ValueError(f"{self.id}: needs at least one visible test")
        if not any(t.hidden for t in self.tests):
            raise ValueError(f"{self.id}: needs at least one hidden test")
        return self


class WrittenQuestion(_QuestionBase):
    type: Literal["written"] = "written"
    rubric: list[str] = Field(min_length=1)
    min_words: int = 0
    max_words: int = 400
    model_answer: str = ""
    points: float = 10


Question = Annotated[McqQuestion | CodeQuestion | WrittenQuestion, Field(discriminator="type")]
_question_list = TypeAdapter(list[Question])


class TestSection(BaseModel):
    category: str
    count: int = Field(gt=0)
    difficulties: list[Difficulty] | None = None


class TestDefinition(BaseModel):
    id: str
    title: str
    description: str
    skill_area: str
    time_limit_minutes: int = Field(gt=0)
    instructions: list[str] = []
    sections: list[TestSection] = Field(min_length=1)
    shuffle: bool = True

    @property
    def question_count(self) -> int:
        return sum(s.count for s in self.sections)


class QuestionBank:
    def __init__(self, questions: list[Question], tests: list[TestDefinition]):
        self.questions: dict[str, Question] = {}
        for q in questions:
            if q.id in self.questions:
                raise ValueError(f"Duplicate question id: {q.id}")
            self.questions[q.id] = q
        self.tests: dict[str, TestDefinition] = {t.id: t for t in tests}
        self._validate_tests()

    def _pool(self, section: TestSection) -> list[Question]:
        return [
            q
            for q in self.questions.values()
            if q.category == section.category
            and (section.difficulties is None or q.difficulty in section.difficulties)
        ]

    def _validate_tests(self) -> None:
        for test in self.tests.values():
            for section in test.sections:
                available = len(self._pool(section))
                if available < section.count:
                    raise ValueError(
                        f"Test '{test.id}' needs {section.count} '{section.category}' "
                        f"questions but the bank has {available}"
                    )

    def pick_questions(
        self,
        test: TestDefinition,
        rng: random.Random | None = None,
        times_seen: dict[str, int] | None = None,
    ) -> list[Question]:
        """Choose a test's questions, least-seen first.

        `times_seen` maps question id -> how often this user has been served it.
        Unseen questions always come first, then the least repeated, with random
        order among equals, so a retake shows fresh questions until the pool runs out.
        """
        rng = rng or random.Random()
        times_seen = times_seen or {}
        picked: list[Question] = []
        taken: set[str] = set()
        for section in test.sections:
            pool = [q for q in self._pool(section) if q.id not in taken]
            pool.sort(key=lambda q: (times_seen.get(q.id, 0), rng.random()))
            chosen = pool[: section.count]
            picked.extend(chosen)
            taken.update(q.id for q in chosen)
        if test.shuffle:
            rng.shuffle(picked)
        return picked


def load_bank(data_dir: Path = DATA_DIR) -> QuestionBank:
    questions: list[Question] = []
    for path in sorted((data_dir / "questions").glob("*.json")):
        try:
            questions.extend(_question_list.validate_json(path.read_bytes()))
        except Exception as exc:
            raise ValueError(f"Invalid question file {path.name}: {exc}") from exc
    tests = [TestDefinition.model_validate(t) for t in json.loads((data_dir / "tests.json").read_text("utf-8"))]
    return QuestionBank(questions, tests)


@lru_cache
def get_bank() -> QuestionBank:
    return load_bank()


def public_question(q: Question) -> dict[str, Any]:
    """The question as shown to a candidate: no answers, scores, or hidden tests."""
    data: dict[str, Any] = {
        "id": q.id,
        "type": q.type,
        "category": q.category,
        "topic": q.topic,
        "difficulty": q.difficulty,
        "prompt": q.prompt,
        "points": q.points,
    }
    if isinstance(q, McqQuestion):
        data["options"] = q.options
    elif isinstance(q, CodeQuestion):
        data["language"] = q.language
        data["function_name"] = q.function_name
        data["starter_code"] = q.starter_code
        data["examples"] = [{"args": t.args, "expected": t.expected} for t in q.tests if not t.hidden]
        data["hidden_test_count"] = sum(t.hidden for t in q.tests)
    elif isinstance(q, WrittenQuestion):
        data["min_words"] = q.min_words
        data["max_words"] = q.max_words
    return data


def question_from_snapshot(snapshot: dict[str, Any]) -> Question:
    return TypeAdapter(Question).validate_python(snapshot)
