"""
Production wiring for ContextBuilder in AnalysisRunner and the API.

Uses fakes only — no GitHub, no real LLM, no network.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.code_intelligence.types import (
    BudgetUsage,
    ContextPackage,
    ContextSlice,
    FileRollup,
    OmittedEntry,
)
from app.dependencies import get_analysis_store
from app.main import app
from app.services.analysis_runner import AnalysisRunner
from app.services.analysis_store import AnalysisStore
from app.services.issue_diagnosis_service import IssueDiagnosisService


ISSUE = {
    "number": 1,
    "title": "Spinner stuck",
    "body": "Refresh never completes.",
    "state": "open",
    "html_url": "https://example.test/issues/1",
    "comments": 0,
}

FILES = [
    {
        "path": "lib/bloc/task_state.dart",
        "sha": "state",
        "content": (
            "abstract class TaskState {}\n"
            "class TaskLoading extends TaskState {}\n"
            "class TaskLoaded extends TaskState {\n"
            "  TaskLoaded(this.tasks);\n"
            "  final List<dynamic> tasks;\n"
            "}\n"
        ),
    },
    {
        "path": "lib/bloc/task_bloc.dart",
        "sha": "bloc",
        "content": (
            "class TaskBloc {\n"
            "  Future<void> refresh() async {\n"
            "    // missing emit\n"
            "  }\n"
            "}\n"
        ),
    },
]

ANALYSIS = {
    "signals": [{"term": "refresh", "type": "behavior"}],
    "ranked": [
        {
            "rank": 1,
            "path": "lib/bloc/task_bloc.dart",
            "sha": "bloc",
            "total_score": 1.0,
            "signals_matched": 1,
        },
        {
            "rank": 2,
            "path": "lib/bloc/task_state.dart",
            "sha": "state",
            "total_score": 0.8,
            "signals_matched": 1,
        },
    ],
    "direct_evidence": [
        {
            "file": {"path": "lib/bloc/task_bloc.dart"},
            "evidence_type": "class",
            "concept": "refresh",
            "strength": 1.0,
            "line": 1,
            "identifier": "TaskBloc",
        }
    ],
    "structural_results": [
        {
            "source": "lib/bloc/task_bloc.dart",
            "target": "lib/bloc/task_state.dart",
            "relationship": "imports",
            "distance": 1,
        }
    ],
}

DIAGNOSIS = {
    "root_cause": "TaskBloc never emits TaskLoaded on refresh.",
    "confidence": 0.9,
    "relevant_files": ["lib/bloc/task_bloc.dart"],
    "explanation": "Refresh handler stops in TaskLoading.",
    "suggested_fix": "emit(TaskLoaded) after refresh succeeds.",
    "root_cause_symbols": ["TaskBloc"],
    "symbols": ["TaskLoading"],
}


class FakeGithub:
    def __init__(self):
        self.source_refs = []
        self.tracked_refs = []

    def get_issue(self, owner, repo, issue_number):
        return ISSUE

    def resolve_commit(self, owner, repo, ref=None):
        return ref or "headsha"

    def get_repository_source_files(self, owner, repo, ref=None):
        self.source_refs.append(ref)
        return FILES

    def get_repository_tracked_files(self, owner, repo, ref=None, on_progress=None, **kwargs):
        self.tracked_refs.append(ref)
        return FILES + [
            {
                "path": "pubspec.yaml",
                "sha": "yaml",
                "content": "name: demo\n",
            }
        ]


class FakeLLM:
    def ask(self, prompt):
        return json.dumps(DIAGNOSIS)


class RecordingContextBuilder:
    def __init__(self, package=None, error=None):
        self.package = package
        self.error = error
        self.last_kwargs = None

    def build(self, **kwargs):
        self.last_kwargs = kwargs

        if self.error is not None:
            raise self.error

        if self.package is not None:
            return self.package

        return ContextPackage(
            slices=[
                ContextSlice(
                    path="lib/bloc/task_bloc.dart",
                    start_line=1,
                    end_line=4,
                    tier=0,
                    reason="declares TaskBloc, named as the defect site",
                    symbols=("TaskBloc",),
                    content="class TaskBloc {\n  Future<void> refresh() async {\n",
                    truncated=False,
                    language="dart",
                    adapter="DartCodeIntelligence",
                )
            ],
            files=[
                FileRollup(
                    path="lib/bloc/task_bloc.dart",
                    total_lines=4,
                    included_lines=2,
                    complete=False,
                )
            ],
            omitted=[
                OmittedEntry(
                    path="lib/bloc/task_state.dart",
                    reason="budget",
                )
            ],
            warnings=[],
            budget=BudgetUsage(
                max_files=12,
                files_used=1,
                max_lines_total=1200,
                lines_used=2,
                estimated_tokens=10,
                over_budget=False,
            ),
            language="dart",
            adapter="DartCodeIntelligence",
            issue=kwargs.get("issue"),
            diagnosis=kwargs.get("diagnosis"),
            root_cause={
                "symbol": "TaskBloc",
                "path": "lib/bloc/task_bloc.dart",
                "line": 1,
                "kind": "class",
            },
        )


def _sample_context_dict():
    return RecordingContextBuilder().build(
        issue=ISSUE,
        diagnosis=DIAGNOSIS,
        ranked=ANALYSIS["ranked"],
        graph=None,
        files=FILES,
    ).to_dict()


@pytest.fixture
def api_client():
    store = AnalysisStore()
    app.dependency_overrides[get_analysis_store] = lambda: store

    with TestClient(app) as client:
        yield client, store

    app.dependency_overrides.clear()


# ============================================================
# RUNNER
# ============================================================

def test_runner_attaches_context_after_successful_diagnosis(
    monkeypatch,
):
    builder = RecordingContextBuilder()
    runner = AnalysisRunner(
        github_service=FakeGithub(),
        llm_service=FakeLLM(),
        context_builder=builder,
    )

    monkeypatch.setattr(
        "app.services.analysis_runner.build_analyze_issue_service",
        lambda files, llm_service=None: type(
            "AnalyzeStub",
            (),
            {"analyze": lambda self, files, issue, available_n=10: ANALYSIS},
        )(),
    )

    result = runner.run("owner", "repo", 1)

    assert result["diagnosis"] is not None
    assert result["diagnosis_error"] is None
    assert result["context_package"] is not None
    assert result["context_error"] is None
    assert result["context_package"]["slices"]
    assert builder.last_kwargs is not None
    assert builder.last_kwargs["ranked"] == ANALYSIS["ranked"]
    assert builder.last_kwargs["files"] == FILES
    assert "pubspec.yaml" not in {
        file["path"] for file in builder.last_kwargs["files"]
    }
    assert result["snapshot"]["pubspec.yaml"] == "name: demo\n"
    assert result["snapshot_commit"] == result["commit_sha"] == "headsha"
    assert "pubspec.yaml" not in result["sources"]
    assert len(result["sources"]) <= 10
    github = runner.github
    assert github.source_refs == []
    assert github.tracked_refs == ["headsha"]
    assert (
        builder.last_kwargs["direct_evidence"]
        == ANALYSIS["direct_evidence"]
    )


def test_context_failure_does_not_discard_diagnosis(monkeypatch):
    builder = RecordingContextBuilder(
        error=RuntimeError("context assembly failed"),
    )
    runner = AnalysisRunner(
        github_service=FakeGithub(),
        llm_service=FakeLLM(),
        context_builder=builder,
    )

    monkeypatch.setattr(
        "app.services.analysis_runner.build_analyze_issue_service",
        lambda files, llm_service=None: type(
            "AnalyzeStub",
            (),
            {"analyze": lambda self, files, issue, available_n=10: ANALYSIS},
        )(),
    )

    result = runner.run("owner", "repo", 1)

    assert result["diagnosis"] is not None
    assert result["diagnosis_error"] is None
    assert result["context_package"] is None
    assert result["context_error"] == "context assembly failed"


def test_runner_skips_context_when_diagnosis_fails(monkeypatch):
    builder = RecordingContextBuilder()
    runner = AnalysisRunner(
        github_service=FakeGithub(),
        llm_service=FakeLLM(),
        context_builder=builder,
    )

    monkeypatch.setattr(
        "app.services.analysis_runner.build_analyze_issue_service",
        lambda files, llm_service=None: type(
            "AnalyzeStub",
            (),
            {"analyze": lambda self, files, issue, available_n=10: ANALYSIS},
        )(),
    )

    monkeypatch.setattr(
        IssueDiagnosisService,
        "diagnose",
        lambda self, analysis: (_ for _ in ()).throw(
            ValueError("model failed")
        ),
    )

    result = runner.run("owner", "repo", 1)

    assert result["diagnosis"] is None
    assert result["diagnosis_error"] == "model failed"
    assert result["context_package"] is None
    assert builder.last_kwargs is None


def test_runner_skips_context_when_no_llm_is_configured(monkeypatch):
    builder = RecordingContextBuilder()
    runner = AnalysisRunner(
        github_service=FakeGithub(),
        llm_service=None,
        context_builder=builder,
    )

    monkeypatch.setattr(
        "app.services.analysis_runner.build_analyze_issue_service",
        lambda files, llm_service=None: type(
            "AnalyzeStub",
            (),
            {"analyze": lambda self, files, issue, available_n=10: ANALYSIS},
        )(),
    )

    result = runner.run("owner", "repo", 1)

    assert result["diagnosis"] is None
    assert result["diagnosis_error"] is not None
    assert result["context_package"] is None
    assert builder.last_kwargs is None


# ============================================================
# API
# ============================================================

def test_context_endpoint_returns_the_package(api_client):
    client, store = api_client
    record = store.create("owner", "repo", 1)
    package = _sample_context_dict()

    store.mark_completed(
        record["id"],
        {
            "issue": ISSUE,
            "signals": ANALYSIS["signals"],
            "relevant_files": [],
            "diagnosis": DIAGNOSIS,
            "diagnosis_error": None,
            "context_package": package,
            "context_error": None,
            "sources": {},
            "context": {},
        },
    )

    response = client.get(f"/api/analyses/{record['id']}/context")

    assert response.status_code == 200
    body = response.json()
    assert body["adapter"] == "DartCodeIntelligence"
    assert body["slices"][0]["path"] == "lib/bloc/task_bloc.dart"


def test_context_endpoint_returns_not_found_for_missing_analysis(
    api_client,
):
    client, _store = api_client

    response = client.get("/api/analyses/does-not-exist/context")

    assert response.status_code == 404
    assert "No analysis with id" in response.json()["detail"]


def test_context_endpoint_rejects_incomplete_analysis(api_client):
    client, store = api_client
    record = store.create("owner", "repo", 1)
    store.mark_running(record["id"], "diagnosing")

    response = client.get(f"/api/analyses/{record['id']}/context")

    assert response.status_code == 404
    assert "has not completed yet" in response.json()["detail"]


def test_context_endpoint_surfaces_context_error(api_client):
    client, store = api_client
    record = store.create("owner", "repo", 1)

    store.mark_completed(
        record["id"],
        {
            "issue": ISSUE,
            "signals": ANALYSIS["signals"],
            "relevant_files": [],
            "diagnosis": DIAGNOSIS,
            "diagnosis_error": None,
            "context_package": None,
            "context_error": "context assembly failed",
            "sources": {},
            "context": {},
        },
    )

    response = client.get(f"/api/analyses/{record['id']}/context")

    assert response.status_code == 502
    assert response.json()["detail"] == "context assembly failed"


def test_polling_analysis_response_does_not_leak_context(api_client):
    client, store = api_client
    record = store.create("owner", "repo", 1)
    package = _sample_context_dict()

    store.mark_completed(
        record["id"],
        {
            "issue": ISSUE,
            "signals": ANALYSIS["signals"],
            "relevant_files": [],
            "diagnosis": DIAGNOSIS,
            "diagnosis_error": None,
            "context_package": package,
            "context_error": None,
            "sources": {"lib/bloc/task_bloc.dart": "secret source"},
            "context": {"ranked": ANALYSIS["ranked"]},
        },
    )

    response = client.get(f"/api/analyses/{record['id']}")

    assert response.status_code == 200
    body = response.json()

    assert "context_package" not in body
    assert "context_error" not in body
    assert "sources" not in body
    assert "snapshot" not in body
    assert "snapshot_commit" not in body
    assert "context" not in body
    assert "slices" not in body
    assert body["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]


def test_files_endpoint_serves_ranked_sources(api_client):
    client, store = api_client
    record = store.create("owner", "repo", 1)
    content = "class TaskBloc {}\n"

    store.mark_completed(
        record["id"],
        {
            "issue": ISSUE,
            "signals": ANALYSIS["signals"],
            "relevant_files": [],
            "diagnosis": DIAGNOSIS,
            "diagnosis_error": None,
            "context_package": None,
            "context_error": None,
            "sources": {"lib/bloc/task_bloc.dart": content},
            "snapshot": {},
            "context": {},
        },
    )

    response = client.get(
        f"/api/analyses/{record['id']}/files",
        params={"path": "lib/bloc/task_bloc.dart"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "lib/bloc/task_bloc.dart"
    assert body["content"] == content


def test_files_endpoint_serves_context_package_path_from_snapshot(
    api_client,
):
    """
    Supporting ContextPackage files may sit outside ranked sources.
    Opening them from Patch must still work via the existing /files API.
    """

    client, store = api_client
    record = store.create("owner", "repo", 1)
    supporting = "lib/domain/entities/task_filter.dart"
    content = "class TaskFilter {}\n"

    store.mark_completed(
        record["id"],
        {
            "issue": ISSUE,
            "signals": ANALYSIS["signals"],
            "relevant_files": [],
            "diagnosis": DIAGNOSIS,
            "diagnosis_error": None,
            "context_package": {
                "adapter": "DartCodeIntelligence",
                "language": "dart",
                "budget": {
                    "max_lines_total": 100,
                    "lines_used": 1,
                    "max_files": 12,
                    "files_used": 1,
                },
                "warnings": [],
                "omitted": [],
                "files": [
                    {
                        "path": supporting,
                        "total_lines": 1,
                        "included_lines": 1,
                        "complete": True,
                    }
                ],
                "slices": [
                    {
                        "path": supporting,
                        "start_line": 1,
                        "end_line": 1,
                        "tier": 1,
                        "reason": "supporting declaration",
                        "symbols": ["TaskFilter"],
                        "content": content,
                        "truncated": False,
                        "language": "dart",
                        "adapter": "DartCodeIntelligence",
                    }
                ],
                "issue": ISSUE,
                "diagnosis": DIAGNOSIS,
                "root_cause": None,
            },
            "context_error": None,
            "sources": {"lib/bloc/task_bloc.dart": "class TaskBloc {}\n"},
            "snapshot": {
                "lib/bloc/task_bloc.dart": "class TaskBloc {}\n",
                supporting: content,
                "README.md": "# secret\n",
            },
            "context": {},
        },
    )

    response = client.get(
        f"/api/analyses/{record['id']}/files",
        params={"path": supporting},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == supporting
    assert body["content"] == content


def test_files_endpoint_rejects_snapshot_paths_outside_context(
    api_client,
):
    client, store = api_client
    record = store.create("owner", "repo", 1)

    store.mark_completed(
        record["id"],
        {
            "issue": ISSUE,
            "signals": ANALYSIS["signals"],
            "relevant_files": [],
            "diagnosis": DIAGNOSIS,
            "diagnosis_error": None,
            "context_package": {
                "adapter": "DartCodeIntelligence",
                "language": "dart",
                "budget": {
                    "max_lines_total": 100,
                    "lines_used": 0,
                    "max_files": 12,
                    "files_used": 0,
                },
                "warnings": [],
                "omitted": [],
                "files": [],
                "slices": [],
                "issue": ISSUE,
                "diagnosis": DIAGNOSIS,
                "root_cause": None,
            },
            "context_error": None,
            "sources": {"lib/bloc/task_bloc.dart": "class TaskBloc {}\n"},
            "snapshot": {
                "lib/bloc/task_bloc.dart": "class TaskBloc {}\n",
                "README.md": "# secret\n",
            },
            "context": {},
        },
    )

    response = client.get(
        f"/api/analyses/{record['id']}/files",
        params={"path": "README.md"},
    )

    assert response.status_code == 404
    assert "not among the files this analysis ranked" in response.json()[
        "detail"
    ]
