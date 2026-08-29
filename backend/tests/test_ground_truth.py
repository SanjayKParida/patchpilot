"""
Tests for commit-derived benchmark ground truth.

A fix commit already contains the answer to "which files should
retrieval have found". The risk is the noise around it: real fixes
also touch tests, changelogs and generated code, and counting those
turns a benchmark into a coin toss.

The offline tests pin the filtering. The integration tests confirm
the three known commits produce exactly the expected files.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evalutation.ground_truth import (  # noqa: E402
    GroundTruthError,
    derive_ground_truth,
    exclusion_reason,
    pre_fix_path,
)

FIX = "f" * 40
PARENT = "p" * 40


class FakeGithub:
    def __init__(self, files, parents=None):
        self._files = files
        self._parents = (
            [{"sha": PARENT}] if parents is None else parents
        )
        self.compared = None

    def get_commit(self, owner, repo, ref):
        if ref != FIX:
            raise Exception(f"404 for {ref}")
        return {"sha": FIX, "parents": self._parents}

    def compare_commits(self, owner, repo, base, head):
        self.compared = (base, head)
        return {"files": self._files}


def _changed(filename, status="modified", **extra):
    return {"filename": filename, "status": status, **extra}


def _derive(files, **kwargs):
    github = FakeGithub(files, **kwargs)
    return github, derive_ground_truth(github, "o", "r", FIX)


# ============================================================
# WHAT COUNTS AS PRODUCT SOURCE
# ============================================================

@pytest.mark.parametrize(
    "path",
    [
        "lib/presentation/bloc/task_bloc.dart",
        "lib/data/datasources/task_local_data_source.dart",
        "lib/domain/usecases/get_filtered_tasks.dart",
        "lib/main.dart",
    ],
)
def test_product_source_is_kept(path):
    assert exclusion_reason(path) is None


@pytest.mark.parametrize(
    "path,reason",
    [
        # Tests
        ("test/presentation/bloc/task_bloc_test.dart", "not_product_source"),
        ("lib/presentation/task_bloc_test.dart", "test"),
        ("integration_test/app_test.dart", "not_product_source"),
        # Docs, changelogs, lockfiles, config
        ("README.md", "not_product_source"),
        ("CHANGELOG.md", "not_product_source"),
        ("pubspec.yaml", "not_product_source"),
        ("pubspec.lock", "not_product_source"),
        ("analysis_options.yaml", "not_product_source"),
        (".github/workflows/ci.yml", "not_product_source"),
        # Platform folders
        ("android/app/build.gradle", "not_product_source"),
        ("ios/Runner/Info.plist", "not_product_source"),
        # Generated
        ("lib/models/task.g.dart", "generated"),
        ("lib/models/task.freezed.dart", "generated"),
        ("lib/router.gr.dart", "generated"),
        ("lib/di/injection.config.dart", "generated"),
        ("lib/generated_plugin_registrant.dart", "generated"),
    ],
)
def test_non_product_files_are_excluded(path, reason):
    assert exclusion_reason(path) == reason


# ============================================================
# DERIVATION
# ============================================================

def test_only_product_files_become_ground_truth():
    _, result = _derive([
        _changed("lib/presentation/bloc/task_bloc.dart"),
        _changed("test/presentation/bloc/task_bloc_test.dart"),
        _changed("CHANGELOG.md"),
        _changed("pubspec.lock"),
        _changed("lib/models/task.g.dart"),
    ])

    assert result["affected_files"] == [
        "lib/presentation/bloc/task_bloc.dart"
    ]


def test_the_full_changed_list_is_kept_for_audit():
    _, result = _derive([
        _changed("lib/a.dart"),
        _changed("CHANGELOG.md"),
    ])

    assert result["changed_files"] == ["CHANGELOG.md", "lib/a.dart"]
    assert result["excluded"] == [
        {"path": "CHANGELOG.md", "reason": "not_product_source"}
    ]


def test_the_diff_is_taken_against_the_first_parent():
    github, result = _derive([_changed("lib/a.dart")])

    assert github.compared == (PARENT, FIX)
    assert result["parent_commit"] == PARENT
    assert result["fix_commit"] == FIX


def test_a_renamed_file_is_reported_at_its_pre_fix_path():
    """
    Ground truth is matched against the PRE-fix tree, where the file
    still has its old name.
    """

    _, result = _derive([
        _changed(
            "lib/domain/usecases/get_filtered_tasks.dart",
            status="renamed",
            previous_filename="lib/domain/usecases/get_tasks.dart",
        ),
    ])

    assert result["affected_files"] == [
        "lib/domain/usecases/get_tasks.dart"
    ]


def test_a_file_created_by_the_fix_is_not_ground_truth():
    """
    It does not exist in the pre-fix snapshot, so no retriever could
    rank it. Counting it would make the case unwinnable, not hard.
    """

    _, result = _derive([
        _changed("lib/new_service.dart", status="added"),
        _changed("lib/presentation/bloc/task_bloc.dart"),
    ])

    assert result["affected_files"] == [
        "lib/presentation/bloc/task_bloc.dart"
    ]
    assert {"path": "lib/new_service.dart", "reason": "added_by_fix"} \
        in result["excluded"]


def test_a_deleted_file_is_still_ground_truth():
    """It exists in the pre-fix tree, so it is findable."""

    _, result = _derive([
        _changed("lib/legacy/old_bloc.dart", status="removed"),
    ])

    assert result["affected_files"] == ["lib/legacy/old_bloc.dart"]


def test_a_fix_touching_nothing_product_yields_no_ground_truth():
    _, result = _derive([_changed("README.md")])

    assert result["affected_files"] == []
    assert result["changed_files"] == ["README.md"]


def test_an_initial_commit_is_rejected():
    github = FakeGithub([], parents=[])

    with pytest.raises(GroundTruthError, match="no parent"):
        derive_ground_truth(github, "o", "r", FIX)


def test_an_unknown_commit_is_rejected():
    github = FakeGithub([])

    with pytest.raises(GroundTruthError, match="Could not resolve"):
        derive_ground_truth(github, "o", "r", "deadbeef")


def test_pre_fix_path_falls_back_to_the_current_name():
    assert pre_fix_path({"filename": "lib/a.dart"}) == "lib/a.dart"
    assert pre_fix_path(
        {"filename": "lib/b.dart", "status": "modified"}
    ) == "lib/b.dart"


# ============================================================
# THE THREE KNOWN COMMITS
# ============================================================

DEMO = ("SanjayKParida", "patchpilot-diagnosis-demo")

KNOWN_FIXES = [
    (
        1,
        "afd804edc491fb08e2bb2eed9df4bbfc6985edca",
        "lib/presentation/bloc/task_bloc.dart",
    ),
    (
        2,
        "f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c",
        "lib/data/datasources/task_local_data_source.dart",
    ),
    (
        3,
        "0bf7cc5104c2c7d0546795a9885c74a48bbcc337",
        "lib/domain/usecases/get_filtered_tasks.dart",
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize(
    "issue_number,fix_commit,expected",
    KNOWN_FIXES,
    ids=[f"issue-{n}" for n, _, _ in KNOWN_FIXES],
)
def test_known_fix_commits_yield_the_expected_file(
    issue_number,
    fix_commit,
    expected,
):
    import os

    from app.services.github_service import GithubService

    github = GithubService(os.getenv("GITHUB_TOKEN"))

    result = derive_ground_truth(github, *DEMO, fix_commit)

    assert result["affected_files"] == [expected]
    assert result["fix_commit"] == fix_commit
    assert result["parent_commit"] != fix_commit
