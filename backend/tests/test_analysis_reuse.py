"""A completed diagnosis is returned instead of starting another run."""

from fastapi.testclient import TestClient

from app.dependencies import (
    get_analysis_runner,
    get_analysis_store,
    get_github_service,
)
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.github_service import GithubService


HEAD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PINNED = "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c"


class FakeGithub:
    def get_repository(self, owner, repo):
        return {"default_branch": "main"}

    def get_commit(self, owner, repo, branch):
        shas = {"main": HEAD_SHA, HEAD_SHA: HEAD_SHA, PINNED: PINNED}
        sha = shas.get(branch)
        if sha is None:
            raise Exception(f"unknown {branch}")
        return {"sha": sha, "commit": {"tree": {"sha": "tree"}}}

    def resolve_commit(self, owner, repo, ref=None):
        return GithubService.resolve_commit(self, owner, repo, ref)

    def get_repository_source_files(self, owner, repo, ref=None):
        return [{"path": "lib/a.dart", "sha": "blob", "content": "a"}]

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
        self.calls.append(issue_number)
        if on_stage:
            on_stage("diagnosing")
        return {
            "issue": {"number": issue_number, "title": "Active filter"},
            "signals": [],
            "relevant_files": [],
            "diagnosis": {
                "root_cause": "filter inverted",
                "confidence": 0.9,
                "explanation": "isCompleted used for Active",
                "suggested_fix": "invert the predicate",
                "cited_files": ["lib/a.dart"],
            },
            "diagnosis_error": None,
            "sources": {"lib/a.dart": "a"},
            "commit_sha": self.github.resolve_commit(owner, repo, ref),
        }


def _client():
    store = AnalysisStore()
    github = FakeGithub()
    runner = FakeRunner(github)

    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_analysis_runner] = lambda: runner

    return TestClient(app), store, runner


def _clear():
    app.dependency_overrides.clear()


def test_second_post_returns_the_completed_analysis():
    client, _store, runner = _client()

    try:
        first = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3},
        )
        second = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3},
        )

        assert first.status_code == 202
        assert second.status_code == 202
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["status"] == "completed"
        assert second.json()["diagnosis"]["root_cause"] == "filter inverted"
        assert runner.calls == [3]
    finally:
        _clear()


def test_force_starts_a_new_analysis():
    client, _store, runner = _client()

    try:
        first = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3},
        )
        second = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3, "force": True},
        )

        assert second.json()["id"] != first.json()["id"]
        assert runner.calls == [3, 3]
    finally:
        _clear()


def test_a_different_issue_is_a_new_analysis():
    client, _store, runner = _client()

    try:
        first = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3},
        )
        second = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 1},
        )

        assert second.json()["id"] != first.json()["id"]
        assert runner.calls == [3, 1]
    finally:
        _clear()


def test_a_different_commit_is_a_new_analysis():
    client, _store, runner = _client()

    try:
        first = client.post(
            "/api/analyses",
            json={"owner": "o", "repo": "r", "issue_number": 3},
        )
        second = client.post(
            "/api/analyses",
            json={
                "owner": "o",
                "repo": "r",
                "issue_number": 3,
                "ref": PINNED,
            },
        )

        assert second.json()["id"] != first.json()["id"]
        assert second.json()["commit_sha"] == PINNED
        assert runner.calls == [3, 3]
    finally:
        _clear()


def test_failed_analysis_is_not_reused():
    store = AnalysisStore()
    failed = store.create("o", "r", 3)
    store.mark_failed(failed["id"], "boom")

    reused = store.find_reusable("o", "r", 3)
    assert reused is None
