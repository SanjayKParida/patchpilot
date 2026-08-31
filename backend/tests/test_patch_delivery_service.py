"""Branch naming and PatchDeliveryService behaviour. No GitHub network."""

import json
from pathlib import Path

import pytest

from app.application.patch_delivery_service import PatchDeliveryService
from app.domain.patch_delivery import (
    delivery_branch_name,
    is_safe_branch_name,
)
from app.errors import (
    GithubPermissionDenied,
    PatchDeliveryInProgress,
    PatchDeliveryRejected,
    PatchNotApproved,
    PatchNotValidated,
    UpstreamUnavailable,
)
from app.services.analysis_store import AnalysisStore
from app.services.patch_apply import apply_proposal_to_map, files_to_map
from tests.fakes.github_write_client import FakeGithub, FakeGithubWriteClient

PINNED = "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c"
PATH = "lib/bloc/task_bloc.dart"
OLD = "  // missing emit"
NEW = "  emit(TaskLoaded());"
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
                    "old_text": OLD,
                    "new_text": NEW,
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


def _service():
    store = AnalysisStore()
    github = FakeGithub(commits={PINNED: PINNED})
    writer = FakeGithubWriteClient()
    service = PatchDeliveryService(store, github, writer)
    return store, github, writer, service


def _ready(store, **overrides):
    record = store.create("owner", "repo", 1, ref=PINNED, commit_sha=PINNED)
    payload = {
        "issue": {"number": 1, "title": "Spinner stuck", "body": "Refresh."},
        "signals": [],
        "relevant_files": [],
        "diagnosis": {"root_cause": "never emits"},
        "diagnosis_error": None,
        "context_package": {"slices": []},
        "context_error": None,
        "commit_sha": PINNED,
        "snapshot_commit": PINNED,
        "snapshot": {PATH: SOURCE, "README.md": "# demo\n"},
        "patch_proposal": PROPOSAL_OK,
        "patch_validation": VALIDATION_PASSED,
    }
    payload.update(overrides)
    store.mark_completed(record["id"], payload)
    return record["id"]


def test_branch_name_is_deterministic_and_safe():
    name = delivery_branch_name(3, PINNED, "0d114d0795cb46b8abd322d549305c4b")
    assert name == "patchpilot/issue-3/f0bfc5b317f4-0d114d07"
    assert is_safe_branch_name(name, default_branch="main")
    assert not is_safe_branch_name("main", default_branch="main")
    assert not is_safe_branch_name("../evil", default_branch="main")
    assert not is_safe_branch_name("/abs", default_branch="main")
    assert not is_safe_branch_name("refs/heads/main", default_branch="main")
    assert not is_safe_branch_name("patchpilot/issue-1/abc def", default_branch="main")


def test_approve_requires_runnable_validation():
    store, _github, writer, service = _service()
    analysis_id = _ready(
        store,
        patch_validation={
            **VALIDATION_PASSED,
            "runnable": False,
            "status": "passed",
            "validation_passed": True,
        },
    )

    with pytest.raises(PatchNotValidated):
        service.approve(analysis_id)

    assert writer.write_ops == []
    assert store.get(analysis_id)["patch_approved"] is False


def test_approve_is_idempotent_for_the_same_commit():
    store, _github, _writer, service = _service()
    analysis_id = _ready(store)

    first = service.approve(analysis_id)
    second = service.approve(analysis_id)

    assert first.approved is True
    assert second.approved_at == first.approved_at
    assert second.commit_sha == PINNED


def test_deliver_rejects_unapproved_without_writes():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)

    with pytest.raises(PatchNotApproved):
        service.deliver(analysis_id)

    assert writer.write_ops == []


def test_deliver_uses_analyzed_sha_as_commit_parent():
    store, github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)

    result = service.deliver(analysis_id)

    assert result.succeeded
    assert result.draft is True
    assert writer.commits[0]["parents"] == [PINNED]
    assert github.get_commit_calls[0][2] == PINNED
    tree = writer.trees[0]
    assert tree["base_tree"] == github.tree_sha
    assert [entry["path"] for entry in tree["tree"]] == [PATH]
    blob_sha = tree["tree"][0]["sha"]
    expected, _, errors = apply_proposal_to_map(
        PROPOSAL_OK,
        files_to_map({PATH: SOURCE}),
    )
    assert errors == []
    assert writer.blobs[blob_sha] == expected[PATH]
    assert all(
        payload["ref"] != "refs/heads/main"
        for op, payload in writer.calls
        if op == "create_ref"
    )
    pr = writer.pulls[0]
    assert pr["base"] == "main"
    assert pr["head"] == result.branch
    assert pr["draft"] is True


def test_duplicate_success_does_not_write_again():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    service.deliver(analysis_id)
    writes = list(writer.write_ops)

    second = service.deliver(analysis_id)

    assert second.succeeded
    assert writer.write_ops == writes


