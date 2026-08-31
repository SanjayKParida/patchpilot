"""
Production wiring for PatchValidator via the analysis API.

Uses fakes only — no GitHub, no real LLM, no Flutter toolchain.
Does not change PatchValidator apply or command logic.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_analysis_store,
    get_patch_validator,
)
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.patch_types import (
    PatchFile,
    PatchHunk,
    PatchProposal,
    STATUS_OK,
)
from app.services.patch_validator_service import PatchValidatorService
from app.services.validation_command_runner import FakeValidationCommandRunner


PATH = "lib/bloc/task_bloc.dart"
OLD = "  // missing emit"
NEW = "  emit(TaskLoaded());"
SOURCE = "class TaskBloc {\n  // missing emit\n}"


ISSUE = {
    "number": 1,
    "title": "Spinner stuck",
    "body": "Refresh never completes.",
    "state": "open",
}


DIAGNOSIS = {
    "root_cause": "TaskBloc never emits TaskLoaded on refresh.",
    "confidence": 0.9,
    "relevant_files": [PATH],
    "explanation": "Refresh handler stops in TaskLoading.",
    "suggested_fix": "emit(TaskLoaded) after refresh succeeds.",
}


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
                        old_text=OLD,
                        new_text=NEW,
                    ),
                ),
            )
        ],
        warnings=[],
        errors=[],
    )


class CountingValidator:
    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def validate(self, proposal, files, config=None):
        self.calls.append({
            "proposal": proposal,
            "files": files,
            "config": config,
        })
        return self.inner.validate(proposal, files, config)


@pytest.fixture
def api_client():
    store = AnalysisStore()
    runner = FakeValidationCommandRunner()
    inner = PatchValidatorService(command_runner=runner)
    validator = CountingValidator(inner)

    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_patch_validator] = lambda: validator

    with TestClient(app) as client:
        yield client, store, validator, runner

    app.dependency_overrides.clear()


def _complete(store, **overrides):
    record = store.create("owner", "repo", 1)
    payload = {
        "issue": ISSUE,
        "signals": [],
        "relevant_files": [],
        "diagnosis": DIAGNOSIS,
        "diagnosis_error": None,
        "context_package": {"slices": []},
        "context_error": None,
        "sources": {PATH: SOURCE},
        "context": {},
        "patch_proposal": _proposal().to_dict(),
        "patch_error": None,
    }
    payload.update(overrides)
    store.mark_completed(record["id"], payload)
    return record["id"]


def _flutter_sources():
    return {
        PATH: SOURCE,
        "pubspec.yaml": "name: demo\n",
    }


# ============================================================
# SUCCESS / CACHE
# ============================================================

def test_validate_endpoint_applies_and_stores_result(api_client):
    client, store, validator, _runner = api_client
    analysis_id = _complete(store, sources=_flutter_sources())

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["applied"] is True
    assert body["validation_passed"] is True
    assert body["runnable"] is True
    assert body["unavailable_reason"] == ""
    assert [item["name"] for item in body["commands"]] == [
        "pub_get",
        "analyze",
        "test",
    ]

    stored = store.get(analysis_id)
    assert stored["patch_validation"]["status"] == "passed"
    assert stored["patch_validation_error"] is None
    assert stored["patch_proposal"]["summary"] == _proposal().summary
    assert stored["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]
    assert len(validator.calls) == 1


def test_validate_endpoint_returns_cached_result_without_rerunning(
    api_client,
):
    client, store, validator, _runner = api_client
    analysis_id = _complete(store, sources=_flutter_sources())

    first = client.post(f"/api/analyses/{analysis_id}/patch/validate")
    second = client.post(f"/api/analyses/{analysis_id}/patch/validate")
    fetched = client.get(f"/api/analyses/{analysis_id}/patch/validate")

    assert first.status_code == 200
    assert second.status_code == 200
    assert fetched.status_code == 200
    assert first.json() == second.json() == fetched.json()
    assert len(validator.calls) == 1


def test_validate_without_pubspec_is_apply_only_not_runnable(api_client):
    client, store, validator, runner = api_client
    analysis_id = _complete(store)

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "passed"
    assert body["runnable"] is False
    assert "pubspec.yaml" in body["unavailable_reason"]
    assert body["commands"] == []
    assert runner.calls == []
    assert len(validator.calls) == 1


def test_validate_node_backend_uses_package_scripts_not_flutter(api_client):
    client, store, validator, runner = api_client
    ts_path = "backend/src/server.ts"
    old = "export {}\n"
    new = "export const ok = 1;\n"
    proposal = PatchProposal(
        status=STATUS_OK,
        summary="fix type",
        reasoning="mismatch",
        confidence=0.9,
        files=[
            PatchFile(
                path=ts_path,
                language="ts",
                hunks=(
                    PatchHunk(
                        start_line=1,
                        end_line=1,
                        old_text=old,
                        new_text=new,
                    ),
                ),
            )
        ],
        warnings=[],
        errors=[],
    )
    analysis_id = _complete(
        store,
        sources={},
        snapshot={
            "backend/package.json": (
                '{"scripts":{"test":"vitest","start":"node dist/server.js"}}'
            ),
            "backend/package-lock.json": "{}",
            ts_path: old,
            "frontend/pubspec.yaml": "name: frontend\n",
        },
        snapshot_commit="abc",
        commit_sha="abc",
        patch_proposal=proposal.to_dict(),
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["runnable"] is True
    assert body["unavailable_reason"] == ""
    assert [item["name"] for item in body["commands"]] == [
        "install",
        "test",
    ]
    assert [item["argv"] for item in body["commands"]] == [
        ["npm", "ci", "--ignore-scripts"],
        ["npm", "run", "test"],
    ]
    assert runner.calls[0]["cwd"].endswith("backend")
    assert runner.calls[1]["cwd"].endswith("backend")
    assert len(validator.calls) == 1


# ============================================================
# FAILURE MODES
# ============================================================

def test_validate_endpoint_returns_not_found_for_missing_analysis(
    api_client,
):
    client, _store, _validator, _runner = api_client

    response = client.post("/api/analyses/does-not-exist/patch/validate")

    assert response.status_code == 404
    assert "No analysis with id" in response.json()["detail"]


def test_validate_endpoint_rejects_incomplete_analysis(api_client):
    client, store, _validator, _runner = api_client
    record = store.create("owner", "repo", 1)
    store.mark_running(record["id"], "diagnosing")

    response = client.post(
        f"/api/analyses/{record['id']}/patch/validate"
    )

    assert response.status_code == 404
    assert "has not completed yet" in response.json()["detail"]


def test_validate_endpoint_requires_stored_proposal(api_client):
    client, store, validator, _runner = api_client
    analysis_id = _complete(
        store,
        patch_proposal=None,
        patch_error="generation failed",
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 502
    assert response.json()["detail"] == "generation failed"
    assert validator.calls == []

    stored = store.get(analysis_id)
    assert stored["diagnosis"] is not None
    assert stored["patch_validation"] is None


def test_validate_apply_failure_preserves_diagnosis_and_proposal(
    api_client,
):
    client, store, _validator, _runner = api_client
    analysis_id = _complete(
        store,
        sources={PATH: "class TaskBloc {\n  // different\n}"},
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "apply_failed"
    assert body["applied"] is False
    assert body["validation_passed"] is False
    assert body["errors"]

    stored = store.get(analysis_id)
    assert stored["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]
    assert stored["patch_proposal"]["status"] == STATUS_OK
    assert stored["patch_validation"]["status"] == "apply_failed"


def test_validate_command_failure_keeps_proposal(api_client):
    client, store, _validator, _runner = api_client
    analysis_id = _complete(store, sources=_flutter_sources())

    failing = CountingValidator(
        PatchValidatorService(
            command_runner=FakeValidationCommandRunner(default_exit=1),
        )
    )
    app.dependency_overrides[get_patch_validator] = lambda: failing

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validation_failed"
    assert body["applied"] is True
    assert body["validation_passed"] is False
    assert body["runnable"] is True

    stored = store.get(analysis_id)
    assert stored["patch_proposal"] is not None
    assert stored["diagnosis"] is not None


def test_polling_analysis_response_does_not_leak_validation(api_client):
    client, store, _validator, _runner = api_client
    analysis_id = _complete(store, sources=_flutter_sources())

    assert client.post(
        f"/api/analyses/{analysis_id}/patch/validate"
    ).status_code == 200

    response = client.get(f"/api/analyses/{analysis_id}")

    assert response.status_code == 200
    body = response.json()
    assert "patch_validation" not in body
    assert "patch_validation_error" not in body
    assert "patch_proposal" not in body
    assert "sources" not in body
    assert "snapshot" not in body
    assert "snapshot_commit" not in body
    assert body["diagnosis"]["root_cause"] == DIAGNOSIS["root_cause"]


def test_get_validation_without_prior_run_returns_error(api_client):
    client, store, _validator, _runner = api_client
    analysis_id = _complete(store)

    response = client.get(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 502
    assert "No patch validation is available" in response.json()["detail"]


def test_validate_uses_full_snapshot_not_ranked_sources(api_client):
    client, store, validator, _runner = api_client
    sha = "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c"
    analysis_id = _complete(
        store,
        commit_sha=sha,
        snapshot_commit=sha,
        sources={PATH: SOURCE},
        snapshot={
            PATH: SOURCE,
            "pubspec.yaml": "name: demo\n",
            "README.md": "# demo\n",
        },
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["runnable"] is True
    assert body["status"] == "passed"
    assert [item["name"] for item in body["commands"]] == [
        "pub_get",
        "analyze",
        "test",
    ]
    files = validator.calls[0]["files"]
    stored = store.get(analysis_id)
    assert "pubspec.yaml" in files
    assert PATH in files
    assert "pubspec.yaml" not in stored["sources"]
    assert stored["snapshot"]["pubspec.yaml"] == "name: demo\n"


def test_validate_refuses_a_snapshot_from_a_different_commit(api_client):
    client, store, validator, _runner = api_client
    analysis_id = _complete(
        store,
        commit_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        snapshot_commit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        sources={PATH: SOURCE},
        snapshot=_flutter_sources(),
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/validate")

    assert response.status_code == 502
    assert "does not match the analysis commit" in response.json()["detail"]
    assert validator.calls == []
    stored = store.get(analysis_id)
    assert stored["patch_proposal"] is not None
    assert stored["diagnosis"] is not None
