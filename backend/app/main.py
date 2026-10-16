import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.question_bank import get_bank
from app.routers import attempts, auth, stats, tests
from app.services.auth import secret_key
from app.services.attempts import recover_interrupted_feedback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bank = get_bank()  # fail fast on an invalid question bank
    secret_key()  # fail fast on a bad SECRET_KEY, or warn if it's missing
    log.info("Loaded %d questions and %d tests", len(bank.questions), len(bank.tests))
    init_db()
    with SessionLocal() as db:
        if n := recover_interrupted_feedback(db):
            log.warning("Marked %d interrupted feedback job(s) as failed", n)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Épreuve API", version="0.1.0", lifespan=lifespan)
    settings = get_settings()

    @app.middleware("http")
    async def reject_cross_site_writes(request: Request, call_next):
        """CSRF defence in depth (the session cookie is also SameSite=Lax): browsers send
        an Origin header on cross-site requests, so refuse writes from unknown origins."""
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in settings.cors_origins:
            same_host = origin.split("://", 1)[-1] == request.headers.get("host")
            if not same_host:
                return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(tests.router)
    app.include_router(attempts.router)
    app.include_router(stats.router)

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
