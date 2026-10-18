"""API documentation in two editions.

Public (/api/docs): anyone can read it, but "Try it out" is switched off and the
admin endpoints are left out. Internal (/api/internal/docs): the full API with
"Try it out" on, for signed-in admins only. Requests made from it use the
admin's own session cookie, so they act as that admin.
"""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from app.deps import get_admin_user

DESCRIPTION = """
Épreuve is a job-readiness assessment platform: timed tests, AI feedback on
written answers, proctored certification and verifiable certificates.

**Authentication.** Sign in with `POST /api/auth/login`. The API uses a secure,
httpOnly session cookie, so requests from the browser are authenticated
automatically. Write requests from other origins are refused.

**Verifying a certificate.** `GET /api/public/certificates/{code}` needs no
account. Codes look like `EPR-XXXX-XXXX`.
"""

TAGS = [
    {"name": "auth", "description": "Accounts, sessions and password resets."},
    {"name": "tests", "description": "The catalogue of tests."},
    {"name": "attempts", "description": "Taking a test: start, answer, submit and review."},
    {"name": "stats", "description": "Your progress over time."},
    {"name": "certificates", "description": "Your certificates and public verification."},
    {"name": "invites", "description": "Assessments a company has invited you to."},
    {"name": "payments", "description": "Claiming an earned certificate."},
    {"name": "admin", "description": "Platform administration. Admins only."},
    {"name": "meta", "description": "Service health."},
]


def _spec(app: FastAPI, *, internal: bool) -> dict:
    spec = get_openapi(
        title="Épreuve API" + (" (internal)" if internal else ""),
        version=app.version,
        description=DESCRIPTION,
        routes=app.routes,
        tags=TAGS,
    )
    spec["paths"] = {
        path: ops
        for path, ops in spec["paths"].items()
        if path.startswith("/api/") and (internal or not path.startswith("/api/admin"))
    }
    used = {t for ops in spec["paths"].values() for op in ops.values() for t in op.get("tags", [])}
    spec["tags"] = [t for t in TAGS if t["name"] in used]
    return spec


def install(app: FastAPI) -> None:
    cache: dict[bool, dict] = {}

    def spec(internal: bool) -> dict:
        if internal not in cache:
            cache[internal] = _spec(app, internal=internal)
        return cache[internal]

    public = APIRouter(include_in_schema=False)

    @public.get("/api/openapi.json")
    def public_spec():
        return spec(False)

    @public.get("/api/docs")
    def public_docs():
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title="Épreuve API",
            swagger_ui_parameters={"supportedSubmitMethods": [], "defaultModelsExpandDepth": 0},
        )

    internal = APIRouter(include_in_schema=False, dependencies=[Depends(get_admin_user)])

    @internal.get("/api/internal/openapi.json")
    def internal_spec():
        return spec(True)

    @internal.get("/api/internal/docs")
    def internal_docs():
        return get_swagger_ui_html(
            openapi_url="/api/internal/openapi.json",
            title="Épreuve API (internal)",
            swagger_ui_parameters={"persistAuthorization": True, "defaultModelsExpandDepth": 0},
        )

    app.include_router(public)
    app.include_router(internal)
