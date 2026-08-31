"""
Deterministic tests for the patch repair benchmark.

No GitHub, no model, no subprocess. Every case is prepared by hand so
the harness itself is what is under test, not the pipeline feeding it.

The rule these tests exist to protect: a patch that differs from the
historical fix is not thereby wrong. Several assert exactly that.
"""

import argparse
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The evaluation harness lives at the repository root, outside the
# backend package. Same approach as test_commit_benchmark.py.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.patch_types import (
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_INVALID,
    STATUS_OK,
    PatchFile,
    PatchHunk,
    PatchProposal,
)
from app.services.patch_validation_types import (
    CommandResult,
    ValidationCommand,
)
from app.services.patch_validator_service import PatchValidatorService
from app.services.validation_command_runner import (
    FakeValidationCommandRunner,
)

from evalutation import patch_benchmark as bench  # noqa: E402


COMMIT_CASES = REPO_ROOT / "evalutation" / "cases" / "commit_grounded"


# ============================================================
# HAND-BUILT INPUTS
# ============================================================

FILES = [
    {
        "path": "lib/bloc/task_bloc.dart",
        "content": "one\ntwo\nthree\nfour\n",
    },
    {
        "path": "lib/ui/task_page.dart",
        "content": "alpha\nbeta\ngamma\n",
    },
]

RUNNABLE_FILES = FILES + [
    {"path": "pubspec.yaml", "content": "name: demo\n"},
]


def hunk_proposal(edits, status=STATUS_OK):
    """`edits` maps path -> (start, end, old, new)."""

    return PatchProposal(
        status=status,
        summary="repair",
        reasoning="because",
        confidence=0.9,
        files=[
            PatchFile(
                path=path,
                language="dart",
                hunks=(PatchHunk(*edit),),
            )
            for path, edit in edits.items()
        ],
    )


def working_proposal():
    return hunk_proposal(
        {"lib/bloc/task_bloc.dart": (2, 2, "two", "TWO")}
    )


def prepared(
    proposal_files=("lib/bloc/task_bloc.dart",),
    issue_number=1,
):
    """
    A prepared case, as `context_benchmark.prepare_case` would return.

    Built literally so no network or model is involved.
    """

    return {
        "case": {"issue_number": issue_number, "owner": "o", "repo": "r"},
        "case_path": "evalutation/cases/commit_grounded/task_refresh.json",
        "snapshot": {"issue": {"title": "t", "body": "b"}},
        "files": FILES,
        "issue": {"title": "Spinner stuck", "body": "never completes"},
        "analysis": {"ranked": [], "direct_evidence": []},
        "diagnosis": {"root_cause": "x", "root_cause_locations": []},
        "ground_truth": {
            "affected_files": list(proposal_files),
            "repository": "o/r",
            "fix_commit": "f" * 40,
            "parent_commit": "p" * 40,
        },
        "changed_lines": {"lib/bloc/task_bloc.dart": [2]},
        "signals_pinned": True,
    }


class FakeGenerator:
    """Returns a canned proposal, or raises, without a model."""

    def __init__(self, proposal=None, error=None):
        self.proposal = proposal
        self.error = error
        self.calls = 0

    def generate(self, issue, diagnosis, context_package):
        self.calls += 1

        if self.error:
            raise RuntimeError(self.error)

        return self.proposal


@pytest.fixture
def package(monkeypatch):
    """
    Stub context building.

    ContextBuilder has its own benchmark and its own tests; rebuilding
    a real package here would couple these tests to it for no gain.
    """

    monkeypatch.setattr(
        bench,
        "build_context_package",
        lambda *args, **kwargs: object(),
    )


def evaluate(prepared_case, **kwargs):
    kwargs.setdefault("source", bench.SOURCE_GENERATED)
    kwargs.setdefault("generator", FakeGenerator(working_proposal()))
    return bench.evaluate_prepared(prepared_case, **kwargs)


# ============================================================
# THE HAPPY PATH
# ============================================================

