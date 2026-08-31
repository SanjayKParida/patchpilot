import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analyses import analyses_router
from app.api.auth import auth_router
from app.api.github import github_router
from app.api.repositories import repositories_router
from app.dependencies import get_llm_service, get_settings
from app.errors import (
    AnalysisNotFound,
    AuthorizationFailed,
    GithubPermissionDenied,
    InvalidOAuthState,
    InvalidRef,
    InvalidRepositoryUrl,
    IssueNotFound,
    NotAuthenticated,
    NotAuthorized,
    PatchApprovalNotFound,
    PatchDeliveryInProgress,
    PatchGenerationInProgress,
    SnapshotPreparationInProgress,
    PatchDeliveryNotFound,
    PatchDeliveryRejected,
    PatchNotApproved,
    PatchNotValidated,
    PatchPilotError,
    RepositoryNotFound,
    UpstreamUnavailable,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PatchPilot API", version="0.1.0")

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain errors map to status codes in exactly one place.
ERROR_STATUS = {
    InvalidRepositoryUrl: 400,
    InvalidRef: 400,
    RepositoryNotFound: 404,
    IssueNotFound: 404,
    AnalysisNotFound: 404,
    PatchApprovalNotFound: 404,
    PatchDeliveryNotFound: 404,
    InvalidOAuthState: 400,
    AuthorizationFailed: 400,
    NotAuthenticated: 401,
    NotAuthorized: 403,
    GithubPermissionDenied: 403,
    PatchNotApproved: 409,
    PatchNotValidated: 409,
    PatchDeliveryInProgress: 409,
    PatchGenerationInProgress: 409,
    SnapshotPreparationInProgress: 409,
    PatchDeliveryRejected: 422,
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

    settings = get_settings()
    return {
        "status": "ok",
        "github_configured": bool(settings.github_token),
        "github_app_configured": settings.github_app_configured,
        "diagnosis_available": get_llm_service() is not None,
        "demo_repository": settings.demo_full_name,
    }


app.include_router(github_router, prefix="/github")
app.include_router(auth_router, prefix="/api/auth")
app.include_router(repositories_router, prefix="/api/repositories")
app.include_router(analyses_router, prefix="/api/analyses")
