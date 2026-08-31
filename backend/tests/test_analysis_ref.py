"""
Analysis jobs can pin a repository ref.

Default remains the current default-branch HEAD. An explicit ref is
resolved to a SHA before the job starts and that SHA is used for
source retrieval. An invalid ref fails the request; HEAD is never
substituted.
"""

from fastapi.testclient import TestClient

from app.dependencies import (
    get_analysis_runner,
    get_analysis_store,
    get_github_service,
)
from app.errors import InvalidRef, RepositoryNotFound, UpstreamUnavailable
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.github_service import GithubService


HEAD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PINNED = "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c"
SHORT = "f0bfc5b"


class FakeGithub:
    def __init__(self):
        self.source_refs = []
        self.commits = {
            "main": HEAD_SHA,
            HEAD_SHA: HEAD_SHA,
            SHORT: PINNED,
            PINNED: PINNED,
        }

    def get_repository(self, owner, repo):
        return {"default_branch": "main"}

    def get_commit(self, owner, repo, branch):
        sha = self.commits.get(branch)
        if sha is None:
            if branch.startswith("not-a-real"):
                raise UpstreamUnavailable(
                    f"GitHub returned 422 for "
                    f"https://api.github.com/repos/{owner}/{repo}"
                    f"/commits/{branch}"
                )
            raise RepositoryNotFound(f"unknown {branch}")
        return {"sha": sha, "commit": {"tree": {"sha": "tree"}}}

    def resolve_commit(self, owner, repo, ref=None):
        return GithubService.resolve_commit(self, owner, repo, ref)

    def get_repository_source_files(self, owner, repo, ref=None):
        self.source_refs.append(ref)
        return [
            {
                "path": "lib/domain/usecases/get_filtered_tasks.dart",
                "sha": "blob",
                "content": "if (task.isCompleted) {",
            }
        ]

    def get_issue(self, owner, repo, issue_number):
        return {
            "number": issue_number,
            "title": "Active filter",
            "body": "shows completed tasks",
            "state": "open",
        }


class FakeRunner:
    def __init__(self, github):
        self.github = github
        self.calls = []

    def run(self, owner, repo, issue_number, on_stage=None, ref=None):
        self.calls.append({
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "ref": ref,
        })
        if on_stage:
            on_stage("fetching_source")
        commit_sha = self.github.resolve_commit(owner, repo, ref)
        files = self.github.get_repository_source_files(
            owner, repo, ref=commit_sha,
        )
        return {
            "issue": {"number": issue_number, "title": "Active filter"},
            "signals": [],
            "relevant_files": [],
            "diagnosis": None,
            "diagnosis_error": None,
            "sources": {
                files[0]["path"]: files[0]["content"],
            },
            "commit_sha": commit_sha,
        }


def _client():
    store = AnalysisStore()
    github = FakeGithub()
    runner = FakeRunner(github)

    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_analysis_runner] = lambda: runner

    client = TestClient(app)
    return client, store, github, runner


def _clear():
    app.dependency_overrides.clear()


def test_omitted_ref_uses_default_branch_head():
    client, store, github, runner = _client()

    try:
        response = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["ref"] is None
        assert body["commit_sha"] is None

        analysis_id = body["id"]
        stored = store.get(analysis_id)
        assert stored["status"] == "completed"
        assert stored["commit_sha"] == HEAD_SHA
        assert runner.calls[0]["ref"] is None
        assert github.source_refs == [HEAD_SHA]

        fetched = client.get(f"/api/analyses/{analysis_id}")
        assert fetched.status_code == 200
        assert fetched.json()["commit_sha"] == HEAD_SHA
        assert fetched.json()["ref"] is None
    finally:
        _clear()


def test_explicit_commit_is_resolved_before_the_job_and_propagated():
    client, store, github, runner = _client()

    try:
        response = client.post(
            "/api/analyses",
            json={
                "owner": "o",
                "repo": "r",
                "issue_number": 3,
                "ref": SHORT,
            },
        )

        assert response.status_code == 202
        body = response.json()
        assert body["ref"] == SHORT
        assert body["commit_sha"] == PINNED

        stored = store.get(body["id"])
        assert stored["ref"] == SHORT
        assert stored["commit_sha"] == PINNED
        assert runner.calls[0]["ref"] == PINNED
        assert github.source_refs == [PINNED]
        assert stored["sources"][
            "lib/domain/usecases/get_filtered_tasks.dart"
        ] == "if (task.isCompleted) {"

        fetched = client.get(f"/api/analyses/{body['id']}")
        assert fetched.json()["ref"] == SHORT
        assert fetched.json()["commit_sha"] == PINNED
    finally:
        _clear()


def test_commit_alias_is_accepted():
    client, store, github, runner = _client()

    try:
        response = client.post(
            "/api/analyses",
            json={
                "owner": "o",
                "repo": "r",
                "issue_number": 3,
                "commit": PINNED,
            },
        )

        assert response.status_code == 202
        assert response.json()["ref"] == PINNED
        assert response.json()["commit_sha"] == PINNED
        assert runner.calls[0]["ref"] == PINNED
        assert github.source_refs == [PINNED]
    finally:
        _clear()


def test_invalid_ref_fails_before_analysis():
    client, store, github, runner = _client()

    try:
        response = client.post(
            "/api/analyses",
            json={
                "owner": "o",
                "repo": "r",
                "issue_number": 3,
                "ref": "not-a-real-ref",
            },
        )

        assert response.status_code == 400
        assert "not-a-real-ref" in response.json()["detail"]
        assert "not started" in response.json()["detail"]
        assert runner.calls == []
        assert github.source_refs == []
        assert store._analyses == {}
    finally:
        _clear()


def test_invalid_ref_never_falls_back_to_head():
    github = FakeGithub()

    try:
        GithubService.resolve_commit(github, "o", "r", "not-a-real-ref")
        assert False, "expected InvalidRef"
    except InvalidRef as exc:
        assert "not-a-real-ref" in str(exc)

    assert github.source_refs == []
    assert GithubService.resolve_commit(github, "o", "r", None) == HEAD_SHA


def test_disagreeing_ref_and_commit_are_rejected():
    client, _store, _github, runner = _client()

    try:
        response = client.post(
            "/api/analyses",
            json={
                "owner": "o",
                "repo": "r",
                "issue_number": 3,
                "ref": SHORT,
                "commit": HEAD_SHA,
            },
        )

        assert response.status_code == 422
        assert runner.calls == []
    finally:
        _clear()
