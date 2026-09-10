"""
Repository snapshots are cached by exact (owner, repo, commit_sha).

No GitHub network. Ranking still sees language-filtered files derived
from the tracked snapshot.
"""

import threading

import pytest
from fastapi.testclient import TestClient

from app.config import SESSION_COOKIE_NAME, Settings
from app.application.repository_access import RepositoryAccess
from app.dependencies import (
    get_analysis_store,
    get_auth_store,
    get_github_service,
    get_repository_access,
    get_repository_snapshot_store,
    get_settings,
)
from app.domain.auth import AuthorizedRepository
from app.errors import InvalidRef, SnapshotPreparationInProgress
from app.main import app
from app.services.analysis_runner import AnalysisRunner
from app.services.analysis_store import AnalysisStore
from app.services.auth_store import AuthStore
from app.services.github_service import GithubService
from app.services.repository_snapshot import (
    prepare_repository_snapshot,
    source_files_from_tracked,
)
from app.services.repository_snapshot_store import RepositorySnapshotStore


HEAD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PINNED = "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c"
SHORT = "f0bfc5b"
OTHER_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

TRACKED = [
    {
        "path": "lib/main.dart",
        "sha": "dart",
        "content": "void main() {}\n",
    },
    {
        "path": "pubspec.yaml",
        "sha": "yaml",
        "content": "name: demo\n",
    },
]


class CountingGithub:
    def __init__(self, block=False):
        self.tracked_refs = []
        self.block = block
        self.started = threading.Event()
        self.release = threading.Event()
        self.commits = {
            "main": HEAD_SHA,
            HEAD_SHA: HEAD_SHA,
            SHORT: PINNED,
            PINNED: PINNED,
            OTHER_SHA: OTHER_SHA,
        }

    def get_repository(self, owner, repo):
        return {"default_branch": "main"}

    def get_commit(self, owner, repo, branch):
        sha = self.commits.get(branch)
        if sha is None:
            if str(branch).startswith("not-a-real"):
                from app.errors import UpstreamUnavailable

                raise UpstreamUnavailable(
                    f"GitHub returned 422 for "
                    f"https://api.github.com/repos/{owner}/{repo}"
                    f"/commits/{branch}"
                )
            from app.errors import RepositoryNotFound

            raise RepositoryNotFound(f"unknown {branch}")
        return {"sha": sha, "commit": {"tree": {"sha": "tree"}}}

    def resolve_commit(self, owner, repo, ref=None):
        return GithubService.resolve_commit(self, owner, repo, ref)

    def get_issue(self, owner, repo, issue_number):
        return {
            "number": issue_number,
            "title": "Spinner stuck",
            "body": "Refresh never completes.",
            "state": "open",
        }

    def get_repository_tracked_files(self, owner, repo, ref=None, on_progress=None, **kwargs):
        self.tracked_refs.append(ref)
        self.started.set()
        if self.block:
            assert self.release.wait(timeout=5)
        return list(TRACKED)

    def get_repository_source_files(self, owner, repo, ref=None):
        raise AssertionError(
            "source files must be derived from the tracked snapshot"
        )


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


# ============================================================
# STORE
# ============================================================

def test_first_prepare_downloads_once():
    store = RepositorySnapshotStore()
    github = CountingGithub()

    sha, files, status = prepare_repository_snapshot(
        github, store, "o", "r",
    )

    assert sha == HEAD_SHA
    assert status == "ready"
    assert github.tracked_refs == [HEAD_SHA]
    assert [item["path"] for item in files] == [
        "lib/main.dart",
        "pubspec.yaml",
    ]


def test_second_prepare_for_same_sha_is_a_cache_hit():
    store = RepositorySnapshotStore()
    github = CountingGithub()

    first = prepare_repository_snapshot(github, store, "o", "r")
    second = prepare_repository_snapshot(github, store, "o", "r")

    assert first[0] == second[0] == HEAD_SHA
    assert github.tracked_refs == [HEAD_SHA]
    assert [item["path"] for item in second[1]] == [
        item["path"] for item in first[1]
    ]


def test_different_sha_downloads_separately():
    store = RepositorySnapshotStore()
    github = CountingGithub()

    prepare_repository_snapshot(github, store, "o", "r")
    prepare_repository_snapshot(github, store, "o", "r", ref=PINNED)

    assert github.tracked_refs == [HEAD_SHA, PINNED]


