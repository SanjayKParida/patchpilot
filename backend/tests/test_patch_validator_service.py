"""
Tests for PatchValidator: full-file apply, workspace isolation, commands.

No GitHub, no LLM, no Flutter. Default suite stays offline.
"""

import json
import sys
from pathlib import Path

from app.services.patch_apply import (
    apply_hunks_to_content,
    apply_proposal_to_map,
    expected_old_text_from_content,
    is_safe_relative_path,
)
from app.services.patch_types import (
    PatchFile,
    PatchHunk,
    PatchProposal,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_OK,
)
from app.services.patch_validation_types import (
    STATUS_APPLY_FAILED,
    STATUS_PASSED,
    STATUS_PROPOSAL_INVALID,
    STATUS_VALIDATION_FAILED,
    ValidationCommand,
    ValidationConfig,
)
from app.services.patch_validator_service import PatchValidatorService
from app.services.patch_workspace import cleanup, materialize
from app.services.validation_command_runner import (
    FakeValidationCommandRunner,
    ShellValidationCommandRunner,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "evalutation" / "fixtures"
PROPOSALS = Path(__file__).resolve().parent / "fixtures" / "patch_proposals"


def _load_snapshot(name):
    data = json.loads((FIXTURES / name).read_text())
    return {item["path"]: item["content"] for item in data["files"]}


def _load_proposal(name):
    return json.loads((PROPOSALS / name).read_text())


def _proposal(path, start, end, old, new, status=STATUS_OK):
    return PatchProposal(
        status=status,
        summary="test",
        reasoning="test",
        confidence=1.0,
        files=[
            PatchFile(
                path=path,
                language="fake",
                hunks=(
                    PatchHunk(start, end, old, new),
                ),
            )
        ],
    )


MINI = {
    "lib/a.fake": "one\ntwo\nthree\nfour",
    "lib/b.fake": "alpha\nbeta",
}


# ============================================================
# TYPES
# ============================================================

def test_validation_result_to_json_is_deterministic():
    service = PatchValidatorService()
    proposal = _proposal(
        "lib/a.fake",
        2,
        2,
        "two",
        "TWO",
    )
    first = service.validate(proposal, MINI)
    second = service.validate(proposal, MINI)

    assert first.to_json() == second.to_json()
    assert first.to_json() == first.to_json()
    assert '"status":"passed"' in first.to_json()


# ============================================================
# PATH SAFETY
# ============================================================

def test_rejects_absolute_and_parent_paths():
    assert is_safe_relative_path("lib/a.fake") is True
    assert is_safe_relative_path("/etc/passwd") is False
    assert is_safe_relative_path("../secret") is False
    assert is_safe_relative_path("lib/../../etc/passwd") is False
    assert is_safe_relative_path("C:\\windows") is False
    assert is_safe_relative_path("") is False
    assert is_safe_relative_path("lib/\x00a.fake") is False


def test_allowlist_rejects_paths_outside_prefix():
    assert is_safe_relative_path(
        "lib/a.fake",
        allowed_prefixes=("lib/",),
    )
    assert not is_safe_relative_path(
        "test/a.fake",
        allowed_prefixes=("lib/",),
    )


# ============================================================
# FULL-FILE MATCH AND APPLY
# ============================================================

def test_expected_old_text_matches_full_file_span():
    text = expected_old_text_from_content(MINI["lib/a.fake"], 2, 3)

    assert text == "two\nthree"


def test_apply_replaces_matching_old_text():
    result = apply_hunks_to_content(
        MINI["lib/a.fake"],
        [PatchHunk(2, 2, "two", "TWO")],
    )

    assert result == "one\nTWO\nthree\nfour"


def test_apply_uses_reverse_start_line_order():
    result = apply_hunks_to_content(
        MINI["lib/a.fake"],
        [
            PatchHunk(1, 1, "one", "ONE"),
            PatchHunk(3, 3, "three", "THREE"),
        ],
    )

    assert result == "ONE\ntwo\nTHREE\nfour"


def test_apply_preserves_trailing_newline():
    with_nl = apply_hunks_to_content(
        "one\ntwo\n",
        [PatchHunk(1, 1, "one", "ONE")],
    )
    without_nl = apply_hunks_to_content(
        "one\ntwo",
        [PatchHunk(1, 1, "one", "ONE")],
    )

    assert with_nl == "ONE\ntwo\n"
    assert without_nl == "ONE\ntwo"


def test_empty_new_text_deletes_the_span():
    result = apply_hunks_to_content(
        MINI["lib/a.fake"],
        [PatchHunk(2, 3, "two\nthree", "")],
    )

    assert result == "one\nfour"


def test_does_not_mutate_caller_file_map():
    original = dict(MINI)
    proposal = _proposal("lib/a.fake", 2, 2, "two", "TWO")

    PatchValidatorService().validate(proposal, original)

    assert original == MINI


def test_multi_file_apply():
    proposal = PatchProposal(
        status=STATUS_OK,
        summary="two files",
        reasoning="test",
        files=[
            PatchFile(
                path="lib/a.fake",
                language="fake",
                hunks=(PatchHunk(1, 1, "one", "ONE"),),
            ),
            PatchFile(
                path="lib/b.fake",
                language="fake",
                hunks=(PatchHunk(2, 2, "beta", "BETA"),),
            ),
        ],
    )

    patched, results, errors = apply_proposal_to_map(proposal, MINI)

    assert errors == []
    assert patched["lib/a.fake"] == "ONE\ntwo\nthree\nfour"
    assert patched["lib/b.fake"] == "alpha\nBETA"
    assert all(item.applied for item in results)


# ============================================================
# REJECTION
# ============================================================

def test_stale_old_text_is_apply_failed():
    result = PatchValidatorService().validate(
        _proposal("lib/a.fake", 2, 2, "wrong", "TWO"),
        MINI,
    )

    assert result.status == STATUS_APPLY_FAILED
    assert result.applied is False
    assert any("old_text mismatch" in error for error in result.errors)


def test_missing_path_is_apply_failed():
    result = PatchValidatorService().validate(
        _proposal("lib/missing.fake", 1, 1, "x", "y"),
        MINI,
    )

    assert result.status == STATUS_APPLY_FAILED
    assert any("not in snapshot" in error for error in result.errors)


def test_path_traversal_is_proposal_invalid():
    result = PatchValidatorService().validate(
        _proposal("../etc/passwd", 1, 1, "x", "y"),
        MINI,
    )

    assert result.status == STATUS_PROPOSAL_INVALID
    assert result.applied is False
    assert any("unsafe path" in error for error in result.errors)


def test_overlapping_hunks_are_proposal_invalid():
    proposal = PatchProposal(
        status=STATUS_OK,
        summary="overlap",
        reasoning="test",
        files=[
            PatchFile(
                path="lib/a.fake",
                language="fake",
                hunks=(
                    PatchHunk(1, 2, "one\ntwo", "x"),
                    PatchHunk(2, 3, "two\nthree", "y"),
                ),
            )
        ],
    )

    result = PatchValidatorService().validate(proposal, MINI)

    assert result.status == STATUS_PROPOSAL_INVALID
    assert any("overlapping" in error for error in result.errors)


def test_invalid_range_is_proposal_invalid():
    result = PatchValidatorService().validate(
        _proposal("lib/a.fake", 3, 1, "x", "y"),
        MINI,
    )

    assert result.status == STATUS_PROPOSAL_INVALID
    assert any("invalid hunk range" in error for error in result.errors)


def test_non_ok_proposal_is_not_applied():
    result = PatchValidatorService().validate(
        _proposal(
            "lib/a.fake",
            2,
            2,
            "two",
            "TWO",
            status=STATUS_INSUFFICIENT_CONTEXT,
        ),
        MINI,
    )

    assert result.status == STATUS_PROPOSAL_INVALID
    assert result.applied is False


# ============================================================
# WORKSPACE
# ============================================================

def test_materialize_writes_files_and_cleanup_removes_them():
    root = materialize(MINI)

    assert (root / "lib" / "a.fake").read_text() == MINI["lib/a.fake"]
    assert cleanup(root) is True
    assert not root.exists()


def test_validator_cleans_up_workspace():
    result = PatchValidatorService().validate(
        _proposal("lib/a.fake", 2, 2, "two", "TWO"),
        MINI,
    )

    assert result.workspace.cleaned_up is True
    assert result.workspace.root is None


# ============================================================
# COMMANDS
# ============================================================

def test_fake_command_success_is_passed():
    runner = FakeValidationCommandRunner(default_exit=0)
    service = PatchValidatorService(command_runner=runner)
    config = ValidationConfig(
        commands=[ValidationCommand("check", ("true",))],
    )

    result = service.validate(
        _proposal("lib/a.fake", 2, 2, "two", "TWO"),
        MINI,
        config=config,
    )

    assert result.status == STATUS_PASSED
    assert result.applied is True
    assert result.validation_passed is True
    assert runner.calls[0]["cwd"] is not None
    assert runner.calls[0]["name"] == "check"


def test_fake_command_failure_is_validation_failed():
    service = PatchValidatorService(
        command_runner=FakeValidationCommandRunner(default_exit=1),
    )
    config = ValidationConfig(
        commands=[ValidationCommand("check", ("false",))],
    )

    result = service.validate(
        _proposal("lib/a.fake", 2, 2, "two", "TWO"),
        MINI,
        config=config,
    )

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.applied is True
    assert result.validation_passed is False
    assert result.commands[0].exit_code == 1


def test_fake_timeout_is_validation_failed():
    service = PatchValidatorService(
        command_runner=FakeValidationCommandRunner(timed_out=True),
    )
    config = ValidationConfig(
        commands=[ValidationCommand("slow", ("sleep", "30"))],
    )

    result = service.validate(
        _proposal("lib/a.fake", 2, 2, "two", "TWO"),
        MINI,
        config=config,
    )

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.commands[0].timed_out is True


def test_no_commands_passes_with_warning():
    result = PatchValidatorService().validate(
        _proposal("lib/a.fake", 2, 2, "two", "TWO"),
        MINI,
        config=ValidationConfig(commands=[]),
    )

    assert result.status == STATUS_PASSED
    assert any("no validation commands" in warning for warning in result.warnings)


def test_shell_runner_timeout():
    service = PatchValidatorService(
        command_runner=ShellValidationCommandRunner(),
    )
    config = ValidationConfig(
        commands=[
            ValidationCommand(
                "sleep",
                (sys.executable, "-c", "import time; time.sleep(10)"),
            )
        ],
        timeout_seconds=0.2,
    )

    result = service.validate(
        _proposal("lib/a.fake", 2, 2, "two", "TWO"),
        MINI,
        config=config,
    )

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.applied is True
    assert result.commands[0].timed_out is True


# ============================================================
# DEMO CANNED PROPOSALS
# ============================================================

def test_task_refresh_canned_proposal_applies():
    files = _load_snapshot("task_refresh_pre_fix.json")
    proposal = _load_proposal("task_refresh_good.json")

    result = PatchValidatorService().validate(proposal, files)

    assert result.status == STATUS_PASSED
    assert result.applied is True
    assert result.files[0].path == "lib/presentation/bloc/task_bloc.dart"


def test_empty_state_canned_proposal_applies():
    files = _load_snapshot("empty_state_pre_fix.json")
    proposal = _load_proposal("empty_state_good.json")

    result = PatchValidatorService().validate(proposal, files)

    assert result.status == STATUS_PASSED
    assert result.applied is True


def test_active_filter_canned_proposal_applies():
    files = _load_snapshot("active_filter_pre_fix.json")
    proposal = _load_proposal("active_filter_good.json")

    result = PatchValidatorService().validate(proposal, files)

    assert result.status == STATUS_PASSED
    assert result.applied is True


def test_task_refresh_stale_old_text_fails_apply():
    files = _load_snapshot("task_refresh_pre_fix.json")
    proposal = _load_proposal("task_refresh_good.json")
    proposal["files"][0]["hunks"][0]["old_text"] = "stale"

    result = PatchValidatorService().validate(proposal, files)

    assert result.status == STATUS_APPLY_FAILED
    assert result.applied is False