def test_in_progress_delivery_is_rejected():
    store, github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    store.begin_delivery(analysis_id)

    with pytest.raises(PatchDeliveryInProgress):
        service.deliver(analysis_id)

    assert writer.write_ops == []
    assert github.get_commit_calls == []


def test_apply_failure_writes_nothing():
    store, _github, writer, service = _service()
    analysis_id = _ready(
        store,
        snapshot={PATH: "class TaskBloc {\n  // different\n}"},
    )
    service.approve(analysis_id)

    result = service.deliver(analysis_id)

    assert result.status == "failed"
    assert result.stage == "apply"
    assert result.pr_url is None
    assert writer.write_ops == []


def test_commit_failure_creates_no_branch_or_pr():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    writer.unavailable("create_commit")

    with pytest.raises(UpstreamUnavailable):
        service.deliver(analysis_id)

    assert writer.commits == []
    assert writer.refs == {}
    assert writer.pulls == []
    stored = store.get(analysis_id)["patch_delivery"]
    assert stored["status"] == "failed"
    assert stored["stage"] == "commit"
    assert stored["pr_url"] is None


def test_push_failure_creates_no_pr():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    writer.unavailable("create_ref")

    with pytest.raises(UpstreamUnavailable):
        service.deliver(analysis_id)

    assert writer.commits
    assert writer.refs == {}
    assert writer.pulls == []
    stored = store.get(analysis_id)["patch_delivery"]
    assert stored["stage"] == "push"
    assert stored["commit_sha"] is not None


def test_pr_failure_keeps_branch_and_retries():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    writer.fail_on = "create_pull_request"
    writer.fail_once = True
    writer.fail_with = UpstreamUnavailable("pr failed")

    with pytest.raises(UpstreamUnavailable):
        service.deliver(analysis_id)

    stored = store.get(analysis_id)["patch_delivery"]
    assert stored["status"] == "failed"
    assert stored["stage"] == "pull_request"
    assert stored["branch"]
    assert stored["commit_sha"]
    assert writer.refs
    blob_writes = writer.write_ops.count("create_blob")

    result = service.deliver(analysis_id)

    assert result.succeeded
    assert writer.write_ops.count("create_blob") == blob_writes
    assert writer.write_ops.count("create_pull_request") == 2


def test_foreign_branch_collision_does_not_open_that_pr():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    primary = delivery_branch_name(1, PINNED, analysis_id)
    writer.refs[f"refs/heads/{primary}"] = "deadbeef" * 5

    result = service.deliver(analysis_id)

    assert result.succeeded
    assert result.branch != primary
    assert result.branch.startswith(primary + "-")
    assert writer.pulls[0]["head"] == result.branch
    assert f"refs/heads/{primary}" not in [
        payload["ref"]
        for op, payload in writer.calls
        if op == "create_ref"
    ]


def test_permission_denied_is_not_success():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    writer.permission_denied("create_blob")

    with pytest.raises(GithubPermissionDenied):
        service.deliver(analysis_id)

    stored = store.get(analysis_id)["patch_delivery"]
    assert stored["status"] != "succeeded"
    assert stored["pr_url"] is None


def test_commit_mismatch_after_approval_is_rejected():
    store, _github, writer, service = _service()
    analysis_id = _ready(store)
    service.approve(analysis_id)
    store.update(analysis_id, commit_sha="b" * 40)

    with pytest.raises(PatchDeliveryRejected):
        service.deliver(analysis_id)

    assert writer.write_ops == []


def test_issue_3_fixture_blob_matches_apply_output():
    proposal_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "patch_proposals"
        / "active_filter_good.json"
    )
    eval_path = (
        Path(__file__).resolve().parents[1].parent
        / "evalutation"
        / "fixtures"
        / "active_filter_pre_fix.json"
    )
    proposal = json.loads(proposal_path.read_text())
    tracked = json.loads(eval_path.read_text())
    snapshot = {
        item["path"]: item["content"]
        for item in tracked["files"]
        if item.get("path")
    }

    expected, _, errors = apply_proposal_to_map(proposal, files_to_map(snapshot))
    assert errors == []

    store, _github, writer, service = _service()
    analysis_id = _ready(
        store,
        issue={"number": 3, "title": "Active filter", "body": ""},
        patch_proposal=proposal,
        snapshot=snapshot,
    )
    store.update(analysis_id, issue_number=3)
    service.approve(analysis_id)
    result = service.deliver(analysis_id)

    path = "lib/domain/usecases/get_filtered_tasks.dart"
    blob_sha = writer.trees[0]["tree"][0]["sha"]
    assert writer.trees[0]["tree"][0]["path"] == path
    assert writer.blobs[blob_sha] == expected[path]
    assert "!task.isCompleted" in writer.blobs[blob_sha]
    assert result.succeeded
    assert "issue-3" in result.branch
