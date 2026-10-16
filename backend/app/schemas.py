from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


class StartAttemptRequest(BaseModel):
    test_id: str


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
