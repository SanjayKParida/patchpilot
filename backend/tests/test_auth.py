"""GitHub App login, sessions, and repository authorization."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.application.auth_service import AuthService
from app.application.patch_delivery_service import PatchDeliveryService
from app.application.repository_access import RepositoryAccess
from app.config import SESSION_COOKIE_NAME, Settings
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
from app.domain.auth import AuthorizedRepository
from app.infrastructure.github_app_client import (
    GithubAppClient,
    sanitize_oauth_authorize_url,
)
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.auth_store import AuthStore
from app.services.oauth_resume_store import OAuthResumeStore
from tests.fakes.github_app_client import FakeGitHubAppClient
from tests.fakes.memory_redis import MemoryRedis
from tests.fakes.github_write_client import FakeGithub, FakeGithubWriteClient


def _settings(**overrides):
    values = dict(
        github_token="gho_demo_read_only",
        github_app_id="1",
        github_app_client_id="iv1.test",
        github_app_client_secret="secret",
        github_app_private_key="-----BEGIN KEY-----\nM\n-----END KEY-----",
        github_app_slug="patchpilot-dev",
        github_app_redirect_uri="http://localhost:8000/api/auth/github/callback",
        session_secret="test-session-secret",
        session_ttl_seconds=3600,
        cookie_secure=False,
        cookie_samesite="lax",
        demo_owner="SanjayKParida",
        demo_repo="patchpilot-diagnosis-demo",
        demo_description="Try PatchPilot on prepared issues",
        frontend_origin="http://localhost:59738",
        cors_origins=None,
        redis_url=None,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def auth_env():
    settings = _settings()
    auth_store = AuthStore(session_ttl_seconds=settings.session_ttl_seconds)
    github_app = FakeGitHubAppClient()
    resume_store = OAuthResumeStore(redis_client=MemoryRedis())
    auth = AuthService(auth_store, github_app, settings, resume_store=resume_store)
    access = RepositoryAccess(auth_store, settings, github_app)
    analyses = AnalysisStore()
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
            "settings": settings,
            "auth_store": auth_store,
            "github_app": github_app,
            "auth": auth,
            "access": access,
            "analyses": analyses,
            "writer": writer,
            "resume_store": resume_store,
        }

    app.dependency_overrides.clear()


def _login(client, code="ok-code"):
    start = client.get("/api/auth/github/login")
    assert start.status_code == 200
    url = start.json()["authorization_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    response = client.get(
        "/api/auth/github/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    return start, response


EXPECTED_CALLBACK = "http://localhost:8000/api/auth/github/callback"


def _authorize_query(url):
    parsed = urlparse(url)
    return parsed, parse_qs(parsed.query, keep_blank_values=True)


def _assert_github_app_web_flow(url, *, expected_client_id=None):
    parsed, query = _authorize_query(url)
    assert parsed.scheme == "https"
    assert parsed.hostname == "github.com"
    assert parsed.path == "/login/oauth/authorize"
    assert query["client_id"][0]
    if expected_client_id is not None:
        assert query["client_id"] == [expected_client_id]
    assert query["redirect_uri"] == [EXPECTED_CALLBACK]
    assert query["state"][0]
    assert query["code_challenge"][0]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query) == {
        "client_id",
        "redirect_uri",
        "state",
        "code_challenge",
        "code_challenge_method",
    }


def test_github_app_authorization_url_matches_web_flow():
    client = GithubAppClient(_settings())
    url = client.authorization_url(
        state="oauth-state",
        code_challenge="a" * 43,
    )
    _assert_github_app_web_flow(url, expected_client_id="iv1.test")
    _, query = _authorize_query(url)
    assert query["state"] == ["oauth-state"]
    assert query["code_challenge"] == ["a" * 43]


def test_login_endpoint_authorization_url_matches_web_flow():
    settings = _settings()
    store = AuthStore(session_ttl_seconds=settings.session_ttl_seconds)
    github_app = GithubAppClient(settings)
    auth = AuthService(store, github_app, settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_store] = lambda: store
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_github_app_client] = lambda: github_app
    try:
        with TestClient(app) as client:
            response = client.get("/api/auth/github/login")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    _assert_github_app_web_flow(
        response.json()["authorization_url"],
        expected_client_id="iv1.test",
    )


def test_sanitize_oauth_authorize_url_names_only():
    url = (
        "https://github.com/login/oauth/authorize"
        "?client_id=Iv23secret"
        "&redirect_uri=http://localhost:8000/api/auth/github/callback"
        "&state=super-secret-state"
        "&code_challenge=challenge-value"
        "&code_challenge_method=S256"
    )
    described = sanitize_oauth_authorize_url(url)
    blob = str(described)
    assert "Iv23secret" not in blob
    assert "super-secret-state" not in blob
    assert "challenge-value" not in blob
    assert described["hostname"] == "github.com"
    assert described["path"] == "/login/oauth/authorize"
    assert described["parameter_names"] == [
        "client_id",
        "code_challenge",
        "code_challenge_method",
        "redirect_uri",
        "state",
    ]
    assert described["required_present"] == {
        "client_id": True,
        "redirect_uri": True,
        "state": True,
        "code_challenge": True,
        "code_challenge_method": True,
    }
    assert described["unexpected_parameters"] == []
    assert described["code_challenge_method_is_s256"] is True
    assert described["uses_github_authorize_path"] is True
    assert described["redirect_uri_ends_with_callback_path"] is True


def test_login_logs_parameter_presence_not_secrets(caplog):
    settings = _settings()
    store = AuthStore(session_ttl_seconds=settings.session_ttl_seconds)
    github_app = GithubAppClient(settings)
    auth = AuthService(store, github_app, settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_store] = lambda: store
    app.dependency_overrides[get_auth_service] = lambda: auth
    try:
        with TestClient(app) as client:
            with caplog.at_level("INFO", logger="app.api.auth"):
                response = client.get("/api/auth/github/login")
    finally:
        app.dependency_overrides.clear()

    url = response.json()["authorization_url"]
    _, query = _authorize_query(url)
    combined = caplog.text
    assert "GitHub App user-authorization URL" in combined
    assert "parameter_names" in combined
    assert query["state"][0] not in combined
    assert query["code_challenge"][0] not in combined
    assert "iv1.test" not in combined
    assert settings.github_app_client_secret not in combined


def test_unauthenticated_me(auth_env):
    response = auth_env["client"].get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body == {"authenticated": False, "user": None}
    assert "token" not in response.text.lower()
    assert "ghu_" not in response.text
    assert "ghs_" not in response.text


def test_login_callback_success(auth_env):
    start, callback = _login(auth_env["client"])
    assert "code_challenge=" in start.json()["authorization_url"]
    assert callback.status_code == 302
    assert SESSION_COOKIE_NAME in callback.cookies
    assert callback.cookies[SESSION_COOKIE_NAME]
    assert "ghu_user_token" not in callback.text
    assert "connected=1" in callback.headers["location"]
    assert "#session=" in callback.headers["location"]
    fragment = callback.headers["location"].rsplit("#", 1)[-1]
    assert fragment.startswith("session=")
    session_id = fragment.split("=", 1)[1]
    assert len(session_id) == 32

    me = auth_env["client"].get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["authenticated"] is True
    assert body["user"]["github_login"] == "octocat"
    assert "access_token" not in body
    assert "ghu_" not in me.text


def test_invalid_oauth_state(auth_env):
    auth_env["client"].get("/api/auth/github/login")
    response = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"code": "ok-code", "state": "not-the-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=" in response.headers["location"]
    assert SESSION_COOKIE_NAME not in response.cookies
    me = auth_env["client"].get("/api/auth/me")
    assert me.json()["authenticated"] is False


def test_authorization_failure(auth_env):
    start = auth_env["client"].get("/api/auth/github/login")
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    response = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"code": "bad-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=" in response.headers["location"]
    assert auth_env["client"].get("/api/auth/me").json()["authenticated"] is False


def test_session_persists_across_requests(auth_env):
    _login(auth_env["client"])
    first = auth_env["client"].get("/api/auth/me")
    second = auth_env["client"].get("/api/auth/me")
    assert first.json()["user"]["id"] == second.json()["user"]["id"]


def test_bearer_token_authenticates_without_cookie(auth_env):
    callback = _login(auth_env["client"])[1]
    session_id = callback.headers["location"].rsplit("session=", 1)[-1]
    client = auth_env["client"]
    client.cookies.clear()

    anonymous = client.get("/api/auth/me")
    assert anonymous.json()["authenticated"] is False

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {session_id}"},
    )
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["user"]["github_login"] == "octocat"


def test_logout_invalidates_session(auth_env):
    _login(auth_env["client"])
    assert auth_env["client"].get("/api/auth/me").json()["authenticated"] is True
    logout = auth_env["client"].post("/api/auth/logout")
    assert logout.status_code == 200
    me = auth_env["client"].get("/api/auth/me")
    assert me.json()["authenticated"] is False


def test_expired_session(auth_env):
    _login(auth_env["client"])
    store = auth_env["auth_store"]
    session_id = next(iter(store._sessions))
    store._sessions[session_id].expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    me = auth_env["client"].get("/api/auth/me")
    assert me.json()["authenticated"] is False


def test_repeated_login_maps_to_same_github_identity(auth_env):
    _login(auth_env["client"])
    first_id = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    auth_env["client"].post("/api/auth/logout")
    _login(auth_env["client"])
    second = auth_env["client"].get("/api/auth/me").json()["user"]
    assert second["id"] == first_id
    assert second["github_id"] == 4242
    assert len(auth_env["auth_store"]._users_by_github_id) == 1


def test_repository_listing_only_authorized(auth_env):
    _login(auth_env["client"])
    response = auth_env["client"].get("/api/repositories/authorized")
    assert response.status_code == 200
    names = {item["full_name"] for item in response.json()}
    assert names == {"octocat/private-app", "octocat/public-notes"}
    assert "ghu_user_token" not in response.text


def test_private_and_public_repo_authorization(auth_env):
    _login(auth_env["client"])
    repos = {
        item["full_name"]: item
        for item in auth_env["client"].get("/api/repositories/authorized").json()
    }
    private = repos["octocat/private-app"]
    public = repos["octocat/public-notes"]
    assert private["private"] is True
    assert private["can_write"] is True
    assert private["access"] == "write"
    assert public["private"] is False
    assert public["can_write"] is False
    assert public["access"] == "read"


def test_authorized_listing_requires_login(auth_env):
    response = auth_env["client"].get("/api/repositories/authorized")
    assert response.status_code == 401


def test_anonymous_cannot_analyze_a_user_repository(auth_env):
    response = auth_env["client"].post(
        "/api/analyses",
        json={
            "owner": "octocat",
            "repo": "private-app",
            "issue_number": 1,
        },
    )
    assert response.status_code == 401
    assert auth_env["analyses"].find_reusable("octocat", "private-app", 1) is None


def test_demo_repository_available_without_login(auth_env):
    response = auth_env["client"].get("/api/repositories/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["demo"] is True
    assert body["owner"] == "SanjayKParida"
    assert body["repo"] == "patchpilot-diagnosis-demo"
    assert body["can_read"] is True
    assert body["can_write"] is False


def test_user_cannot_access_another_users_analysis(auth_env):
    _login(auth_env["client"])
    user_a = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    record = auth_env["analyses"].create(
        "octocat",
        "private-app",
        1,
        user_id=user_a,
    )
    auth_env["client"].post("/api/auth/logout")

    auth_env["github_app"].users_by_code["other-code"] = {
        "id": 99,
        "login": "other",
        "avatar_url": "",
        "name": "",
        "access_token": "ghu_other",
    }
    _login(auth_env["client"], code="other-code")

    response = auth_env["client"].get(f"/api/analyses/{record['id']}")
    assert response.status_code == 404
    assert auth_env["client"].post(
        f"/api/analyses/{record['id']}/patch/approve"
    ).status_code == 404
    assert auth_env["client"].post(
        f"/api/analyses/{record['id']}/patch/deliver"
    ).status_code == 404


def test_delivery_blocked_for_unauthorized_repository(auth_env):
    _login(auth_env["client"])
    user_id = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    record = auth_env["analyses"].create(
        "octocat",
        "not-granted",
        1,
        user_id=user_id,
        commit_sha="a" * 40,
    )
    auth_env["analyses"].mark_completed(
        record["id"],
        {
            "commit_sha": "a" * 40,
            "snapshot": {"lib/a.dart": "a"},
            "snapshot_commit": "a" * 40,
            "patch_proposal": {"status": "ok", "files": []},
            "patch_validation": {
                "status": "passed",
                "applied": True,
                "validation_passed": True,
                "runnable": True,
            },
        },
    )
    auth_env["analyses"].set_approval(
        record["id"],
        approved_at="2026-01-01T00:00:00+00:00",
        commit_sha="a" * 40,
    )

    response = auth_env["client"].post(f"/api/analyses/{record['id']}/patch/deliver")
    assert response.status_code == 403
    assert auth_env["writer"].write_ops == []


def test_demo_cannot_become_write_token_fallback(auth_env):
    record = auth_env["analyses"].create(
        "SanjayKParida",
        "patchpilot-diagnosis-demo",
        3,
        commit_sha="a" * 40,
    )
    auth_env["analyses"].mark_completed(
        record["id"],
        {
            "commit_sha": "a" * 40,
            "snapshot": {"lib/a.dart": "a"},
            "snapshot_commit": "a" * 40,
            "patch_proposal": {"status": "ok", "files": []},
            "patch_validation": {
                "status": "passed",
                "applied": True,
                "validation_passed": True,
                "runnable": True,
            },
        },
    )
    auth_env["analyses"].set_approval(
        record["id"],
        approved_at="2026-01-01T00:00:00+00:00",
        commit_sha="a" * 40,
    )

    response = auth_env["client"].post(f"/api/analyses/{record['id']}/patch/deliver")
    assert response.status_code == 403
    assert "write" in response.json()["detail"].lower() or "draft PR" in response.json()["detail"]
    assert auth_env["writer"].write_ops == []
    assert auth_env["access"].github_token_for(
        "SanjayKParida",
        "patchpilot-diagnosis-demo",
        None,
        write=False,
    ) == "gho_demo_read_only"

    with pytest.raises(Exception):
        auth_env["access"].github_token_for(
            "SanjayKParida",
            "patchpilot-diagnosis-demo",
            None,
            write=True,
        )


def test_github_credentials_never_returned_to_client(auth_env):
    _login(auth_env["client"])
    bodies = [
        auth_env["client"].get("/api/auth/me").text,
        auth_env["client"].get("/api/repositories/authorized").text,
        auth_env["client"].get("/api/repositories/demo").text,
        auth_env["client"].get("/api/auth/github/login").text,
    ]
    combined = "\n".join(bodies)
    assert "ghu_" not in combined
    assert "ghs_" not in combined
    assert "gho_demo_read_only" not in combined
    assert "iv1.test" in auth_env["client"].get("/api/auth/github/login").text
    assert "client_secret" not in combined
    assert "access_token" not in combined


def test_install_url_requires_login(auth_env):
    response = auth_env["client"].get("/api/auth/github/install")
    assert response.status_code == 401


def test_install_url_uses_app_slug(auth_env):
    _login(auth_env["client"])
    response = auth_env["client"].get("/api/auth/github/install")
    assert response.status_code == 200
    url = response.json()["installation_url"]
    parsed = urlparse(url)
    assert parsed.hostname == "github.com"
    assert parsed.path == "/apps/patchpilot-dev/installations/new"
    assert parse_qs(parsed.query)["state"][0]
    assert "client_secret" not in url
    assert "ghu_" not in url


def test_authorized_refresh_requires_login(auth_env):
    response = auth_env["client"].post("/api/repositories/authorized/refresh")
    assert response.status_code == 401


def test_authorized_refresh_rereads_installations(auth_env):
    _login(auth_env["client"])
    auth_env["github_app"].installations = []
    empty = auth_env["client"].post("/api/repositories/authorized/refresh")
    assert empty.status_code == 200
    assert empty.json() == []
    assert auth_env["client"].get("/api/repositories/authorized").json() == []

    extra = {
        "id": 3,
        "name": "added-later",
        "full_name": "octocat/added-later",
        "private": False,
        "description": "",
        "html_url": "https://github.com/octocat/added-later",
        "default_branch": "main",
        "owner": {"login": "octocat"},
        "permissions": {"pull": True, "push": True, "admin": False},
    }
    auth_env["github_app"].installations = [{"id": 77}]
    auth_env["github_app"].repositories_by_installation[77].append(extra)
    refreshed = auth_env["client"].post("/api/repositories/authorized/refresh")
    names = {item["full_name"] for item in refreshed.json()}
    assert "octocat/added-later" in names
    assert "octocat/private-app" in names


def test_empty_installation_lists_no_user_repositories(auth_env):
    _login(auth_env["client"])
    auth_env["github_app"].installations = []
    auth_env["github_app"].repositories_by_installation = {}
    response = auth_env["client"].post("/api/repositories/authorized/refresh")
    assert response.status_code == 200
    assert response.json() == []


def test_install_callback_without_code_refreshes_grants(auth_env):
    _login(auth_env["client"])
    auth_env["github_app"].installations = []
    auth_env["client"].post("/api/repositories/authorized/refresh")
    assert auth_env["client"].get("/api/repositories/authorized").json() == []

    auth_env["github_app"].installations = [{"id": 77}]
    start = auth_env["client"].get("/api/auth/github/install")
    state = parse_qs(
        urlparse(start.json()["installation_url"]).query
    )["state"][0]
    callback = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"installation_id": "77", "setup_action": "install", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "connected=1" in callback.headers["location"]
    assert "auth_error=" not in callback.headers["location"]
    names = {
        item["full_name"]
        for item in auth_env["client"].get("/api/repositories/authorized").json()
    }
    assert names == {"octocat/private-app", "octocat/public-notes"}


def test_install_callback_without_session_redirects_to_error(auth_env):
    response = auth_env["client"].get(
        "/api/auth/github/callback",
        params={"installation_id": "77", "setup_action": "install"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=" in response.headers["location"]


def test_user_cannot_see_another_users_repositories(auth_env):
    _login(auth_env["client"])
    first_user = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    first_repos = auth_env["auth_store"].list_repositories(first_user)
    assert first_repos

    auth_env["client"].post("/api/auth/logout")
    auth_env["github_app"].installations = []
    auth_env["github_app"].users_by_code["other-code"] = {
        "id": 99,
        "login": "other",
        "avatar_url": "",
        "name": "",
        "access_token": "ghu_other",
    }
    _login(auth_env["client"], code="other-code")
    second = auth_env["client"].get("/api/auth/me").json()["user"]["id"]
    assert second != first_user
    assert auth_env["client"].get("/api/repositories/authorized").json() == []
    assert auth_env["auth_store"].list_repositories(first_user)
    assert {item.full_name for item in first_repos} == {
        "octocat/private-app",
        "octocat/public-notes",
    }


def test_login_callback_preserves_repair_path(auth_env):
    client = auth_env["client"]
    repair = "http://localhost:59738/r/owner/repo/issues/1/diagnosis"
    start = client.get(
        "/api/auth/github/login",
        params={
            "return_to": repair,
            "analysis_id": "analysis-abc",
            "stage": "diagnosis",
            "repair_path": "/r/owner/repo/issues/1/diagnosis",
        },
    )
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    oauth = auth_env["auth_store"]._oauth[state]
    assert oauth.resume_id
    assert oauth.return_to.startswith(repair)

    stored = auth_env["resume_store"]._client().get(
        f"oauth:resume:{oauth.resume_id}"
    )
    assert stored
    resume_id = oauth.resume_id

    callback = client.get(
        "/api/auth/github/callback",
        params={"code": "ok-code", "state": state},
        follow_redirects=False,
    )
    location = callback.headers["location"]
    assert callback.status_code == 302
    assert "/r/owner/repo/issues/1/diagnosis" in location
    assert "analysis_id=analysis-abc" in location
    assert "connected=1" in location
    assert "#session=" in location
    assert "auth_error=" not in location
    assert auth_env["resume_store"].consume(resume_id) is None


def test_install_callback_preserves_repair_path(auth_env):
    client = auth_env["client"]
    _login(client)
    repair = "http://localhost:59738/r/owner/repo/issues/1/pull-request"
    start = client.get(
        "/api/auth/github/install",
        params={"return_to": repair},
    )
    state = parse_qs(
        urlparse(start.json()["installation_url"]).query
    )["state"][0]
    callback = client.get(
        "/api/auth/github/callback",
        params={
            "installation_id": "77",
            "setup_action": "install",
            "state": state,
        },
        follow_redirects=False,
    )
    location = callback.headers["location"]
    assert callback.status_code == 302
    assert "/r/owner/repo/issues/1/pull-request" in location
    assert "connected=1" in location
    assert "auth_error=" not in location
