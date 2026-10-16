import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.question_bank import get_bank
from app.routers import attempts, stats, tests
from app.services.attempts import recover_interrupted_feedback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bank = get_bank()  # fail fast on an invalid question bank
    log.info("Loaded %d questions and %d tests", len(bank.questions), len(bank.tests))
    init_db()
    with SessionLocal() as db:
        if n := recover_interrupted_feedback(db):
            log.warning("Marked %d interrupted feedback job(s) as failed", n)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Assessment Practice Platform", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(tests.router)
    app.include_router(attempts.router)
    app.include_router(stats.router)

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