def test_concurrent_same_sha_requests_do_not_double_fetch():
    store = RepositorySnapshotStore()
    github = CountingGithub(block=True)
    results = []

    def wait_and_fetch():
        results.append(
            prepare_repository_snapshot(
                github, store, "o", "r", wait=True,
            )
        )

    first = threading.Thread(target=wait_and_fetch)
    first.start()
    assert github.started.wait(timeout=5)

    status, files = store.get_or_fetch(
        "o", "r", HEAD_SHA, lambda: (_ for _ in ()).throw(
            AssertionError("second caller started a download")
        ),
        wait=False,
    )
    assert status == "running"
    assert files is None

    with pytest.raises(SnapshotPreparationInProgress):
        prepare_repository_snapshot(
            github, store, "o", "r", wait=False,
        )

    github.release.set()
    first.join(timeout=5)
    assert results[0][0] == HEAD_SHA
    assert github.tracked_refs == [HEAD_SHA]

    cached = prepare_repository_snapshot(github, store, "o", "r")
    assert cached[0] == HEAD_SHA
    assert github.tracked_refs == [HEAD_SHA]


def test_lru_eviction_drops_the_oldest_snapshot():
    store = RepositorySnapshotStore(max_entries=2)
    calls = []

    def load(label):
        def _load():
            calls.append(label)
            return [{"path": f"{label}.dart", "content": label}]
        return _load

    store.get_or_fetch("o", "r", "sha-a", load("a"))
    store.get_or_fetch("o", "r", "sha-b", load("b"))
    store.get_or_fetch("o", "r", "sha-c", load("c"))

    assert calls == ["a", "b", "c"]
    assert store.inspect("o", "r", "sha-a")[0] == "missing"
    assert store.inspect("o", "r", "sha-b")[0] == "ready"
    assert store.inspect("o", "r", "sha-c")[0] == "ready"

    store.get_or_fetch("o", "r", "sha-a", load("a-again"))
    assert calls == ["a", "b", "c", "a-again"]
    assert store.inspect("o", "r", "sha-b")[0] == "missing"


def test_source_files_are_derived_from_tracked_snapshot():
    files = source_files_from_tracked(TRACKED)
    assert [item["path"] for item in files] == ["lib/main.dart"]


def test_invalid_ref_never_falls_back_to_head():
    store = RepositorySnapshotStore()
    github = CountingGithub()

    with pytest.raises(InvalidRef) as exc:
        prepare_repository_snapshot(
            github, store, "o", "r", ref="not-a-real-ref",
        )

    assert "not-a-real-ref" in str(exc.value)
    assert github.tracked_refs == []
    assert GithubService.resolve_commit(github, "o", "r", None) == HEAD_SHA


# ============================================================
# ANALYSIS RUNNER
# ============================================================

def _stub_analyze(monkeypatch):
    analysis = {
        "signals": [],
        "ranked": [],
        "direct_evidence": [],
    }
    monkeypatch.setattr(
        "app.services.analysis_runner.build_analyze_issue_service",
        lambda files, llm_service=None: type(
            "AnalyzeStub",
            (),
            {
                "analyze": lambda self, files, issue, available_n=10: analysis,
            },
        )(),
    )


def test_two_analyses_at_same_sha_share_one_download(monkeypatch):
    _stub_analyze(monkeypatch)
    store = RepositorySnapshotStore()
    github = CountingGithub()
    runner = AnalysisRunner(
        github_service=github,
        llm_service=None,
        snapshot_store=store,
    )

    first = runner.run("o", "r", 1)
    second = runner.run("o", "r", 2)

    assert github.tracked_refs == [HEAD_SHA]
    assert first["commit_sha"] == second["commit_sha"] == HEAD_SHA
    assert first["snapshot_commit"] == HEAD_SHA
    assert first["snapshot"]["pubspec.yaml"] == "name: demo\n"
    assert "pubspec.yaml" not in first["sources"]
    assert "lib/main.dart" in first["snapshot"]
    assert second["snapshot"]["lib/main.dart"] == "void main() {}\n"


def test_analysis_at_a_different_sha_downloads_again(monkeypatch):
    _stub_analyze(monkeypatch)
    store = RepositorySnapshotStore()
    github = CountingGithub()
    runner = AnalysisRunner(
        github_service=github,
        llm_service=None,
        snapshot_store=store,
    )

    runner.run("o", "r", 1)
    runner.run("o", "r", 2, ref=PINNED)

    assert github.tracked_refs == [HEAD_SHA, PINNED]


# ============================================================
# HTTP
# ============================================================

@pytest.fixture
def snapshot_api():
    store = RepositorySnapshotStore()
    github = CountingGithub()
    analyses = AnalysisStore()

    app.dependency_overrides[get_repository_snapshot_store] = lambda: store
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_analysis_store] = lambda: analyses

    with TestClient(app) as client:
        yield client, store, github

    app.dependency_overrides.clear()


