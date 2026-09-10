"""Anonymous analyses are adopted only through a consumed OAuth resume."""

from copy import deepcopy
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.application.auth_service import AuthService
from app.application.patch_delivery_service import PatchDeliveryService
from app.application.repository_access import RepositoryAccess
from app.dependencies import (
    get_analysis_store,
    get_auth_service,
    get_auth_store,
    get_github_app_client,
    get_github_service,
    get_github_write_client,
    get_oauth_resume_store,
    get_patch_delivery_service,
    get_repository_access,
    get_settings,
)
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.auth_store import AuthStore
from app.services.oauth_resume_store import RESUME_TTL_SECONDS, OAuthResumeStore
from tests.fakes.github_app_client import FakeGitHubAppClient
from tests.fakes.github_write_client import FakeGithub, FakeGithubWriteClient
from tests.fakes.memory_redis import MemoryRedis
from tests.test_auth import _login, _settings


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def auth_env():
    settings = _settings()
    auth_store = AuthStore(session_ttl_seconds=settings.session_ttl_seconds)
    github_app = FakeGitHubAppClient()
    resume_store = OAuthResumeStore(redis_client=MemoryRedis())
    analyses = AnalysisStore()
    auth = AuthService(
        auth_store,
        github_app,
        settings,
        resume_store=resume_store,
        analysis_store=analyses,
    )
    access = RepositoryAccess(auth_store, settings, github_app)
    github = FakeGithub()
    writer = FakeGithubWriteClient()
    delivery = PatchDeliveryService(analyses, github, writer)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_store] = lambda: auth_store
    app.dependency_overrides[get_github_app_client] = lambda: github_app
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_repository_access] = lambda: access
    app.dependency_overrides[get_analysis_store] = lambda: analyses
    app.dependency_overrides[get_oauth_resume_store] = lambda: resume_store
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_github_write_client] = lambda: writer
    app.dependency_overrides[get_patch_delivery_service] = lambda: delivery

    with TestClient(app) as client:
        yield {
            "client": client,
            "auth_store": auth_store,
            "github_app": github_app,
            "analyses": analyses,
            "resume_store": resume_store,
        }

    app.dependency_overrides.clear()


def _without_owner(record):
    payload = deepcopy(record)
    payload.pop("user_id", None)
    return payload


def _completed_anonymous(store, *, owner="o", repo="r", issue_number=1):
    created = store.create(
        owner,
        repo,
        issue_number,
        ref="main",
        commit_sha="a" * 40,
    )
    store.mark_completed(
        created["id"],
        {
            "diagnosis": {
                "root_cause": "filter inverted",
                "confidence": 0.9,
                "explanation": "Active uses isCompleted",
                "suggested_fix": "invert the predicate",
                "cited_files": ["lib/a.dart"],
            },
            "commit_sha": "a" * 40,
            "ref": "main",
            "patch_proposal": {"status": "ok", "files": []},
            "patch_validation": {"status": "passed", "validation_passed": True},
            "patch_approved": True,
            "patch_approved_at": "2026-08-30T12:00:00+00:00",
            "patch_approved_commit_sha": "a" * 40,
            "patch_delivery": {
                "status": "succeeded",
                "stage": "pull_request",
                "pr_number": 12,
                "pr_url": "https://github.com/o/r/pull/12",
            },
        },
    )
    return store.get(created["id"])