def test_a_generated_patch_applies_and_validates(package):
    result = evaluate(prepared())

    assert result["patch_generated"] is True
    assert result["patch_status"] == STATUS_OK
    assert result["patch_applied"] is True
    assert result["validation_passed"] is True
    assert result["stage"] == bench.STAGE_PASSED
    assert result["proposal_source"] == bench.SOURCE_GENERATED


def test_validation_commands_are_flutter_conventions(package):
    data = prepared()
    data["files"] = RUNNABLE_FILES
    result = evaluate(data)

    assert [command["argv"] for command in result["commands"]] == [
        ["flutter", "pub", "get"],
        ["flutter", "analyze"],
        ["flutter", "test"],
    ]


def test_the_profile_label_says_the_runner_was_fake(package):
    """
    A PASS from the fake runner is not a compile check, and the report
    must not let the two be confused.
    """

    data = prepared()
    data["files"] = RUNNABLE_FILES
    result = evaluate(data)

    assert result["validation_profile"] == bench.PROFILE_FAKE
    assert result["validation_profile_label"] == "fake runner"


def test_source_only_trees_do_not_fake_flutter_commands(package):
    result = evaluate(prepared())

    assert result["commands"] == []
    assert "not runnable" in result["validation_profile_label"]
    assert result["patch_applied"] is True


# ============================================================
# FAILURE STAGES
# ============================================================

def test_a_raising_generator_is_a_generation_failure(package):
    result = evaluate(
        prepared(),
        generator=FakeGenerator(error="model unavailable"),
    )

    assert result["stage"] == bench.STAGE_GENERATION_FAILURE
    assert result["patch_generated"] is False
    assert result["patch_applied"] is False
    assert any("model unavailable" in e for e in result["errors"])


def test_a_model_failure_is_not_scored_as_a_bad_patch(package):
    """
    An unavailable model is a fact about the run, not a repair
    failure. It must be visible as its own stage.
    """

    result = evaluate(
        prepared(),
        generator=FakeGenerator(error="503"),
    )

    assert result["stage"] == bench.STAGE_GENERATION_FAILURE
    assert result["validation_status"] is None


def test_an_insufficient_context_proposal_is_a_generation_failure(
    package,
):
    proposal = PatchProposal(
        status=STATUS_INSUFFICIENT_CONTEXT,
        summary="",
        reasoning="",
    )

    result = evaluate(prepared(), generator=FakeGenerator(proposal))

    assert result["stage"] == bench.STAGE_GENERATION_FAILURE
    assert result["patch_generated"] is False


def test_an_invalid_proposal_is_reported_as_such(package):
    proposal = PatchProposal(
        status=STATUS_INVALID,
        summary="",
        reasoning="",
        errors=["hunk did not anchor"],
    )

    result = evaluate(prepared(), generator=FakeGenerator(proposal))

    assert result["stage"] == bench.STAGE_PROPOSAL_INVALID
    assert result["patch_generated"] is False


def test_a_hunk_that_does_not_match_is_an_apply_failure(package):
    """
    The old text does not match the pre-fix snapshot, so there is
    nothing to anchor the edit to.
    """

    proposal = hunk_proposal(
        {"lib/bloc/task_bloc.dart": (2, 2, "NOT THE TEXT", "TWO")}
    )

    result = evaluate(prepared(), generator=FakeGenerator(proposal))

    assert result["stage"] == bench.STAGE_APPLY_FAILURE
    assert result["patch_generated"] is True
    assert result["patch_applied"] is False
    assert result["validation_passed"] is False


def test_a_failing_command_is_a_validation_failure(package):
    validator = PatchValidatorService(
        command_runner=FakeValidationCommandRunner(
            results={"analyze": 1},
        )
    )

    data = prepared()
    data["files"] = RUNNABLE_FILES
    result = evaluate(data, validator=validator)

    assert result["stage"] == bench.STAGE_VALIDATION_FAILURE
    assert result["patch_applied"] is True
    assert result["validation_passed"] is False


