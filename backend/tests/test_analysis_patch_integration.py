"""
Production wiring for PatchGenerator via the analysis API.

Uses fakes only — no GitHub, no real LLM, no network.
"""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.code_intelligence.types import (
    BudgetUsage,
    ContextPackage,
    ContextSlice,
    FileRollup,
)
from app.dependencies import (
    get_analysis_store,
    get_llm_service,
    get_patch_generator,
)
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.patch_types import (
    PatchFile,
    PatchHunk,
    PatchProposal,
    STATUS_OK,
)


ISSUE = {
    "number": 1,
    "title": "Spinner stuck",
    "body": "Refresh never completes.",
    "state": "open",
    "html_url": "https://example.test/issues/1",
    "comments": 0,
}

DIAGNOSIS = {
    "root_cause": "TaskBloc never emits TaskLoaded on refresh.",
    "confidence": 0.9,
    "relevant_files": ["lib/bloc/task_bloc.dart"],
    "explanation": "Refresh handler stops in TaskLoading.",
    "suggested_fix": "emit(TaskLoaded) after refresh succeeds.",
    "root_cause_symbols": ["TaskBloc"],
    "symbols": ["TaskLoading"],
    "root_cause_locations": [
        {
            "symbol": "TaskBloc",
            "path": "lib/bloc/task_bloc.dart",
            "line": 1,
            "kind": "class",
        }
    ],
    "locations": [],
}

PATH = "lib/bloc/task_bloc.dart"


def _context_package_dict():
    package = ContextPackage(
        slices=[
            ContextSlice(
                path=PATH,
                start_line=1,
                end_line=3,
                tier=0,
                reason="declares TaskBloc, named as the defect site",
                symbols=("TaskBloc",),
                content=(
                    "class TaskBloc {\n"
                    "  // missing emit\n"
                    "}"
                ),
                truncated=False,
                language="dart",
                adapter="DartCodeIntelligence",
            )
        ],
        files=[
            FileRollup(
                path=PATH,
                total_lines=3,
                included_lines=3,
                complete=True,
            )
        ],
        omitted=[],
        warnings=[],
        budget=BudgetUsage(
            max_files=12,
            files_used=1,
            max_lines_total=1200,
            lines_used=3,
            estimated_tokens=20,
            over_budget=False,
        ),
        language="dart",
        adapter="DartCodeIntelligence",
        issue=ISSUE,
        diagnosis=DIAGNOSIS,
        root_cause={
            "symbol": "TaskBloc",
            "path": PATH,
            "line": 1,
            "kind": "class",
        },
    )
    return package.to_dict()


def _proposal():
    return PatchProposal(
        status=STATUS_OK,
        summary="emit loaded state after refresh",
        reasoning="Refresh handler never leaves TaskLoading.",
        confidence=0.9,
        files=[
            PatchFile(
                path=PATH,
                language="dart",
                hunks=(
                    PatchHunk(
                        start_line=2,
                        end_line=2,
                        old_text="  // missing emit",
                        new_text="  emit(TaskLoaded());",
                    ),
                ),
            )
        ],
        warnings=[],
        errors=[],
    )


class FakeLLM:
    available = True

    def ask(self, prompt):
        return json.dumps(_proposal().to_dict())


class FakePatchGenerator:
    def __init__(self, proposal=None, error=None):
        self.proposal = proposal or _proposal()
        self.error = error
        self.calls = []

    def generate(self, issue, diagnosis, context_package):
        self.calls.append({
            "issue": issue,
            "diagnosis": diagnosis,
            "context_package": context_package,
        })

        if self.error is not None:
            raise self.error

        return self.proposal


@pytest.fixture
def api_client():
    store = AnalysisStore()
    generator = FakePatchGenerator()

    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_patch_generator] = lambda: generator
    app.dependency_overrides[get_llm_service] = lambda: FakeLLM()

    with TestClient(app) as client:
        yield client, store, generator

    app.dependency_overrides.clear()


def _complete(store, **overrides):
    record = store.create("owner", "repo", 1)
    payload = {
        "issue": ISSUE,
        "signals": [{"term": "refresh", "type": "behavior"}],
        "relevant_files": [],
        "diagnosis": DIAGNOSIS,
        "diagnosis_error": None,
        "context_package": _context_package_dict(),
        "context_error": None,
        "sources": {},
        "context": {},
    }
    payload.update(overrides)
    store.mark_completed(record["id"], payload)
    return record["id"]


# ============================================================
# SUCCESS
# ============================================================

