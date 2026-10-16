# Épreuve

*Épreuve* (French for "test") is a practice platform for employer-style screening tests (TestGorilla, SkillLadder and similar): timed, one question at a time, no going back. AI grades written answers and writes a personalised study plan after every attempt.

Built for preparing for the Learn2Earn job-readiness assessment, covering technical, cognitive and soft-skill tests.

## What it does

- **10 tests, 90 questions** across numerical reasoning, critical thinking, attention to detail, software engineering, Python, AI/ML fundamentals, coding, situational judgement and written communication, plus a 60-minute mixed **Job Readiness Assessment**.
- **Real test conditions, enforced by the server.** The deadline is held by the API, not the browser. Questions must be answered in order and can't be revisited. Answers are never sent to the browser until the attempt is completed.
- **Coding questions** run your Python in a separate process against visible example tests (with a Run button) and hidden tests (for scoring), with a time limit and partial credit per test passed.
- **Situational judgement** scoring gives partial credit for acceptable-but-not-best answers, as real SJTs do.
- **AI coach.** One AI request per attempt grades written answers against a hiring rubric and produces strengths, weaknesses, a prioritised study plan and test-taking tips.
- **Provider fallback.** OpenRouter, then Gemini, then local Ollama. If one is rate-limited or down, the next is tried. If all fail, the attempt is still scored and the report can be retried later.
- **Accounts.** Email and password sign-up with Argon2 password hashing and server-side sessions in an httpOnly cookie. Every attempt, score and stat belongs to its user, and the API enforces it: another user's attempt simply returns 404.
- **Progress tracking.** Score trend, per-skill accuracy across all attempts, a "recommended next" test, and full question review with explanations and reference solutions.

## Design

An exam-paper look: warm paper tones, an ink-green brand colour and a marigold "highlighter" accent. Headings use Fraunces and body text uses Atkinson Hyperlegible, a typeface designed for legibility (its slashed zero tells 0 from O apart in detail questions). Fonts are bundled, so the app works offline. Light and dark modes both meet WCAG AA contrast for text and 3:1 for form controls. Every page works from 390px phones up, with no horizontal scrolling and tap targets of at least 40px. See [docs/screenshots](docs/screenshots) for before and after images.

## Architecture

```
frontend/  React + TypeScript + Vite (Monaco editor, Recharts)
  └─ /api → proxied to the backend in dev

backend/   FastAPI + SQLAlchemy (SQLite)
  app/
    data/questions/*.json   question bank (validated at startup)
    data/tests.json         test definitions (sections, timing)
    question_bank.py        schemas, loading, random selection
    services/attempts.py    attempt lifecycle, deadline, ordering rules
    services/grading.py     MCQ / SJT / code / written grading
    services/code_runner.py subprocess harness for candidate code
    services/feedback.py    the single AI prompt + response schema
    services/auth.py        accounts, password hashing, sessions, login throttling
    services/ai/            provider clients + fallback chain
    routers/                HTTP API
  tests/                    pytest suite
```

Key design decisions:

- **Questions are JSON, versioned with the code.** Each attempt stores a snapshot of the questions it served, so past reviews stay correct even after the bank is edited.
- **One AI call per attempt** keeps usage well inside free tiers (OpenRouter's free tier is about 50 requests/day).
- **AI output is validated** with Pydantic, scores are clamped to the maximum, and candidate text is fenced off in the prompt as data to resist prompt injection.
- **Sessions are server-side.** The cookie holds a random token, and the database stores only an HMAC of it keyed with `SECRET_KEY`, so logging out really revokes the session and a leaked database can't be used to forge cookies. Failed logins are throttled per email and per IP, and writes from unknown origins are rejected (CSRF defence on top of `SameSite=Lax`).
- **AI work runs in the background.** Results show immediately and the report fills in when ready. Jobs interrupted by a restart are marked failed so they can be retried.

## Setup

Requirements: Python 3.12+, Node 20+. Optional: [Ollama](https://ollama.com) for offline AI.

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
# then edit .env: set SECRET_KEY (see the comment there) and add your OpenRouter and/or Gemini key

# Frontend
cd ../frontend
npm install
```

## Running

Start the API and the web app in two terminals:

```bash
# Terminal 1, from backend/
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

```bash
# Terminal 2, from frontend/
npm run dev
```

Open http://localhost:5173. API docs are at http://localhost:8000/docs.

## Tests

```bash
# from backend/
.venv\Scripts\python -m pytest
```

The suite checks sign-up, login, wrong passwords, throttling, session revocation and that one user can never read or change another user's attempts. It also checks that every coding question's reference solution passes all of its tests, that no question leaks its answer before submission, the timer and ordering rules, sandbox behaviour (timeouts, crashes, stray prints), AI fallback, and score clamping.

## Adding questions

Add entries to a file in `backend/app/data/questions/` (or create a new file). The app refuses to start if a question is malformed, a test asks for more questions than exist, or IDs clash. Run `pytest` after adding coding questions; it verifies the reference solution against your tests.

Question types: `mcq` (optional `option_scores` for partial credit), `code` (Python function plus visible and hidden tests), and `written` (rubric and word limits, graded by AI).

## Notes

- The code runner isolates crashes and infinite loops, but it is **not a security sandbox**. It is meant for running your own code locally.
- Questions are original, written to match the formats and difficulty of common screening tests. They are not copied from any vendor's question bank.