def test_every_stage_is_reachable_and_named(package):
    """
    Stage names are compared in reports and baselines, so the set is
    pinned rather than left to drift.
    """

    assert bench.STAGES == (
        "generation_failure",
        "proposal_invalid",
        "apply_failure",
        "validation_failure",
        "passed",
    )


# ============================================================
# A DIFFERENT PATCH IS STILL A VALID PATCH
# ============================================================

def test_a_patch_unlike_the_historical_fix_still_passes(package):
    """
    The core evaluation rule. The generated patch touches a file the
    historical fix never did, and does not touch the one it did. It
    applies and validates, so it passes — recall and precision merely
    record the divergence.
    """

    proposal = hunk_proposal(
        {"lib/ui/task_page.dart": (1, 1, "alpha", "ALPHA")}
    )

    result = evaluate(
        prepared(proposal_files=("lib/bloc/task_bloc.dart",)),
        generator=FakeGenerator(proposal),
    )

    assert result["stage"] == bench.STAGE_PASSED
    assert result["validation_passed"] is True

    metrics = result["metrics"]
    assert metrics["file_recall"] == 0.0
    assert metrics["expected_file_touched"] is False
    assert metrics["unexpected_files"] == ["lib/ui/task_page.dart"]


def test_extra_files_lower_precision_without_failing_the_case(package):
    proposal = hunk_proposal({
        "lib/bloc/task_bloc.dart": (2, 2, "two", "TWO"),
        "lib/ui/task_page.dart": (1, 1, "alpha", "ALPHA"),
    })

    result = evaluate(
        prepared(proposal_files=("lib/bloc/task_bloc.dart",)),
        generator=FakeGenerator(proposal),
    )

    assert result["stage"] == bench.STAGE_PASSED
    assert result["metrics"]["file_recall"] == 1.0
    assert result["metrics"]["file_precision"] == 0.5


def test_a_multi_file_patch_applies_every_file(package):
    proposal = hunk_proposal({
        "lib/bloc/task_bloc.dart": (2, 2, "two", "TWO"),
        "lib/ui/task_page.dart": (1, 1, "alpha", "ALPHA"),
    })

    result = evaluate(
        prepared(
            proposal_files=(
                "lib/bloc/task_bloc.dart",
                "lib/ui/task_page.dart",
            )
        ),
        generator=FakeGenerator(proposal),
    )

    assert result["stage"] == bench.STAGE_PASSED
    assert len(result["file_results"]) == 2
    assert all(item["applied"] for item in result["file_results"])
    assert result["metrics"]["file_recall"] == 1.0
    assert result["metrics"]["file_precision"] == 1.0


# ============================================================
# SCORING
# ============================================================

@pytest.mark.parametrize(
    "expected,predicted,recall,precision",
    [
        (["a"], ["a"], 1.0, 1.0),
        (["a", "b"], ["a"], 0.5, 1.0),
        (["a"], ["a", "b"], 1.0, 0.5),
        (["a"], ["b"], 0.0, 0.0),
        (["a"], [], 0.0, 0.0),
        ([], ["a"], 1.0, 0.0),
    ],
)
def test_file_scoring(expected, predicted, recall, precision):
    score = bench.score_files(expected, predicted)

    assert score["file_recall"] == recall
    assert score["file_precision"] == precision


def test_scoring_reports_both_directions_of_difference():
    score = bench.score_files(["a", "b"], ["b", "c"])

    assert score["matched_files"] == ["b"]
    assert score["missing_files"] == ["a"]
    assert score["unexpected_files"] == ["c"]
    assert score["expected_file_touched"] is False


# ============================================================
# CANNED PROPOSALS
# ============================================================

def test_all_three_cases_have_a_canned_proposal():
    for case in sorted(COMMIT_CASES.glob("*.json")):
        path = bench.canned_proposal_path(case)
        assert path.exists(), f"missing canned proposal for {case.name}"


def test_a_canned_proposal_round_trips():
    proposal = bench.load_canned_proposal(
        COMMIT_CASES / "task_refresh.json"
    )

    assert proposal.status == STATUS_OK
    assert proposal.files
    assert all(file.hunks for file in proposal.files)