def test_post_snapshot_returns_metadata_only(snapshot_api):
    client, _store, github = snapshot_api

    response = client.post("/api/repositories/o/r/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "commit_sha": HEAD_SHA,
        "status": "ready",
        "file_count": 2,
        "progress_percent": 100,
        "files_downloaded": 2,
        "files_total": 2,
    }
    assert "files" not in body
    assert "content" not in response.text
    assert github.tracked_refs == [HEAD_SHA]


def test_second_post_snapshot_is_a_cache_hit(snapshot_api):
    client, _store, github = snapshot_api

    first = client.post("/api/repositories/o/r/snapshot")
    second = client.post("/api/repositories/o/r/snapshot")

    assert first.json() == second.json()
    assert github.tracked_refs == [HEAD_SHA]


def test_get_snapshot_ready_running_missing(snapshot_api):
    client, store, github = snapshot_api

    missing = client.get("/api/repositories/o/r/snapshot")
    assert missing.status_code == 200
    assert missing.json()["status"] == "missing"
    assert missing.json()["commit_sha"] == HEAD_SHA
    assert missing.json()["file_count"] == 0
    assert github.tracked_refs == []

    github.block = True
    github.started.clear()
    github.release.clear()

    def prepare():
        results.append(client.post("/api/repositories/o/r/snapshot"))

    results = []
    thread = threading.Thread(target=prepare)
    thread.start()
    assert github.started.wait(timeout=5)

    running = client.get("/api/repositories/o/r/snapshot")
    assert running.status_code == 200
    assert running.json()["status"] == "running"
    assert running.json()["file_count"] == 0
    assert running.json()["progress_percent"] >= 0

    conflict = client.post("/api/repositories/o/r/snapshot")
    assert conflict.status_code == 409
    assert "already running" in conflict.json()["detail"]

    github.release.set()
    thread.join(timeout=5)
    assert results[0].status_code == 200

    ready = client.get("/api/repositories/o/r/snapshot")
    assert ready.json()["status"] == "ready"
    assert ready.json()["file_count"] == 2
    assert "pubspec.yaml" not in ready.text


def test_post_snapshot_invalid_ref_is_400(snapshot_api):
    client, _store, github = snapshot_api

    response = client.post(
        "/api/repositories/o/r/snapshot",
        params={"ref": "not-a-real-ref"},
    )

    assert response.status_code == 400
    assert "not-a-real-ref" in response.json()["detail"]
    assert github.tracked_refs == []


def test_post_snapshot_explicit_ref_caches_resolved_sha(snapshot_api):
    client, store, github = snapshot_api

    response = client.post(
        "/api/repositories/o/r/snapshot",
        params={"ref": SHORT},
    )

    assert response.status_code == 200
    assert response.json()["commit_sha"] == PINNED
    assert github.tracked_refs == [PINNED]
    assert store.inspect("o", "r", PINNED)[0] == "ready"
    assert store.inspect("o", "r", HEAD_SHA)[0] == "missing"


def test_demo_snapshot_is_available_without_login():
    store = RepositorySnapshotStore()
    github = CountingGithub()
    settings = _settings()
    access = RepositoryAccess(AuthStore(), settings)
    access.github_service_for = lambda owner, repo, session, write=False: github

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_repository_access] = lambda: access
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_repository_snapshot_store] = lambda: store

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/repositories/SanjayKParida/"
                "patchpilot-diagnosis-demo/snapshot"
            )
            assert response.status_code == 200
            assert response.json()["status"] == "ready"
            denied = client.post("/api/repositories/octocat/private-app/snapshot")
            assert denied.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_authorized_snapshot_works_after_grant():
    store = RepositorySnapshotStore()
    github = CountingGithub()
    settings = _settings()
    auth_store = AuthStore(session_ttl_seconds=settings.session_ttl_seconds)
    access = RepositoryAccess(auth_store, settings)
    access.github_service_for = lambda owner, repo, session, write=False: github

    user = auth_store.upsert_github_user(
        github_id=1,
        github_login="octocat",
        github_access_token="ghu",
    )
    session = auth_store.create_session(user.id)
    auth_store.replace_repositories(
        user.id,
        [
            AuthorizedRepository(
                owner="octocat",
                repo="private-app",
                full_name="octocat/private-app",
                github_repo_id=1,
                installation_id=1,
                private=True,
                can_read=True,
                can_write=True,
            )
        ],
    )

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_store] = lambda: auth_store
    app.dependency_overrides[get_repository_access] = lambda: access
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_repository_snapshot_store] = lambda: store

    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE_NAME, session.id)
            allowed = client.post("/api/repositories/octocat/private-app/snapshot")
            assert allowed.status_code == 200
            other = client.post("/api/repositories/someone/else/snapshot")
            assert other.status_code == 403
    finally:
        app.dependency_overrides.clear()
