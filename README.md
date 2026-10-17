# Épreuve

*Épreuve* (French for "test") is a job-readiness assessment and certification platform: timed, proctored tests of cognitive, technical, coding and workplace skills. AI grades written answers and writes a personalised study plan after every attempt, high scores earn verifiable certificates, and companies can invite candidates to take assessments.

Built for preparing for the Learn2Earn job-readiness assessment, covering technical, cognitive and soft-skill tests.

## What it does

- **10 tests, nearly 300 questions** across numerical reasoning, critical thinking, attention to detail, software engineering, Python, AI/ML fundamentals, coding, situational judgement and written communication, plus a 60-minute mixed **Job Readiness Assessment**.
- **Fresh questions on every retake.** Tests serve the questions you've seen least, so you practise the skill rather than memorising answers.
- **Strict test conditions, enforced by the server.** The deadline is held by the API, not the browser. Questions must be answered in order and can't be revisited. Answers are never sent to the browser until the attempt is completed.
- **Coding questions** run your Python in a locked-down process (see [Code runner security](#code-runner-security)) against visible example tests (with a Run button) and hidden tests (for scoring), with a time limit and partial credit per test passed.
- **Situational judgement** scoring gives partial credit for acceptable-but-not-best answers, as real SJTs do.
- **AI coach.** One AI request per attempt grades written answers against a hiring rubric and produces strengths, weaknesses, a prioritised study plan and test-taking tips.
- **Provider fallback.** OpenRouter, then Gemini, then local Ollama. If one is rate-limited or down, the next is tried. If all fail, the attempt is still scored and the report can be retried later.
- **Accounts.** Email and password sign-up (with password confirmation), Argon2 password hashing, server-side sessions in an httpOnly cookie, and password reset by email (via Resend). Every attempt, score and stat belongs to its user, and the API enforces it: another user's attempt simply returns 404.
- **Progress tracking.** Score trend, per-skill accuracy across all attempts, a "recommended next" test, and full question review with explanations and reference solutions.

## Design

An exam-paper look: warm paper tones, an ink-green brand colour and a marigold "highlighter" accent. Headings use Fraunces and body text uses Atkinson Hyperlegible, a typeface designed for legibility (its slashed zero tells 0 from O apart in detail questions). Fonts are bundled, so the app works offline. Light and dark modes both meet WCAG AA contrast for text and 3:1 for form controls. Every page works from 390px phones up, with no horizontal scrolling and tap targets of at least 40px. See [docs/screenshots](docs/screenshots) for before and after images.

## Architecture

```
frontend/  React + TypeScript + Vite (Monaco editor, Recharts)
  └─ /api → proxied to the backend in dev

backend/   FastAPI + SQLAlchemy (SQLite locally, Postgres in production)
  migrations/               Alembic migrations (applied automatically at startup)
  app/
    data/questions/*.json   question bank (validated at startup)
    data/tests.json         test definitions (sections, timing)
    question_bank.py        schemas, loading, random selection
    services/attempts.py    attempt lifecycle, deadline, ordering rules
    services/grading.py     MCQ / SJT / code / written grading
    services/code_runner.py subprocess harness for candidate code
    services/feedback.py    the single AI prompt + response schema
    services/auth.py        accounts, password hashing, sessions, resets, throttling
    services/email.py       Resend client + email templates
    services/ai/            provider clients + fallback chain
    routers/                HTTP API
  tests/                    pytest suite
```

Key design decisions:

- **Questions are JSON, versioned with the code.** Each attempt stores a snapshot of the questions it served, so past reviews stay correct even after the bank is edited.
- **One AI call per attempt** keeps usage well inside free tiers (OpenRouter's free tier is about 50 requests/day).
- **AI output is validated** with Pydantic, scores are clamped to the maximum, and candidate text is fenced off in the prompt as data to resist prompt injection.
- **Sessions are server-side.** The cookie holds a random token, and the database stores only an HMAC of it keyed with `SECRET_KEY`, so logging out really revokes the session and a leaked database can't be used to forge cookies. Failed logins are throttled per email and per IP, and writes from unknown origins are rejected (CSRF defence on top of `SameSite=Lax`).
- **Password resets** use single-use, 60-minute links stored as keyed hashes. The "forgot password" reply is identical whether or not the account exists, requests are rate-limited, and a successful reset signs the account out everywhere else.
- **One server, one domain.** In production FastAPI also serves the built frontend, so cookies need no cross-site setup and it all runs as a single (free) web service.
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

Locally, with no `RESEND_API_KEY`, password reset emails are printed in the API terminal, link included.

## Tests

```bash
# from backend/
.venv\Scripts\python -m pytest
```

To run the whole suite against Postgres instead of SQLite, set `TEST_DATABASE_URL` (its schema is wiped).

The suite checks sign-up, login, wrong passwords, throttling, session revocation and that one user can never read or change another user's attempts. It also checks that every coding question's reference solution passes all of its tests, that no question leaks its answer before submission, the timer and ordering rules, password resets, migrations, sandbox escape attempts (secrets, files, network, processes, memory and output floods), timeouts and crashes, AI fallback, and score clamping.

## Adding questions

Add entries to a file in `backend/app/data/questions/` (or create a new file). The app refuses to start if a question is malformed, a test asks for more questions than exist, or IDs clash. Run `pytest` after adding questions: it verifies every coding question's reference solution against its tests, and runs every Python "What does this print?" snippet to check the marked answer.

Question types: `mcq` (optional `option_scores` for partial credit), `code` (Python function plus visible and hidden tests), and `written` (rubric and word limits, graded by AI).

## Database and migrations

Locally the app uses a SQLite file. Set `DATABASE_URL` to use Postgres (any `postgres://` or `postgresql://` URL works). Migrations live in `backend/migrations/` and run automatically on startup; databases from before migrations existed are detected and brought up to date without losing data.

After changing a model, create a migration from `backend/`:

```bash
.venv\Scripts\alembic revision --autogenerate -m "describe the change"
```

A test fails if the models and migrations ever drift apart.

## Code runner security

Submitted code runs in a separate process with layered protection, designed for hosts where containers aren't available (such as free web services):

1. **No secrets:** the process gets a minimal environment, so `SECRET_KEY`, API keys and `DATABASE_URL` are invisible.
2. **Python audit hooks** block opening files (apart from reading the Python standard library), listing directories, network access, starting processes and `ctypes`.
3. **Linux resource limits** cap CPU time, memory (256 MB), output (1 MB) and open files, and the process runs in its own session so it can be killed as a group.
4. **At most 2 runs at once**, so a burst can't exhaust a small server's memory, plus a wall-clock timeout.

Audit hooks raise the bar a lot but aren't a perfect boundary (CPython's docs say so). For large-scale untrusted traffic, also run the runner inside a container or microVM.

## Deploying for free (Render + Neon)

Not yet tried on a live Render service; these are the intended settings.

1. **Database:** create a free Postgres project on [Neon](https://neon.tech) (its free tier doesn't expire, unlike Render's free Postgres) and copy the connection string.
2. **Web service:** on [Render](https://render.com), create a free *Web Service* from this repo:
   - Build command: `pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build`
   - Start command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
   - Environment: `DATABASE_URL` (from Neon), `SECRET_KEY`, `APP_BASE_URL=https://epreuve.site`, `CORS_ORIGINS=["https://epreuve.site"]`, `SESSION_COOKIE_SECURE=true`, `RESEND_API_KEY`, your AI keys, and `OLLAMA_ENABLED=false`.
3. **Domain:** add `epreuve.site` as a custom domain on the service and point your DNS at it as Render instructs.

Free Render services sleep after about 15 minutes without traffic, so the first request afterwards takes a little while.

## Notes

- Questions are original, written to match the formats and difficulty of common screening tests. They are not copied from any vendor's question bank.