def test_generated_proposals_require_a_configured_generator(package):
    """
    Regression. Defaulting to a bare PatchGeneratorService() silently
    builds one with no model, and every case reports "LLM service is
    not configured" as though the patch were at fault.
    """

    with pytest.raises(bench.PatchBenchmarkError):
        bench.evaluate_prepared(
            prepared(),
            source=bench.SOURCE_GENERATED,
            generator=None,
        )


def test_a_missing_canned_proposal_is_an_explicit_error():
    with pytest.raises(bench.PatchBenchmarkError):
        bench.load_canned_proposal("cases/does_not_exist.json")


def test_the_canned_source_never_calls_the_generator(package):
    generator = FakeGenerator(working_proposal())

    bench.evaluate_prepared(
        prepared(),
        source=bench.SOURCE_CANNED,
        generator=generator,
    )

    assert generator.calls == 0


# ============================================================
# ROLLUP
# ============================================================

def make_result(number, generated=True, applied=True, passed=True,
                stage=bench.STAGE_PASSED, recall=1.0, precision=1.0):
    return {
        "case": f"case_{number}.json",
        "issue": {"number": number, "title": f"issue {number}"},
        "patch_generated": generated,
        "patch_applied": applied,
        "validation_passed": passed,
        "stage": stage,
        "metrics": {
            "file_recall": recall,
            "file_precision": precision,
            "expected_files": [],
            "predicted_files": [],
            "missing_files": [],
            "unexpected_files": [],
        },
    }


def test_the_rollup_counts_each_stage():
    aggregate = bench.summarize([
        make_result(1),
        make_result(
            2,
            passed=False,
            stage=bench.STAGE_VALIDATION_FAILURE,
            precision=0.5,
        ),
        make_result(
            3,
            generated=False,
            applied=False,
            passed=False,
            stage=bench.STAGE_GENERATION_FAILURE,
            recall=0.0,
            precision=0.0,
        ),
    ])

    assert aggregate["scored"] == 3
    assert aggregate["generated"] == 2
    assert aggregate["applied"] == 2
    assert aggregate["validated"] == 1
    assert aggregate["stages"][bench.STAGE_PASSED] == 1
    assert aggregate["stages"][bench.STAGE_VALIDATION_FAILURE] == 1
    assert aggregate["stages"][bench.STAGE_GENERATION_FAILURE] == 1


def test_a_failed_case_does_not_destroy_the_others():
    aggregate = bench.summarize([
        make_result(1),
        {"case": "broken.json", "failed": True, "error": "no network"},
        make_result(2),
    ])

    assert aggregate["cases"] == 3
    assert aggregate["scored"] == 2
    assert aggregate["failed"] == 1
    assert aggregate["file_recall"] == 1.0


def test_failed_cases_are_excluded_from_the_means():
    aggregate = bench.summarize([
        make_result(1, recall=1.0),
        {"case": "broken.json", "failed": True, "error": "boom"},
    ])

    assert aggregate["file_recall"] == 1.0


def test_the_rollup_is_deterministic():
    results = [
        make_result(1),
        make_result(2, passed=False, stage=bench.STAGE_VALIDATION_FAILURE),
    ]

    assert bench.summarize(results) == bench.summarize(results)


def test_run_all_records_a_failure_and_keeps_going(monkeypatch):
    calls = []

    def fake_run_case(case, github, llm, **kwargs):
        calls.append(case)

        if case["issue_number"] == 2:
            raise RuntimeError("case two exploded")

        return make_result(case["issue_number"])

    monkeypatch.setattr(bench, "load_case", lambda path: {
        "issue_number": int(Path(path).stem)
    })
    monkeypatch.setattr(bench, "run_case", fake_run_case)

    results = bench.run_all(
        ["1.json", "2.json", "3.json"],
        github=None,
        llm=None,
    )

    assert len(results) == 3
    assert results[1]["failed"] is True
    assert "case two exploded" in results[1]["error"]
    assert results[2]["issue"]["number"] == 3