def test_patch_endpoint_generates_and_stores_proposal(api_client):
    client, store, generator = api_client
    analysis_id = _complete(store)

    response = client.post(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == STATUS_OK
    assert body["files"][0]["path"] == PATH
    assert "emit(TaskLoaded" in body["files"][0]["hunks"][0]["new_text"]

    stored = store.get(analysis_id)
    assert stored["patch_proposal"]["status"] == STATUS_OK
    assert stored["patch_error"] is None
    assert stored["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]
    assert stored["context_package"] is not None
    assert len(generator.calls) == 1
    assert generator.calls[0]["issue"] == ISSUE
    assert generator.calls[0]["diagnosis"] == DIAGNOSIS


def test_patch_endpoint_returns_cached_proposal_without_regenerating(
    api_client,
):
    client, store, generator = api_client
    analysis_id = _complete(store)

    first = client.post(f"/api/analyses/{analysis_id}/patch")
    second = client.post(f"/api/analyses/{analysis_id}/patch")
    fetched = client.get(f"/api/analyses/{analysis_id}/patch")

    assert first.status_code == 200
    assert second.status_code == 200
    assert fetched.status_code == 200
    assert first.json() == second.json() == fetched.json()
    assert len(generator.calls) == 1


# ============================================================
# FAILURE MODES
# ============================================================

def test_patch_endpoint_returns_not_found_for_missing_analysis(
    api_client,
):
    client, _store, _generator = api_client

    response = client.post("/api/analyses/does-not-exist/patch")

    assert response.status_code == 404
    assert "No analysis with id" in response.json()["detail"]


def test_patch_endpoint_rejects_incomplete_analysis(api_client):
    client, store, _generator = api_client
    record = store.create("owner", "repo", 1)
    store.mark_running(record["id"], "diagnosing")

    response = client.post(f"/api/analyses/{record['id']}/patch")

    assert response.status_code == 404
    assert "has not completed yet" in response.json()["detail"]


def test_patch_endpoint_requires_context_package(api_client):
    client, store, generator = api_client
    analysis_id = _complete(
        store,
        context_package=None,
        context_error="context assembly failed",
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 502
    assert response.json()["detail"] == "context assembly failed"
    assert generator.calls == []

    stored = store.get(analysis_id)
    assert stored["diagnosis"] is not None
    assert stored["patch_proposal"] is None


def test_patch_endpoint_requires_diagnosis(api_client):
    client, store, generator = api_client
    analysis_id = _complete(
        store,
        diagnosis=None,
        diagnosis_error="model failed",
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 502
    assert response.json()["detail"] == "model failed"
    assert generator.calls == []


def test_patch_generator_failure_preserves_diagnosis_and_context(
    api_client,
):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    failing = FakePatchGenerator(error=RuntimeError("llm exploded"))
    app.dependency_overrides[get_patch_generator] = lambda: failing

    response = client.post(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 502
    assert "llm exploded" in response.json()["detail"]

    stored = store.get(analysis_id)
    assert stored["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]
    assert stored["context_package"]["slices"]
    assert stored["patch_proposal"] is None
    assert stored["patch_error"] == "llm exploded"


def test_polling_analysis_response_does_not_leak_patch(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    assert client.post(f"/api/analyses/{analysis_id}/patch").status_code == 200

    response = client.get(f"/api/analyses/{analysis_id}")

    assert response.status_code == 200
    body = response.json()
    assert "patch_proposal" not in body
    assert "patch_error" not in body
    assert "patch_validation" not in body
    assert "patch_validation_error" not in body
    assert "context_package" not in body
    assert "sources" not in body
    assert "snapshot" not in body
    assert "snapshot_commit" not in body
    assert body["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]


def test_get_patch_without_prior_generation_returns_error(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    response = client.get(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 502
    assert "No patch proposal is available" in response.json()["detail"]


def test_slow_generator_still_returns_proposal_within_request(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    class SlowGenerator(FakePatchGenerator):
        def generate(self, issue, diagnosis, context_package):
            time.sleep(0.2)
            return super().generate(issue, diagnosis, context_package)

    slow = SlowGenerator()
    app.dependency_overrides[get_patch_generator] = lambda: slow

    response = client.post(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 200
    assert response.json()["status"] == STATUS_OK
    assert store.get(analysis_id)["patch_proposal"] is not None
    assert store.get(analysis_id)["patch_generating"] is False
    assert len(slow.calls) == 1


def test_proposal_is_stored_before_http_response(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)
    order = []
    original = store.finish_patch_generation

    def wrapped(aid, proposal=None, error=None):
        original(aid, proposal=proposal, error=error)
        order.append("store")

    store.finish_patch_generation = wrapped

    response = client.post(f"/api/analyses/{analysis_id}/patch")
    order.append("http")

    assert response.status_code == 200
    assert order == ["store", "http"]
    assert store.get(analysis_id)["patch_proposal"]["status"] == STATUS_OK
    assert response.json() == store.get(analysis_id)["patch_proposal"]


def test_concurrent_generate_requests_do_not_duplicate_generation(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    started = threading.Event()
    release = threading.Event()

    class BlockingGenerator(FakePatchGenerator):
        def generate(self, issue, diagnosis, context_package):
            self.calls.append({
                "issue": issue,
                "diagnosis": diagnosis,
                "context_package": context_package,
            })
            started.set()
            assert release.wait(timeout=5)
            if self.error is not None:
                raise self.error
            return self.proposal

    blocking = BlockingGenerator()
    app.dependency_overrides[get_patch_generator] = lambda: blocking

    results = {}

    def first_request():
        results["first"] = client.post(
            f"/api/analyses/{analysis_id}/patch"
        )

    thread = threading.Thread(target=first_request)
    thread.start()
    assert started.wait(timeout=5)

    second = client.post(f"/api/analyses/{analysis_id}/patch")
    during = client.get(f"/api/analyses/{analysis_id}/patch")

    assert second.status_code == 409
    assert "already running" in second.json()["detail"]
    assert during.status_code == 409
    assert "already running" in during.json()["detail"]
    assert len(blocking.calls) == 1
    assert store.get(analysis_id)["patch_generating"] is True
    assert store.get(analysis_id)["patch_proposal"] is None

    release.set()
    thread.join(timeout=5)

    assert results["first"].status_code == 200
    assert len(blocking.calls) == 1
    assert store.get(analysis_id)["patch_generating"] is False

    cached = client.post(f"/api/analyses/{analysis_id}/patch")
    assert cached.status_code == 200
    assert cached.json() == results["first"].json()
    assert len(blocking.calls) == 1


def test_blank_finish_does_not_discard_a_cached_proposal(api_client):
    """
    A cancelled HTTP request used to call finish(proposal=None) and
    wipe the stored patch, so the next POST generated a different one.
    """

    client, store, generator = api_client
    analysis_id = _complete(store)

    first = client.post(f"/api/analyses/{analysis_id}/patch")
    assert first.status_code == 200
    assert len(generator.calls) == 1

    store.finish_patch_generation(analysis_id, proposal=None, error=None)

    second = client.post(f"/api/analyses/{analysis_id}/patch")
    fetched = client.get(f"/api/analyses/{analysis_id}/patch")

    assert second.status_code == 200
    assert fetched.status_code == 200
    assert first.json() == second.json() == fetched.json()
    assert len(generator.calls) == 1
    assert store.get(analysis_id)["patch_proposal"] is not None


def test_failed_generation_can_be_retried(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    failing = FakePatchGenerator(error=RuntimeError("llm exploded"))
    app.dependency_overrides[get_patch_generator] = lambda: failing

    first = client.post(f"/api/analyses/{analysis_id}/patch")
    assert first.status_code == 502
    assert store.get(analysis_id)["patch_proposal"] is None

    succeeding = FakePatchGenerator()
    app.dependency_overrides[get_patch_generator] = lambda: succeeding

    second = client.post(f"/api/analyses/{analysis_id}/patch")
    assert second.status_code == 200
    assert second.json()["status"] == STATUS_OK
    assert len(succeeding.calls) == 1
    assert store.get(analysis_id)["patch_error"] is None


def test_generator_failure_is_distinguishable_from_in_progress(api_client):
    client, store, _generator = api_client
    analysis_id = _complete(store)

    failing = FakePatchGenerator(error=RuntimeError("llm exploded"))
    app.dependency_overrides[get_patch_generator] = lambda: failing

    response = client.post(f"/api/analyses/{analysis_id}/patch")
    fetched = client.get(f"/api/analyses/{analysis_id}/patch")

    assert response.status_code == 502
    assert "Patch generation failed: llm exploded" in response.json()["detail"]
    assert fetched.status_code == 502
    assert fetched.json()["detail"] == "llm exploded"
    assert "already running" not in response.json()["detail"]
    assert store.get(analysis_id)["patch_generating"] is False
    assert store.get(analysis_id)["patch_proposal"] is None
