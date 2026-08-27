import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analyses import analyses_router
from app.api.github import github_router
from app.api.repositories import repositories_router
from app.dependencies import get_llm_service
from app.errors import (
    AnalysisNotFound,
    InvalidRepositoryUrl,
    IssueNotFound,
    PatchPilotError,
    RepositoryNotFound,
    UpstreamUnavailable,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PatchPilot API", version="0.1.0")

# The web client is served separately, and `flutter run -d chrome` binds a
# NEW RANDOM PORT on every launch. Pinning an origin list would break the
# client each restart, so development allows any loopback port and
# production is locked down explicitly via CORS_ORIGINS.
_allowed_origins = os.getenv("CORS_ORIGINS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [origin.strip() for origin in _allowed_origins.split(",")]
        if _allowed_origins
        else []
    ),
    allow_origin_regex=(
        None
        if _allowed_origins
        else r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain errors map to status codes in exactly one place.
ERROR_STATUS = {
    InvalidRepositoryUrl: 400,
    RepositoryNotFound: 404,
    IssueNotFound: 404,
    AnalysisNotFound: 404,
    UpstreamUnavailable: 502,
}


@app.exception_handler(PatchPilotError)
def handle_domain_error(request: Request, exc: PatchPilotError):
    return JSONResponse(
        status_code=ERROR_STATUS.get(type(exc), 500),
        content={"detail": str(exc)},
    )


@app.get("/health", tags=["health"])
def health_check():
    """Readiness, including whether diagnosis is actually available."""

    return {
        "status": "ok",
        "github_configured": bool(os.getenv("GITHUB_TOKEN")),
        "diagnosis_available": get_llm_service() is not None,
    }


app.include_router(github_router, prefix="/github")
app.include_router(repositories_router, prefix="/api/repositories")
app.include_router(analyses_router, prefix="/api/analyses")
