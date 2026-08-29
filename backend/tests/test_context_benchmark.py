"""
Tests for the context recall benchmark harness.

Scoring is deterministic and offline. The runner is exercised with
faked GitHub and LLM dependencies so the default suite never calls
either.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evalutation.context_benchmark import (  # noqa: E402
    ContextBenchmarkError,
    derive_changed_lines,
    parse_patch_changed_lines,
    run_case,
    score_context_files,
    score_efficiency,
    score_line_recall,
    union_lines,
    verify_snapshot_parent,
)
from evalutation.commit_benchmark import load_case, load_snapshot  # noqa: E402

FIXTURE = (
    REPO_ROOT
    / "evalutation"
    / "fixtures"
    / "task_refresh_pre_fix.json"
)

FIX_COMMIT = "afd804edc491fb08e2bb2eed9df4bbfc6985edca"
PARENT = "d8e50b735c78620103b1ab031dcd9070c123a785"
TASK_BLOC = "lib/presentation/bloc/task_bloc.dart"


def _case(tmp_path, **overrides):
    case = {
        "owner": "SanjayKParida",
        "repo": "patchpilot-diagnosis-demo",
        "issue_number": 1,
        "fix_commit": FIX_COMMIT,
        "snapshot": str(FIXTURE),
        "title": "Task list stuck on the loading spinner",
        "body": "Refreshing never leaves the spinner.",
        "signals": [
            {"term": "refresh", "type": "behavior"},
            {"term": "loading", "type": "behavior"},
            {"term": "task", "type": "domain"},
        ],
    }
    case.update(overrides)

    path = Path(tmp_path)
    path.mkdir(parents=True, exist_ok=True)
    path = path / "case.json"
    path.write_text(json.dumps(case))

    return path


class FakeGithub:
    def __init__(self, files, parents=None, patch=""):
        self._files = files
        self._parents = (
            [{"sha": PARENT}] if parents is None else parents
        )
        self._patch = patch

    def get_commit(self, owner, repo, ref):
        return {"sha": FIX_COMMIT, "parents": self._parents}

    def compare_commits(self, owner, repo, base, head):
        return {"files": self._files}

    def _entry(self, filename, status="modified", patch=None):
        return {
            "filename": filename,
            "status": status,
            "patch": self._patch if patch is None else patch,
        }


class FakeLLM:
    available = True

    def __init__(self, payload=None):
        self.payload = payload or {
            "root_cause": "TaskBloc never emits TaskLoaded on refresh.",
            "confidence": 0.9,
            "relevant_files": [TASK_BLOC],
            "root_cause_symbols": ["TaskBloc"],
            "symbols": ["TaskLoading"],
            "explanation": "Refresh handler stops in TaskLoading.",
            "suggested_fix": "emit(TaskLoaded(tasks)) after refresh.",
        }

    def ask(self, prompt):
        if "root_cause" not in prompt:
            return json.dumps({"signals": []})
        return json.dumps(self.payload)


# ============================================================
# PATCH PARSING
# ============================================================

def test_parse_patch_collects_removed_old_file_lines():
    patch = "\n".join([
        "@@ -10,4 +10,5 @@",
        " context",
        "-old line",
        "+new line",
        " trailing",
    ])

    assert parse_patch_changed_lines(patch) == {11}


def test_empty_or_missing_patch_yields_no_changed_lines():
    assert parse_patch_changed_lines("") == set()
    assert parse_patch_changed_lines(None) == set()


# ============================================================
# FILE RECALL
# ============================================================

def test_perfect_file_coverage_scores_one():
    score = score_context_files(
        [TASK_BLOC],
        [{"path": TASK_BLOC, "start_line": 1, "end_line": 10}],
    )

    assert score["context_file_recall"] == 1.0
    assert score["missing_files"] == []
    assert score["context_files"] == [TASK_BLOC]


def test_a_missing_file_lowers_recall():
    score = score_context_files(
        [TASK_BLOC, "lib/other.dart"],
        [{"path": TASK_BLOC, "start_line": 1, "end_line": 5}],
    )

    assert score["context_file_recall"] == 0.5
    assert score["missing_files"] == ["lib/other.dart"]


# ============================================================
# LINE RECALL
# ============================================================

def test_partial_line_coverage_is_reported():
    score = score_line_recall(
        {TASK_BLOC: [10, 11, 12]},
        [
            {"path": TASK_BLOC, "start_line": 1, "end_line": 10},
        ],
    )

    assert score["line_recall"] == pytest.approx(1 / 3)
    assert score["uncovered_lines"] == {TASK_BLOC: [11, 12]}


def test_overlapping_slices_do_not_double_count_lines():
    changed = {TASK_BLOC: [10, 11, 12]}
    slices = [
        {"path": TASK_BLOC, "start_line": 8, "end_line": 11},
        {"path": TASK_BLOC, "start_line": 10, "end_line": 12},
    ]

    score = score_line_recall(changed, slices)

    assert score["line_recall"] == 1.0
    assert score["covered_changed_line_count"] == 3


def test_union_lines_deduplicates_ranges():
    assert union_lines([(1, 5), (4, 8)]) == set(range(1, 9))


# ============================================================
# EFFICIENCY
# ============================================================

def test_extra_context_reduces_efficiency_only():
    files = [
        {"path": TASK_BLOC, "content": "\n".join(f"L{i}" for i in range(1, 11))},
        {
            "path": "lib/noise.dart",
            "content": "\n".join(f"N{i}" for i in range(1, 11)),
        },
    ]
    changed = {TASK_BLOC: [3]}

    minimal_slices = [{"path": TASK_BLOC, "start_line": 1, "end_line": 5}]
    extra_slices = minimal_slices + [
        {"path": "lib/noise.dart", "start_line": 1, "end_line": 5},
    ]

    minimal_recall = score_line_recall(changed, minimal_slices)
    extra_recall = score_line_recall(changed, extra_slices)
    minimal = score_efficiency(minimal_slices, files)
    extra = score_efficiency(extra_slices, files)

    assert minimal_recall["line_recall"] == extra_recall["line_recall"] == 1.0
    assert minimal["context_lines_used"] == 5
    assert extra["context_lines_used"] == 10
    assert extra["efficiency"] > minimal["efficiency"]
    assert minimal["repository_lines"] == extra["repository_lines"] == 20


# ============================================================
# SNAPSHOT VALIDATION
# ============================================================

def test_snapshot_parent_mismatch_is_refused():
    with pytest.raises(ContextBenchmarkError, match="not the fix parent"):
        verify_snapshot_parent(
            {"commit": "deadbeef" * 5},
            {
                "parent_commit": PARENT,
                "fix_commit": FIX_COMMIT,
            },
        )


def test_matching_snapshot_parent_is_accepted():
    verify_snapshot_parent(
        {"commit": PARENT},
        {"parent_commit": PARENT, "fix_commit": FIX_COMMIT},
    )


# ============================================================
# END TO END, OFFLINE
# ============================================================

PATCH = "\n".join([
    "@@ -42,4 +42,5 @@",
    "       emit(TaskLoading());",
    "-      emit(const TaskLoaded([]));",
    "+      emit(TaskLoaded(tasks));",
    "     });",
])


def test_run_case_produces_metrics(tmp_path):
    github = FakeGithub(
        [
            {
                "filename": TASK_BLOC,
                "status": "modified",
                "patch": PATCH,
            },
            {
                "filename": "test/presentation/bloc/task_bloc_test.dart",
                "status": "modified",
                "patch": "@@ -1,1 +1,1 @@\n-old\n+new",
            },
        ]
    )

    result = run_case(
        load_case(_case(tmp_path)),
        github=github,
        llm=FakeLLM(),
    )

    metrics = result["metrics"]

    assert metrics["context_file_recall"] == 1.0
    assert metrics["expected_files"] == [TASK_BLOC]
    assert TASK_BLOC in metrics["context_files"]
    assert metrics["changed_lines"][TASK_BLOC]
    assert result["snapshot_commit"] == PARENT
    assert result["slices"]


def test_running_twice_is_deterministic(tmp_path):
    github = FakeGithub(
        [{"filename": TASK_BLOC, "status": "modified", "patch": PATCH}]
    )
    case = load_case(_case(tmp_path))
    llm = FakeLLM()

    first = run_case(case, github=github, llm=llm)
    second = run_case(case, github=github, llm=llm)

    assert first["metrics"] == second["metrics"]
    assert first["slices"] == second["slices"]


def test_no_product_line_changes_yield_perfect_line_recall(tmp_path):
    github = FakeGithub(
        [{"filename": "README.md", "status": "modified", "patch": PATCH}]
    )

    result = run_case(
        load_case(_case(tmp_path)),
        github=github,
        llm=FakeLLM({
            "root_cause": "x",
            "confidence": 0.1,
            "relevant_files": [],
            "explanation": "none",
            "suggested_fix": "none",
        }),
    )

    assert result["metrics"]["changed_lines"] == {}
    assert result["metrics"]["line_recall"] == 1.0


def test_derive_changed_lines_filters_like_ground_truth():
    github = FakeGithub(
        [
            {
                "filename": TASK_BLOC,
                "status": "modified",
                "patch": PATCH,
            },
            {
                "filename": "test/presentation/bloc/task_bloc_test.dart",
                "status": "modified",
                "patch": PATCH,
            },
        ]
    )

    ground_truth, changed = derive_changed_lines(
        github,
        "o",
        "r",
        FIX_COMMIT,
    )

    assert ground_truth["affected_files"] == [TASK_BLOC]
    assert TASK_BLOC in changed
    assert "test/presentation/bloc/task_bloc_test.dart" not in changed
