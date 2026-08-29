"""
Tests for candidate discovery.

Discovery proposes; it does not create. Its job is to be conservative:
a false candidate wastes a human's review, and worse, a plausible-but-
wrong (issue, commit) pair that slips through becomes a benchmark case
that measures nothing.

Deterministic and offline.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evalutation.discover_cases import (  # noqa: E402
    closes_issue,
    commit_ids_from_timeline,
    discover,
    inspect_issue,
)

FIX = "a" * 40
OTHER = "b" * 40
PARENT = "c" * 40

DART = "lib/presentation/bloc/task_bloc.dart"


def _issue(number=1, state="closed", **extra):
    return {
        "number": number,
        "state": state,
        "title": f"Issue {number}",
        **extra,
    }


class FakeGithub:
    def __init__(
        self,
        issues=None,
        timeline=None,
        commits=None,
        changed=None,
    ):
        self.issues = issues if issues is not None else [_issue()]
        self.timeline = (
            timeline
            if timeline is not None
            else [{"event": "closed", "commit_id": FIX}]
        )
        self.commits = commits or {
            FIX: {
                "sha": FIX,
                "parents": [{"sha": PARENT}],
                "commit": {"message": "fix: stop the spinner\n\nFixes #1"},
            }
        }
        self.changed = (
            changed
            if changed is not None
            else [{"filename": DART, "status": "modified"}]
        )
        self.pages = 0

    def get_issues(self, owner, repo, state="open", per_page=30,
                   page=1, since=None):
        self.pages += 1
        return self.issues if page == 1 else []

    def get_issue_timeline(self, owner, repo, number, per_page=100):
        return self.timeline

    def get_commit(self, owner, repo, ref):
        if ref not in self.commits:
            raise Exception(f"404 for {ref}")
        return self.commits[ref]

    def compare_commits(self, owner, repo, base, head):
        return {"files": self.changed}


def _inspect(github=None, issue=None, **kwargs):
    return inspect_issue(
        github or FakeGithub(),
        "o",
        "r",
        issue or _issue(),
        **kwargs,
    )


# ============================================================
# CLOSING KEYWORDS
# ============================================================

@pytest.mark.parametrize(
    "message",
    [
        "Fixes #1", "fixes #1", "Fixed #1", "fix #1",
        "Closes #1", "closed #1", "close #1",
        "Resolves #1", "resolved #1", "resolve #1",
        "Resolves: #1",
        "fix: spinner\n\nFixes #1",
    ],
)
def test_closing_keywords_are_recognised(message):
    assert closes_issue(message, 1) is True


@pytest.mark.parametrize(
    "message",
    [
        "See #1",              # a mention, not a fix
        "Related to #1",
        "Fixes #2",            # a different issue
        "",
        "refactor with no reference",
    ],
)
def test_non_closing_references_are_rejected(message):
    assert closes_issue(message, 1) is False


# ============================================================
# TIMELINE EVIDENCE
# ============================================================

def test_a_closing_event_is_the_strongest_evidence():
    found = commit_ids_from_timeline(
        [{"event": "closed", "commit_id": FIX}], 1
    )

    assert found[0][0] == FIX
    assert "closed by commit" in found[0][1]


def test_closing_events_are_preferred_over_references():
    """A referenced commit is weaker, so it is tried second."""

    found = commit_ids_from_timeline(
        [
            {"event": "referenced", "commit_id": OTHER},
            {"event": "closed", "commit_id": FIX},
        ],
        1,
    )

    assert [commit for commit, _ in found] == [FIX, OTHER]


def test_events_without_a_commit_are_ignored():
    """Closing an issue by hand links no commit."""

    assert commit_ids_from_timeline(
        [
            {"event": "closed", "commit_id": None},
            {"event": "labeled"},
            {"event": "commented"},
        ],
        1,
    ) == []


def test_duplicate_commits_are_reported_once():
    found = commit_ids_from_timeline(
        [
            {"event": "closed", "commit_id": FIX},
            {"event": "referenced", "commit_id": FIX},
        ],
        1,
    )

    assert len(found) == 1


# ============================================================
# WHAT BECOMES A CANDIDATE
# ============================================================

def test_a_closed_issue_with_a_fix_commit_is_a_candidate():
    candidate = _inspect()

    assert candidate["issue_number"] == 1
    assert candidate["fix_commit"] == FIX
    assert candidate["parent_commit"] == PARENT
    assert candidate["affected_files"] == [DART]
    assert any("closed by commit" in e for e in candidate["evidence"])


def test_the_commit_message_is_recorded_as_extra_evidence():
    candidate = _inspect()

    assert any(
        e.startswith("message:") for e in candidate["evidence"]
    )


# ============================================================
# WHAT IS REJECTED
# ============================================================

def test_an_open_issue_is_not_a_candidate():
    assert _inspect(issue=_issue(state="open")) is None


def test_a_pull_request_is_not_a_candidate():
    assert _inspect(issue=_issue(pull_request={})) is None


def test_an_issue_closed_without_a_commit_is_not_a_candidate():
    github = FakeGithub(timeline=[{"event": "closed"}])

    assert _inspect(github) is None


def test_a_commit_with_no_parent_is_not_a_candidate():
    """No parent means no pre-fix state to snapshot."""

    github = FakeGithub(
        commits={FIX: {"sha": FIX, "parents": [], "commit": {"message": ""}}}
    )

    assert _inspect(github) is None


def test_a_fix_touching_no_product_dart_file_is_not_a_candidate():
    github = FakeGithub(
        changed=[{"filename": "README.md", "status": "modified"}]
    )

    assert _inspect(github) is None


def test_a_docs_only_fix_is_rejected_by_the_same_classifier():
    github = FakeGithub(
        changed=[
            {"filename": "CHANGELOG.md", "status": "modified"},
            {"filename": "test/task_bloc_test.dart", "status": "modified"},
        ]
    )

    assert _inspect(github) is None


def test_an_unreachable_commit_is_skipped():
    github = FakeGithub(
        timeline=[{"event": "closed", "commit_id": "deadbeef"}]
    )

    assert _inspect(github) is None


def test_an_unreadable_timeline_skips_the_issue():
    """Some repositories hide it. Skip, do not abort the scan."""

    github = FakeGithub()
    github.get_issue_timeline = lambda *a, **k: (_ for _ in ()).throw(
        Exception("403")
    )

    assert _inspect(github) is None


def test_no_verify_skips_the_product_file_check():
    github = FakeGithub(
        changed=[{"filename": "README.md", "status": "modified"}]
    )

    candidate = _inspect(github, verify=False)

    assert candidate["fix_commit"] == FIX
    assert "affected_files" not in candidate


# ============================================================
# SCANNING
# ============================================================

def test_discovery_collects_candidates_across_issues():
    github = FakeGithub(issues=[_issue(1), _issue(1), _issue(1)])

    result = discover(github, "o", "r", limit=10)

    assert result["examined"] == 3
    assert len(result["candidates"]) == 3
    assert result["repository"] == "o/r"


def test_limit_caps_candidates_not_issues_examined():
    """
    Most closed issues carry no fix link, so capping issues examined
    would usually return nothing.
    """

    github = FakeGithub(issues=[_issue(1) for _ in range(10)])

    result = discover(github, "o", "r", limit=2)

    assert len(result["candidates"]) == 2
    assert result["examined"] == 2


def test_scan_bounds_the_work_on_a_repository_with_no_candidates():
    """Without a scan cap, a big repository would spin against the API."""

    github = FakeGithub(
        issues=[_issue(n, state="open") for n in range(50)]
    )

    result = discover(github, "o", "r", limit=5, scan=10)

    assert result["candidates"] == []
    assert result["examined"] == 10


def test_discovery_stops_when_issues_run_out():
    github = FakeGithub(issues=[_issue(1)])

    result = discover(github, "o", "r", limit=50)

    assert len(result["candidates"]) == 1
    assert result["examined"] == 1


# ============================================================
# SPRAWLING FIXES
# ============================================================

def test_a_sprawling_fix_is_not_a_candidate():
    """
    flutter/samples #2818 closed with a 250-file maintenance commit.
    Scoring retrieval against that measures nothing, so a fix has to
    be localised to be a usable case.
    """

    github = FakeGithub(
        changed=[
            {"filename": f"lib/f{n}.dart", "status": "modified"}
            for n in range(10)
        ]
    )

    assert _inspect(github, max_files=5) is None


def test_a_localised_fix_is_kept():
    github = FakeGithub(
        changed=[
            {"filename": f"lib/f{n}.dart", "status": "modified"}
            for n in range(3)
        ]
    )

    candidate = _inspect(github, max_files=5)

    assert len(candidate["affected_files"]) == 3


def test_max_files_zero_disables_the_limit():
    github = FakeGithub(
        changed=[
            {"filename": f"lib/f{n}.dart", "status": "modified"}
            for n in range(50)
        ]
    )

    assert _inspect(github, max_files=0) is not None
