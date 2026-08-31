"""
Tests for evalutation/snapshot.py commit selection.

The trap this guards against: fetching a commit's metadata and then
reading files from the default branch anyway. A fixture labelled with
an old SHA but containing today's code is worse than no fixture — it
looks like a valid benchmark and silently measures the wrong thing.
"""

import sys
from pathlib import Path

import pytest

# snapshot.py lives in evalutation/ at the repo root, outside the
# backend package the rest of the suite imports from.
REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evalutation.snapshot import (  # noqa: E402
    SnapshotError,
    capture,
    resolve_ref,
)


HEAD = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FIX = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
PARENT = "cccccccccccccccccccccccccccccccccccccccc"
ROOT_COMMIT = "dddddddddddddddddddddddddddddddddddddddd"


class FakeGithub:
    """
    Records which ref each call asked for, so a test can prove the
    files came from the commit that was requested.
    """

    def __init__(self):
        self.tracked_file_refs = []

        self.commits = {
            "main": {"sha": HEAD, "parents": [{"sha": PARENT}]},
            HEAD: {"sha": HEAD, "parents": [{"sha": PARENT}]},
            FIX: {"sha": FIX, "parents": [{"sha": PARENT}]},
            PARENT: {"sha": PARENT, "parents": [{"sha": HEAD}]},
            ROOT_COMMIT: {"sha": ROOT_COMMIT, "parents": []},
        }

    def get_repository(self, owner, repo):
        return {"default_branch": "main"}

    def get_commit(self, owner, repo, ref):
        if ref not in self.commits:
            raise Exception(f"404 for {ref}")
        return self.commits[ref]

    def get_repository_tracked_files(self, owner, repo, ref=None):
        self.tracked_file_refs.append(ref)
        return [
            {
                "path": "lib/main.dart",
                "sha": "blob",
                "content": f"// files as of {ref}\n",
            }
        ]

    # Newest first, exactly as GitHub serves them. Index 0 is the
    # HIGHEST-numbered issue, which is the trap this guards.
    ISSUES = {
        3: {"number": 3, "title": "Filter bug", "body": "c"},
        2: {"number": 2, "title": "Delete bug", "body": "b"},
        1: {"number": 1, "title": "Refresh bug", "body": "a"},
    }

    def get_issues(self, owner, repo):
        return [self.ISSUES[n] for n in (3, 2, 1)]

    def get_issue(self, owner, repo, number):
        if number == 99:
            return {"number": 99, "title": "A PR", "pull_request": {}}
        if number not in self.ISSUES:
            raise Exception(f"404 for issue {number}")
        return self.ISSUES[number]


@pytest.fixture
def github():
    return FakeGithub()


def _capture(github, **kwargs):
    return capture(github, "owner", "repo", **kwargs)


# ============================================================
# 1. DEFAULT: DEFAULT-BRANCH HEAD
# ============================================================

def test_default_snapshots_the_default_branch(github):
    snapshot = _capture(github, issue_number=1)

    assert snapshot["commit"] == HEAD
    # None means "the default branch" to GithubService.
    assert github.tracked_file_refs == [None]


def test_resolve_ref_returns_none_by_default(github):
    assert resolve_ref(github, "owner", "repo") is None


# ============================================================
# 2. EXPLICIT COMMIT
# ============================================================

def test_explicit_commit_is_snapshotted(github):
    snapshot = _capture(github, commit=FIX, issue_number=1)

    assert snapshot["commit"] == FIX


def test_files_are_read_from_the_requested_commit(github):
    """
    The whole point. Files must come from the requested commit, not
    from current HEAD.
    """

    snapshot = _capture(github, commit=FIX, issue_number=1)

    assert github.tracked_file_refs == [FIX]
    assert HEAD not in snapshot["files"][0]["content"]
    assert FIX in snapshot["files"][0]["content"]


# ============================================================
# 3. PARENT OF A COMMIT
# ============================================================

