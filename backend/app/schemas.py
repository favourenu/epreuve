from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CertificateOut(BaseModel):
    id: str
    code: str
    test_id: str
    test_title: str
    percent: float
    level: str
    status: str
    attempt_id: str
    created_at: datetime
    issued_at: datetime | None
    review_note: str | None = None
    price_kobo: int | None = None  # the fee to claim it, when awaiting payment


class TestSummary(BaseModel):
    id: str
    title: str
    description: str
    skill_area: str
    time_limit_minutes: int
    question_count: int
    instructions: list[str]
    attempts: int = 0
    best_percent: float | None = None
    last_percent: float | None = None
    # Certification
    certification_pass_percent: float
    certification_distinction_percent: float
    certification_cooldown_days: int
    certification_available_at: datetime | None = None  # None = can start now
    certificate: CertificateOut | None = None  # best certificate held for this test


class StartAttemptRequest(BaseModel):
    test_id: str
    mode: Literal["practice", "certification"] = "practice"
    # Proctored attempts require agreeing to the rules (one screen, no help, full screen...).
    agree_to_rules: bool = False


class AnswerRequest(BaseModel):
    position: int = Field(ge=0)
    # int for multiple choice, {"code": str} for coding, {"text": str} for written, null to skip.
    answer: Any = None


class RunCodeRequest(BaseModel):
    position: int = Field(ge=0)
    code: str


class AttemptState(BaseModel):
    id: str
    test_id: str
    test_title: str
    mode: str
    proctored: bool
    company: str | None = None  # for invited attempts
    status: str
    started_at: datetime
    deadline: datetime
    submitted_at: datetime | None
    timed_out: bool
    server_time: datetime
    remaining_seconds: int
    position: int
    total_questions: int
    question: dict[str, Any] | None
    score: float | None
    max_score: float | None
    percent: float | None
    feedback_status: str | None


class AttemptListItem(BaseModel):
    id: str
    test_id: str
    test_title: str
    mode: str = "practice"
    company: str | None = None
    status: str
    started_at: datetime
    submitted_at: datetime | None
    timed_out: bool
    score: float | None
    max_score: float | None
    percent: float | None
    feedback_status: str | None


class ReviewItem(BaseModel):
    position: int
    question: dict[str, Any]  # full question, including the answer and explanation
    answer: Any
    points: float | None
    max_points: float
    is_correct: bool | None
    grading: dict[str, Any] | None
    time_spent_seconds: int | None


class CategoryScore(BaseModel):
    category: str
    points: float
    max_points: float
    percent: float
    pending: bool


class AttemptReview(BaseModel):
    attempt: AttemptListItem
    certificate: CertificateOut | None = None
    duration_seconds: int | None
    categories: list[CategoryScore]
    items: list[ReviewItem]
    feedback: dict[str, Any] | None
    feedback_provider: str | None
    feedback_error: str | None


class CategoryStat(BaseModel):
    category: str
    questions: int
    points: float
    max_points: float
    percent: float


class StatsResponse(BaseModel):
    completed_attempts: int
    average_percent: float | None
    categories: list[CategoryStat]
    history: list[AttemptListItem]


class AIStatus(BaseModel):
    providers: list[dict[str, str]]
