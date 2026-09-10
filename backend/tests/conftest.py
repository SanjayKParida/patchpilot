"""Pytest config for PatchPilot backend tests."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: real LLM or GitHub network; opt-in via -m integration",
    )


def pytest_collection_modifyitems(config, items):
    """Keep default pytest free of network and paid LLM calls."""

    if config.option.markexpr:
        return

    items[:] = [
        item
        for item in items
        if item.get_closest_marker("integration") is None
    ]


def pytest_runtest_setup(item):
    if item.get_closest_marker("integration") is None:
        return

    missing = [
        name
        for name in ("OPEN_AI_KEY", "GITHUB_TOKEN")
        if not os.getenv(name)
    ]

    if missing:
        pytest.skip(
            "integration test requires "
            + ", ".join(missing)
        )


@pytest.fixture(autouse=True)
def _isolate_github_app_settings(monkeypatch):
    """Unit tests do not inherit a developer GitHub App from .env."""

    monkeypatch.delenv("GITHUB_APP_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_analysis_store(monkeypatch):
    """Each test gets an empty Redis-backed analysis store."""

    from app import dependencies
    from app.services.analysis_store import AnalysisStore
    from tests.fakes.memory_redis import MemoryRedis

    fake = MemoryRedis()
    monkeypatch.setattr(
        "app.services.analysis_store.connect_redis",
        lambda url=None: fake,
    )
    from app.services.oauth_resume_store import OAuthResumeStore

    dependencies._store = AnalysisStore(redis_client=fake)
    dependencies._resume_store = OAuthResumeStore(redis_client=fake)
    yield
    dependencies._store = None
    dependencies._resume_store = None


@pytest.fixture(autouse=True)
def _isolate_snapshot_store():
    """Each test gets an empty snapshot cache and a fresh runner."""

    from app import dependencies
    from app.dependencies import get_analysis_runner
    from app.services.repository_snapshot_store import RepositorySnapshotStore

    dependencies._snapshot_store = RepositorySnapshotStore()
    get_analysis_runner.cache_clear()
    yield
    get_analysis_runner.cache_clear()
