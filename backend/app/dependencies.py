"""
Composition root.

Services are constructed once, here, so the API modules stay free of
wiring and the object graph is visible in one place.
"""

import logging
import os
from functools import lru_cache

from dotenv import load_dotenv

from app.services.analysis_store import AnalysisStore
from app.services.analysis_runner import AnalysisRunner
from app.services.github_service import GithubService
from app.services.llm_service import LLMService

load_dotenv()

logger = logging.getLogger(__name__)

_store = AnalysisStore()


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
def get_analysis_runner():
    return AnalysisRunner(
        github_service=get_github_service(),
        llm_service=get_llm_service(),
    )


def get_analysis_store():
    return _store