def test_parent_of_snapshots_the_first_parent(github):
    snapshot = _capture(github, parent_of=FIX, issue_number=1)

    assert snapshot["commit"] == PARENT
    assert github.tracked_file_refs == [PARENT]


def test_parent_of_records_the_parent_not_the_fix(github):
    """
    A pre-fix fixture labelled with the fix's SHA would be actively
    misleading.
    """

    snapshot = _capture(github, parent_of=FIX, issue_number=1)

    assert snapshot["commit"] != FIX


def test_parent_of_an_initial_commit_is_rejected(github):
    with pytest.raises(SnapshotError, match="no parent"):
        resolve_ref(
            github,
            "owner",
            "repo",
            parent_of=ROOT_COMMIT,
        )


# ============================================================
# 4. INVALID COMMIT
# ============================================================

@pytest.mark.parametrize("field", ["commit", "parent_of"])
def test_a_nonexistent_commit_is_rejected(github, field):
    with pytest.raises(SnapshotError, match="Could not resolve"):
        resolve_ref(github, "owner", "repo", **{field: "deadbeef"})


def test_nonexistent_commit_takes_no_snapshot(github):
    with pytest.raises(SnapshotError):
        _capture(github, commit="deadbeef", issue_number=1)

    # Nothing was downloaded on the way to failing.
    assert github.tracked_file_refs == []


def test_commit_and_parent_of_are_mutually_exclusive(github):
    with pytest.raises(SnapshotError, match="not both"):
        resolve_ref(
            github,
            "owner",
            "repo",
            commit=FIX,
            parent_of=FIX,
        )


# ============================================================
# FIXTURE SHAPE IS UNCHANGED
# ============================================================

def test_fixture_shape_is_preserved(github):
    snapshot = _capture(github, commit=FIX, issue_number=1)

    assert set(snapshot) == {
        "owner",
        "repo",
        "commit",
        "issue",
        "files",
    }
    assert snapshot["issue"]["number"] == 1
    assert snapshot["files"][0]["path"] == "lib/main.dart"


# ============================================================
# ISSUES ARE SELECTED BY NUMBER, NEVER BY POSITION
# ============================================================

def test_issue_is_selected_by_number_not_list_position(github):
    """
    The regression. GitHub lists issues newest-first, so position 0
    is issue #3. Asking for #1 must give #1.
    """

    assert github.get_issues("o", "r")[0]["number"] == 3

    snapshot = _capture(github, commit=FIX, issue_number=1)

    assert snapshot["issue"]["number"] == 1
    assert snapshot["issue"]["title"] == "Refresh bug"


@pytest.mark.parametrize("number", [1, 2, 3])
def test_every_issue_number_resolves_to_itself(github, number):
    snapshot = _capture(github, commit=FIX, issue_number=number)

    assert snapshot["issue"]["number"] == number


def test_pinning_a_commit_without_an_issue_number_is_refused(github):
    """
    This pairing is exactly what produced a fixture holding issue #3's
    text beside issue #1's pre-fix code.
    """

    with pytest.raises(SnapshotError, match="--issue-number"):
        _capture(github, commit=FIX)

    with pytest.raises(SnapshotError, match="--issue-number"):
        _capture(github, parent_of=FIX)

    # Nothing was downloaded before refusing.
    assert github.tracked_file_refs == []


def test_a_missing_issue_is_rejected(github):
    with pytest.raises(SnapshotError, match="Could not fetch issue"):
        _capture(github, commit=FIX, issue_number=404)


def test_a_pull_request_is_not_an_issue(github):
    with pytest.raises(SnapshotError, match="pull request"):
        _capture(github, commit=FIX, issue_number=99)


def test_head_snapshot_without_a_number_still_works(github):
    """
    Casual HEAD snapshots keep the old convenience; only benchmark
    fixtures are held to the stricter rule.
    """

    snapshot = _capture(github)

    assert snapshot["issue"]["number"] == 3
