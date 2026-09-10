"""
Composition root.

Services are constructed once, here, so the API modules stay free of
wiring and the object graph is visible in one place.
"""

import logging
import os
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, Request

from app.code_intelligence.registry import CodeIntelligenceRegistry
from app.config import SESSION_COOKIE_NAME, get_settings
from app.services.analysis_store import AnalysisStore
from app.services.analysis_runner import AnalysisRunner
from app.services.auth_store import AuthStore
from app.services.oauth_resume_store import OAuthResumeStore
from app.services.context_builder_service import ContextBuilderService
from app.services.github_service import GithubService
from app.services.llm_service import LLMService
from app.services.patch_generator_service import PatchGeneratorService
from app.services.patch_validator_service import PatchValidatorService
from app.services.repository_snapshot_store import RepositorySnapshotStore
from app.services.validation_command_runner import (
    ShellValidationCommandRunner,
)
from app.application.auth_service import AuthService
from app.application.patch_delivery_service import PatchDeliveryService
from app.application.repository_access import RepositoryAccess
from app.infrastructure.github_app_client import GithubAppClient
from app.infrastructure.github_write_client import GithubWriteClient

load_dotenv()

logger = logging.getLogger(__name__)

_store = None
_resume_store = None
_auth_store = AuthStore(
    session_ttl_seconds=get_settings().session_ttl_seconds,
)
_snapshot_store = RepositorySnapshotStore()


@lru_cache(maxsize=1)
def get_github_service():
    return GithubService(os.getenv("GITHUB_TOKEN"))


@lru_cache(maxsize=1)
def get_llm_service():
    """
    The language model, or None when it is not configured.

    LLMService raises without a key. Retrieval does not need a model,
    so a missing key degrades the product to ranked files rather than
    taking the API down.
    """

    try:
        return LLMService()
    except RuntimeError as e:
        logger.warning("Diagnosis disabled: %s", e)
        return None


@lru_cache(maxsize=1)
def get_context_builder():
    return ContextBuilderService(
        CodeIntelligenceRegistry.default(),
    )


@lru_cache(maxsize=1)
def get_analysis_runner():
    return AnalysisRunner(
        github_service=get_github_service(),
        llm_service=get_llm_service(),
        context_builder=get_context_builder(),
        snapshot_store=get_repository_snapshot_store(),
    )


@lru_cache(maxsize=1)
def get_patch_generator():
    return PatchGeneratorService(llm_service=get_llm_service())


@lru_cache(maxsize=1)
def get_patch_validator():
    """
    Apply + command runner for on-demand PATCH validate.

    Uses the shell runner so a Flutter profile can actually execute
    pub get / analyze / test. Tests override this with a fake.
    """

    return PatchValidatorService(
        command_runner=ShellValidationCommandRunner(),
    )


def get_analysis_store():
    global _store
    if _store is None:
        _store = AnalysisStore()
    return _store


def get_repository_snapshot_store():
    return _snapshot_store


def get_auth_store():
    return _auth_store


def get_oauth_resume_store():
    global _resume_store
    if _resume_store is None:
        _resume_store = OAuthResumeStore()
    return _resume_store


@lru_cache(maxsize=1)
def get_github_app_client():
    return GithubAppClient(get_settings())


def get_auth_service():
    return AuthService(
        store=get_auth_store(),
        github_app=get_github_app_client(),
        settings=get_settings(),
        resume_store=get_oauth_resume_store(),
        analysis_store=get_analysis_store(),
    )


def get_repository_access():
    return RepositoryAccess(
        store=get_auth_store(),
        settings=get_settings(),
        github_app=get_github_app_client(),
    )


def get_optional_session(
    request: Request,
    store=Depends(get_auth_store),
):
    return store.get_valid_session(_session_token(request))


def _session_token(request):
    """Cookie first; Bearer for the Flutter web origin on another port."""

    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        return cookie

    header = request.headers.get("authorization") or ""
    prefix = "bearer "
    if header.lower().startswith(prefix):
        return header[len(prefix):].strip()
    return None


def get_visible_analysis(
    analysis_id: str,
    store=Depends(get_analysis_store),
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
):
    record = store.get(analysis_id)
    access.assert_can_read_analysis(record, session)
    return record


@lru_cache(maxsize=1)
def get_github_write_client():
    return GithubWriteClient(os.getenv("GITHUB_TOKEN"))


@lru_cache(maxsize=1)
def get_patch_delivery_service():
    return PatchDeliveryService(
        store=get_analysis_store(),
        github=get_github_service(),
        writer=get_github_write_client(),
    )