def _login_resume(client, analysis_id, *, code="ok-code"):
    start = client.get(
        "/api/auth/github/login",
        params={
            "return_to": "http://localhost:59738/r/o/r/issues/1/pull-request",
            "analysis_id": analysis_id,
            "stage": "pull-request",
            "repair_path": "/r/o/r/issues/1/pull-request",
        },
    )
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = client.get(
        "/api/auth/github/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    return start, callback, state


def test_valid_oauth_resume_adopts_anonymous_analysis(auth_env):
    store = auth_env["analyses"]
    before = _completed_anonymous(store)
    analysis_id = before["id"]
    assert before["user_id"] is None

    _start, callback, _state = _login_resume(auth_env["client"], analysis_id)
    assert callback.status_code == 302
    assert "auth_error=" not in callback.headers["location"]
    assert f"analysis_id={analysis_id}" in callback.headers["location"]

    user_id = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    after = store.get(analysis_id)
    assert after["id"] == analysis_id
    assert after["user_id"] == user_id
    assert _without_owner(after) == _without_owner(before)
    assert store.find_reusable("o", "r", 1, user_id=user_id)["id"] == analysis_id
    assert store.find_reusable("o", "r", 1) is None


def test_already_owned_analysis_is_left_unchanged(auth_env):
    _login(auth_env["client"])
    user_id = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    store = auth_env["analyses"]
    created = store.create("o", "r", 1, user_id=user_id)
    store.mark_completed(
        created["id"],
        {"diagnosis": {"root_cause": "already mine"}},
    )
    before = store.get(created["id"])
    auth_env["client"].post("/api/auth/logout")

    _login_resume(auth_env["client"], created["id"])
    after = store.get(created["id"])
    assert after["user_id"] == user_id
    assert after == before


def test_foreign_analysis_cannot_be_adopted(auth_env):
    _login(auth_env["client"])
    owner_id = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    store = auth_env["analyses"]
    created = store.create("o", "r", 1, user_id=owner_id)
    store.mark_completed(
        created["id"],
        {"diagnosis": {"root_cause": "alice"}},
    )
    before = store.get(created["id"])
    auth_env["client"].post("/api/auth/logout")

    auth_env["github_app"].users_by_code["other-code"] = {
        "id": 99,
        "login": "other",
        "avatar_url": "",
        "name": "",
        "access_token": "ghu_other",
    }
    _login_resume(auth_env["client"], created["id"], code="other-code")
    other_id = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    assert other_id != owner_id

    after = store.get(created["id"])
    assert after["user_id"] == owner_id
    assert after == before
    assert auth_env["client"].get(f"/api/analyses/{created['id']}").status_code == 404


def test_invalid_oauth_state_cannot_adopt(auth_env):
    store = auth_env["analyses"]
    record = _completed_anonymous(store)
    start = auth_env["client"].get(
        "/api/auth/github/login",
        params={"analysis_id": record["id"]},
    )
    assert start.status_code == 200

    callback = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"code": "ok-code", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "auth_error=" in callback.headers["location"]
    assert store.get(record["id"])["user_id"] is None


def test_expired_resume_cannot_adopt(auth_env):
    clock = FakeClock()
    auth_env["resume_store"]._client()._now = clock
    store = auth_env["analyses"]
    record = _completed_anonymous(store)

    start = auth_env["client"].get(
        "/api/auth/github/login",
        params={
            "analysis_id": record["id"],
            "repair_path": "/r/o/r/issues/1/diagnosis",
        },
    )
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    clock.advance(RESUME_TTL_SECONDS)

    callback = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"code": "ok-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "auth_error=" not in callback.headers["location"]
    assert store.get(record["id"])["user_id"] is None
    assert auth_env["client"].get("/api/auth/me").json()["authenticated"] is True


def test_missing_resume_cannot_adopt(auth_env):
    store = auth_env["analyses"]
    record = _completed_anonymous(store)
    start = auth_env["client"].get(
        "/api/auth/github/login",
        params={
            "analysis_id": record["id"],
            "repair_path": "/r/o/r/issues/1/diagnosis",
        },
    )
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    oauth = auth_env["auth_store"]._oauth[state]
    auth_env["resume_store"]._client().delete(f"oauth:resume:{oauth.resume_id}")

    callback = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"code": "ok-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "auth_error=" not in callback.headers["location"]
    assert store.get(record["id"])["user_id"] is None


def test_missing_analysis_does_not_break_oauth(auth_env):
    _start, callback, _state = _login_resume(auth_env["client"], "missing-analysis")
    assert callback.status_code == 302
    assert "auth_error=" not in callback.headers["location"]
    assert "analysis_id=missing-analysis" in callback.headers["location"]
    assert auth_env["client"].get("/api/auth/me").json()["authenticated"] is True


def test_return_to_analysis_id_is_not_enough_to_adopt(auth_env):
    store = auth_env["analyses"]
    record = _completed_anonymous(store)
    start = auth_env["client"].get(
        "/api/auth/github/login",
        params={
            "return_to": (
                "http://localhost:59738/r/o/r/issues/1/diagnosis"
                f"?analysis_id={record['id']}"
            ),
            "repair_path": "/r/o/r/issues/1/diagnosis",
        },
    )
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"code": "ok-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert store.get(record["id"])["user_id"] is None


def test_anonymous_create_still_has_no_owner():
    store = AnalysisStore(redis_client=MemoryRedis())
    created = store.create("o", "r", 3)
    assert created["user_id"] is None
    assert store.get(created["id"])["user_id"] is None
    assert store.find_reusable("o", "r", 3)["id"] == created["id"]


def test_authenticated_create_and_find_reusable_are_unchanged():
    store = AnalysisStore(redis_client=MemoryRedis())
    first = store.create("octocat", "private-app", 3, user_id="u1")
    store.mark_completed(first["id"], {"diagnosis": {"root_cause": "x"}})
    second = store.create("octocat", "private-app", 3, user_id="u1")
    alice = store.create("o", "r", 3, user_id="alice")
    bob = store.create("o", "r", 3, user_id="bob")

    assert second["id"] != first["id"]
    assert store.find_reusable(
        "octocat", "private-app", 3, user_id="u1"
    )["id"] == first["id"]
    assert store.find_reusable("octocat", "private-app", 3) is None
    assert store.find_reusable("o", "r", 3, user_id="alice")["id"] == alice["id"]
    assert store.find_reusable("o", "r", 3, user_id="bob")["id"] == bob["id"]
    assert store.find_reusable("o", "r", 3) is None
