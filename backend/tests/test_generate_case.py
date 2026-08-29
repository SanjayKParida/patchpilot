"""
Tests for the one-command case generator.

Generating a case by hand is three steps, each a chance to pair the
wrong issue with the wrong code — which has already happened once.
The generator's job is to make that impossible, so most of these
tests are about what it REFUSES to produce.

Deterministic and offline: no GitHub, no model.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evalutation.generate_case import (  # noqa: E402
    GenerationError,
    generate,
    slugify,
)

FIX = "afd804edc491fb08e2bb2eed9df4bbfc6985edca"
PARENT = "d8e50b735c78620103b1ab031dcd9070c123a785"

TASK_BLOC = "lib/presentation/bloc/task_bloc.dart"


class FakeGithub:
    def __init__(self, changed=None, parent=PARENT):
        self.changed = changed or [
            {"filename": TASK_BLOC, "status": "modified"},
            {
                "filename": "test/bloc/task_bloc_test.dart",
                "status": "modified",
            },
        ]
        self.parent = parent
        self.source_calls = []

    def get_commit(self, owner, repo, ref):
        if ref in (FIX, "HEAD"):
            return {"sha": FIX, "parents": [{"sha": self.parent}]}
        if ref == self.parent:
            return {"sha": self.parent, "parents": []}
        raise Exception(f"404 for {ref}")

    def compare_commits(self, owner, repo, base, head):
        return {"files": self.changed}

    def get_repository_source_files(self, owner, repo, ref=None):
        self.source_calls.append(ref)
        return [
            {"path": TASK_BLOC, "sha": "b1", "content": "class TaskBloc {}"}
        ]

    def get_issue(self, owner, repo, number):
        return {
            "number": number,
            "title": "Task list stuck on the loading spinner",
            "body": "Refreshing never clears it.",
        }

    def get_issues(self, owner, repo):
        return [self.get_issue(owner, repo, 1)]


class FakeLLM:
    available = True

    def __init__(self, signals=None):
        self.signals = signals if signals is not None else [
            {"term": "refresh", "type": "behavior"},
            {"term": "loading", "type": "behavior"},
        ]

    def ask(self, prompt):
        return json.dumps({"signals": self.signals})


def _generate(tmp_path, github=None, llm=None, **kwargs):
    return generate(
        github or FakeGithub(),
        llm or FakeLLM(),
        "SanjayKParida",
        "patchpilot-diagnosis-demo",
        issue_number=1,
        fix_commit=FIX,
        fixture_dir=tmp_path / "fixtures",
        case_dir=tmp_path / "cases",
        **kwargs,
    )


# ============================================================
# NAMING
# ============================================================

@pytest.mark.parametrize(
    "title,expected",
    [
        ("Task list stuck on the loading spinner", "task_list_stuck_loading_spinner"),
        ("App is not working", "working"),
        ("", "issue_7"),
        ("!!! ???", "issue_7"),
    ],
)
def test_slugify(title, expected):
    assert slugify(title, 7) == expected


def test_an_explicit_name_overrides_the_derived_one(tmp_path):
    result = _generate(tmp_path, name="task_refresh")

    assert result["name"] == "task_refresh"
    assert result["fixture"].name == "task_refresh_pre_fix.json"
    assert result["case"].name == "task_refresh.json"


# ============================================================
# WHAT IT PRODUCES
# ============================================================

def test_both_files_are_written(tmp_path):
    result = _generate(tmp_path)

    assert result["fixture"].exists()
    assert result["case"].exists()


def test_the_case_has_every_field_the_benchmark_requires(tmp_path):
    case = json.loads(_generate(tmp_path)["case"].read_text())

    for field in (
        "owner",
        "repo",
        "issue_number",
        "fix_commit",
        "snapshot",
        "title",
        "body",
    ):
        assert case.get(field), field


def test_the_snapshot_is_taken_at_the_fix_parent(tmp_path):
    github = FakeGithub()

    result = _generate(tmp_path, github=github)

    assert github.source_calls == [PARENT]
    assert result["snapshot"]["commit"] == PARENT
    assert result["ground_truth"]["parent_commit"] == PARENT


def test_signals_are_pinned_with_an_explanation(tmp_path):
    """
    Every committed case must be reproducible. A generated case that
    skipped pinning would quietly reintroduce the noise Step 1 removed.
    """

    case = json.loads(_generate(tmp_path)["case"].read_text())

    assert case["signals"] == [
        {"term": "refresh", "type": "behavior"},
        {"term": "loading", "type": "behavior"},
    ]
    assert case["signals_note"]


def test_ground_truth_excludes_the_test_file(tmp_path):
    result = _generate(tmp_path)

    assert result["ground_truth"]["affected_files"] == [TASK_BLOC]


# ============================================================
# WHAT IT REFUSES
# ============================================================

def test_a_fix_touching_no_product_file_is_refused(tmp_path):
    """
    Nothing for retrieval to find, so the case is unscoreable.
    """

    github = FakeGithub(
        changed=[{"filename": "README.md", "status": "modified"}]
    )

    with pytest.raises(GenerationError, match="no product source"):
        _generate(tmp_path, github=github)


def test_nothing_is_downloaded_before_the_answer_is_known(tmp_path):
    """
    Ground truth is derived first, so an unscoreable case costs no
    snapshot download.
    """

    github = FakeGithub(
        changed=[{"filename": "CHANGELOG.md", "status": "modified"}]
    )

    with pytest.raises(GenerationError):
        _generate(tmp_path, github=github)

    assert github.source_calls == []


def test_an_initial_commit_is_refused(tmp_path):
    github = FakeGithub()
    github.get_commit = lambda o, r, ref: {"sha": FIX, "parents": []}

    with pytest.raises(Exception, match="no parent"):
        _generate(tmp_path, github=github)


def test_empty_signal_extraction_is_refused(tmp_path):
    with pytest.raises(GenerationError, match="reproducible"):
        _generate(tmp_path, llm=FakeLLM(signals=[]))


def test_existing_files_are_not_silently_overwritten(tmp_path):
    _generate(tmp_path, name="task_refresh")

    with pytest.raises(GenerationError, match="--force"):
        _generate(tmp_path, name="task_refresh")


def test_force_overwrites(tmp_path):
    first = _generate(tmp_path, name="task_refresh")
    first["case"].write_text('{"stale": true}')

    _generate(tmp_path, name="task_refresh", force=True)

    case = json.loads(first["case"].read_text())
    assert "stale" not in case
    assert case["issue_number"] == 1


def test_a_snapshot_that_is_not_the_fix_parent_is_refused(
    tmp_path,
    monkeypatch,
):
    """
    The exact failure this tool exists to prevent: code from one
    commit paired with an answer derived from another.
    """

    import evalutation.generate_case as module

    def wrong_snapshot(github, owner, repo, **kwargs):
        return {
            "commit": "0" * 40,
            "issue": {"number": 1, "title": "t", "body": "b"},
            "files": [],
        }

    monkeypatch.setattr(module, "capture", wrong_snapshot)

    with pytest.raises(GenerationError, match="parent"):
        _generate(tmp_path)
