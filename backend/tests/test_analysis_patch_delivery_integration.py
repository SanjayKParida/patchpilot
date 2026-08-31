"""HTTP contract for approve + deliver. Fake GitHub writes only."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.application.patch_delivery_service import PatchDeliveryService
from app.dependencies import (
    get_analysis_store,
    get_github_service,
    get_github_write_client,
    get_patch_delivery_service,
)
from app.domain.patch_delivery import delivery_branch_name
from app.errors import GithubPermissionDenied, UpstreamUnavailable
from app.main import app
from app.services.analysis_store import AnalysisStore
from app.services.patch_apply import apply_proposal_to_map, files_to_map
from tests.fakes.github_write_client import FakeGithub, FakeGithubWriteClient

PINNED = "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c"
PATH = "lib/bloc/task_bloc.dart"
SOURCE = "class TaskBloc {\n  // missing emit\n}"

PROPOSAL_OK = {
    "status": "ok",
    "summary": "emit loaded state after refresh",
    "reasoning": "Refresh handler never leaves TaskLoading.",
    "confidence": 0.9,
    "warnings": [],
    "errors": [],
    "files": [
        {
            "path": PATH,
            "language": "dart",
            "hunks": [
                {
                    "start_line": 2,
                    "end_line": 2,
                    "old_text": "  // missing emit",
                    "new_text": "  emit(TaskLoaded());",
                }
            ],
        }
    ],
}

VALIDATION_PASSED = {
    "status": "passed",
    "applied": True,
    "validation_passed": True,
    "runnable": True,
    "unavailable_reason": "",
    "files": [],
    "commands": [],
    "errors": [],
    "warnings": [],
}


@pytest.fixture
def api():
    store = AnalysisStore()
    github = FakeGithub(commits={PINNED: PINNED})
    writer = FakeGithubWriteClient()
    service = PatchDeliveryService(store, github, writer)

    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_github_service] = lambda: github
    app.dependency_overrides[get_github_write_client] = lambda: writer
    app.dependency_overrides[get_patch_delivery_service] = lambda: service

    with TestClient(app) as client:
        yield client, store, github, writer

    app.dependency_overrides.clear()


def _complete(store, **overrides):
    record = store.create("owner", "repo", 1, ref=PINNED, commit_sha=PINNED)
    payload = {
        "issue": {"number": 1, "title": "Spinner stuck", "body": "Refresh."},
        "signals": [],
        "relevant_files": [],
        "diagnosis": {
            "root_cause": "never emits",
            "confidence": 0.9,
            "explanation": "Refresh stays loading.",
            "suggested_fix": "Emit loaded.",
        },
        "diagnosis_error": None,
        "context_package": {"slices": []},
        "context_error": None,
        "commit_sha": PINNED,
        "snapshot_commit": PINNED,
        "snapshot": {PATH: SOURCE, "pubspec.yaml": "name: demo\n"},
        "patch_proposal": PROPOSAL_OK,
        "patch_validation": VALIDATION_PASSED,
    }
    payload.update(overrides)
    store.mark_completed(record["id"], payload)
    return record["id"]


def test_unapproved_delivery_is_409_with_zero_writes(api):
    client, store, _github, writer = api
    analysis_id = _complete(store)

    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 409
    assert "not been approved" in response.json()["detail"]
    assert writer.write_ops == []


def test_unvalidated_approval_is_409_with_zero_writes(api):
    client, store, _github, writer = api
    analysis_id = _complete(store, patch_validation=None)

    response = client.post(f"/api/analyses/{analysis_id}/patch/approve")

    assert response.status_code == 409
    assert writer.write_ops == []


def test_non_runnable_validation_is_409(api):
    client, store, _github, writer = api
    analysis_id = _complete(
        store,
        patch_validation={
            **VALIDATION_PASSED,
            "runnable": False,
            "unavailable_reason": "missing pubspec.yaml",
        },
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/approve")

    assert response.status_code == 409
    assert writer.write_ops == []


def test_invalid_proposal_is_422(api):
    client, store, _github, writer = api
    analysis_id = _complete(
        store,
        patch_proposal={**PROPOSAL_OK, "status": "empty", "files": []},
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/approve")

    assert response.status_code == 422
    assert writer.write_ops == []


def test_snapshot_commit_mismatch_is_422(api):
    client, store, _github, writer = api
    analysis_id = _complete(
        store,
        commit_sha=PINNED,
        snapshot_commit="b" * 40,
    )

    response = client.post(f"/api/analyses/{analysis_id}/patch/approve")

    assert response.status_code == 422
    assert writer.write_ops == []


def test_commit_mismatch_on_deliver_is_422(api):
    client, store, _github, writer = api
    analysis_id = _complete(store)
    assert client.post(
        f"/api/analyses/{analysis_id}/patch/approve"
    ).status_code == 200
    store.update(analysis_id, commit_sha="c" * 40)

    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 422
    assert writer.write_ops == []


def test_approve_and_deliver_happy_path(api):
    client, store, github, writer = api
    analysis_id = _complete(store)

    approved = client.post(f"/api/analyses/{analysis_id}/patch/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["approved"] is True
    assert body["commit_sha"] == PINNED

    fetched = client.get(f"/api/analyses/{analysis_id}/patch/approve")
    assert fetched.json()["approved_at"] == body["approved_at"]

    delivered = client.post(
        f"/api/analyses/{analysis_id}/patch/deliver",
        json={
            "owner": "evil",
            "repo": "other",
            "commit": "0" * 40,
            "files": [{"path": "/etc/passwd", "hunks": []}],
        },
    )
    assert delivered.status_code == 200
    result = delivered.json()
    assert result["status"] == "succeeded"
    assert result["draft"] is True
    assert result["pr_url"]
    assert result["base_commit_sha"] == PINNED
    assert writer.commits[0]["parents"] == [PINNED]
    assert writer.pulls[0]["base"] == "main"
    assert writer.pulls[0]["head"] == result["branch"]
    assert all(call[0] == "owner" for call in github.get_repository_calls)
    assert all(payload["owner"] == "owner" for _op, payload in writer.calls)


def test_duplicate_deliver_after_success_does_not_write(api):
    client, store, _github, writer = api
    analysis_id = _complete(store)
    client.post(f"/api/analyses/{analysis_id}/patch/approve")
    first = client.post(f"/api/analyses/{analysis_id}/patch/deliver")
    assert first.status_code == 200
    writes = list(writer.write_ops)

    second = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert second.status_code == 200
    assert second.json()["pr_url"] == first.json()["pr_url"]
    assert writer.write_ops == writes


def test_running_delivery_returns_409(api):
    client, store, _github, writer = api
    analysis_id = _complete(store)
    client.post(f"/api/analyses/{analysis_id}/patch/approve")
    store.begin_delivery(analysis_id)

    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 409
    assert writer.write_ops == []


def test_github_403_maps_to_permission_denied(api):
    client, store, _github, writer = api
    analysis_id = _complete(store)
    client.post(f"/api/analyses/{analysis_id}/patch/approve")
    writer.fail_on = "create_blob"
    writer.fail_with = GithubPermissionDenied("token cannot write")

    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 403
    stored = store.get(analysis_id)["patch_delivery"]
    assert stored["status"] != "succeeded"


def test_github_502_on_commit_failure(api):
    client, store, _github, writer = api
    analysis_id = _complete(store)
    client.post(f"/api/analyses/{analysis_id}/patch/approve")
    writer.fail_on = "create_commit"
    writer.fail_with = UpstreamUnavailable("GitHub returned 502")

    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 502
    assert writer.refs == {}
    assert writer.pulls == []


def test_apply_failure_returns_failed_delivery_without_writes(api):
    client, store, _github, writer = api
    analysis_id = _complete(
        store,
        snapshot={PATH: "class TaskBloc {\n  // different\n}"},
    )
    client.post(f"/api/analyses/{analysis_id}/patch/approve")

    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["stage"] == "apply"
    assert body["pr_url"] is None
    assert writer.write_ops == []


def test_polling_analysis_does_not_include_delivery(api):
    client, store, _github, _writer = api
    analysis_id = _complete(store)
    assert client.post(
        f"/api/analyses/{analysis_id}/patch/approve"
    ).status_code == 200
    deliver = client.post(f"/api/analyses/{analysis_id}/patch/deliver")
    assert deliver.status_code == 200

    response = client.get(f"/api/analyses/{analysis_id}")

    body = response.json()
    assert "patch_approved" not in body
    assert "patch_delivery" not in body
    assert "patch_proposal" not in body
    assert "snapshot" not in body


def test_get_approve_without_prior_returns_404(api):
    client, store, _github, _writer = api
    analysis_id = _complete(store)

    response = client.get(f"/api/analyses/{analysis_id}/patch/approve")

    assert response.status_code == 404


def test_get_deliver_without_prior_returns_404(api):
    client, store, _github, _writer = api
    analysis_id = _complete(store)

    response = client.get(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 404


def test_issue_3_fixture_backed_delivery(api):
    client, store, _github, writer = api
    proposal = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "patch_proposals"
            / "active_filter_good.json"
        ).read_text()
    )
    tracked = json.loads(
        (
            Path(__file__).resolve().parents[1].parent
            / "evalutation"
            / "fixtures"
            / "active_filter_pre_fix.json"
        ).read_text()
    )
    snapshot = {
        item["path"]: item["content"]
        for item in tracked["files"]
        if item.get("path")
    }
    expected, _, errors = apply_proposal_to_map(proposal, files_to_map(snapshot))
    assert errors == []

    analysis_id = _complete(
        store,
        issue={"number": 3, "title": "Active filter", "body": ""},
        patch_proposal=proposal,
        snapshot=snapshot,
    )
    store.update(analysis_id, issue_number=3)

    assert client.post(
        f"/api/analyses/{analysis_id}/patch/approve"
    ).status_code == 200
    response = client.post(f"/api/analyses/{analysis_id}/patch/deliver")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["draft"] is True
    assert "issue-3" in body["branch"]
    path = "lib/domain/usecases/get_filtered_tasks.dart"
    assert writer.trees[0]["tree"][0]["path"] == path
    blob_sha = writer.trees[0]["tree"][0]["sha"]
    assert writer.blobs[blob_sha] == expected[path]
    assert writer.commits[0]["parents"] == [PINNED]
    assert body["branch"] == delivery_branch_name(3, PINNED, analysis_id)