# ============================================================
# CASE DISCOVERY
# ============================================================

def test_the_three_controlled_cases_are_discovered():
    from evalutation.commit_benchmark import discover_cases

    found = {Path(path).stem for path in discover_cases(COMMIT_CASES)}

    assert found == {"task_refresh", "empty_state", "active_filter"}


# ============================================================
# PROFILES
# ============================================================

def test_the_none_profile_configures_no_commands():
    config, runner, label = bench.build_validation(bench.PROFILE_NONE)

    assert config.commands == []
    assert runner is None
    assert label == "no commands"


def test_the_shell_profile_skips_commands_without_pubspec():
    config, runner, label = bench.build_validation(bench.PROFILE_SHELL)

    assert config.commands == []
    assert runner is None
    assert "not runnable" in label
    assert "pubspec.yaml" in label


def test_the_shell_profile_uses_the_real_runner_when_runnable():
    config, runner, label = bench.build_validation(
        bench.PROFILE_SHELL,
        files={"pubspec.yaml": "name: demo\n", "lib/main.dart": ""},
    )

    assert [c.argv for c in config.commands] == [
        ("flutter", "pub", "get"),
        ("flutter", "analyze"),
        ("flutter", "test"),
    ]
    assert runner.__class__.__name__ == "ShellValidationCommandRunner"
    assert label == "real toolchain"


def test_the_fake_profile_skips_commands_on_source_only_fixtures():
    config, runner, label = bench.build_validation(
        bench.PROFILE_FAKE,
        files=[{"path": "lib/main.dart"}],
    )

    assert config.commands == []
    assert runner is None
    assert "not runnable" in label


# ============================================================
# SNAPSHOT OVERRIDE
# ============================================================

def _write_snapshot(path, marker):
    path.write_text(json.dumps({
        "commit": "c" * 40,
        "issue": {"number": 1, "title": marker, "body": ""},
        "files": [
            {"path": f"lib/{marker}.dart", "sha": "s", "content": marker},
        ],
    }))


def test_snapshot_override_is_used(tmp_path):
    case_file = tmp_path / "from_case.json"
    override = tmp_path / "override.json"
    _write_snapshot(case_file, "from_case")
    _write_snapshot(override, "override")

    case = {"snapshot": str(case_file)}
    loaded = bench.snapshot_for_case(case, snapshot_path=str(override))

    assert loaded["files"][0]["path"] == "lib/override.dart"
    assert case["snapshot"] == str(case_file)


def test_without_override_the_case_snapshot_is_used(tmp_path):
    case_file = tmp_path / "from_case.json"
    _write_snapshot(case_file, "from_case")

    case = {"snapshot": str(case_file)}
    loaded = bench.snapshot_for_case(case)

    assert loaded["files"][0]["path"] == "lib/from_case.dart"


def test_invalid_snapshot_override_fails_clearly(tmp_path):
    missing = tmp_path / "does-not-exist.json"

    with pytest.raises(bench.BenchmarkError, match="No snapshot"):
        bench.snapshot_for_case(
            {"snapshot": str(tmp_path / "unused.json")},
            snapshot_path=str(missing),
        )


def test_cli_snapshot_override_is_refused_with_cases(tmp_path):
    args = argparse.Namespace(
        snapshot=str(tmp_path / "full.json"),
        cases="evalutation/cases/commit_grounded",
        case=None,
    )

    with pytest.raises(bench.PatchBenchmarkError, match="--case"):
        bench.snapshot_from_args(args)


def test_cli_missing_snapshot_override_is_a_patch_benchmark_error(
    tmp_path,
):
    args = argparse.Namespace(
        snapshot=str(tmp_path / "missing.json"),
        cases=None,
        case="evalutation/cases/commit_grounded/task_refresh.json",
    )

    with pytest.raises(bench.PatchBenchmarkError, match="No snapshot"):
        bench.snapshot_from_args(args)
