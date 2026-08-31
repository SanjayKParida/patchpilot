"""
Freeze a GitHub repository + issue into an offline fixture.

Calibration needs the pipeline to run dozens of times. Hitting the
GitHub API on every run is slow, rate-limited, and non-deterministic:
the repository can change underneath a comparison, which is exactly
what makes a before/after measurement meaningless.

This is the only module in `evalutation` that touches the network.
Run it deliberately, commit the result, and everything else runs
offline against a fixed input.

Snapshotting an old commit
--------------------------

`--parent-of` exists for real-world benchmarking. To test whether
PatchPilot finds a bug that was genuinely fixed, the repository has to
be frozen as it was BEFORE the fix -- the fix commit's first parent --
otherwise the defect is not there to find.

Pairing the right issue with the right code
-------------------------------------------

A benchmark fixture is only meaningful if the issue text and the
repository state describe the SAME bug. Issues are therefore selected
by number, never by position: GitHub returns issues newest-first, so
list index 0 silently changes meaning every time an issue is filed.

`--issue-number` is REQUIRED whenever a commit is pinned, because that
is exactly when a mismatch produces a fixture that looks valid and
measures the wrong thing.

Examples
--------

    # default branch HEAD, first issue listed
    PYTHONPATH=backend python -m evalutation.snapshot \\
        --owner SanjayKParida --repo car-rental-app

    # a specific issue at HEAD
    PYTHONPATH=backend python -m evalutation.snapshot \\
        --owner O --repo R --issue-number 1

    # BENCHMARK: issue #1 against the code as it was before its fix
    PYTHONPATH=backend python -m evalutation.snapshot \\
        --owner O --repo R --issue-number 1 \\
        --parent-of <fix-sha> \\
        --out evalutation/fixtures/issue1_pre_fix.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService


FIXTURE_DIR = Path(__file__).parent / "fixtures"

BACKEND_ENV = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / ".env"
)


class SnapshotError(RuntimeError):
    """A snapshot could not be taken as requested."""


# =============================================================
# COMMIT RESOLUTION
# =============================================================

def resolve_ref(github, owner, repo, commit=None, parent_of=None):
    """
    Decide which commit to snapshot.

        neither      -> None, meaning the default branch
        commit       -> that commit, verified to exist
        parent_of    -> that commit's FIRST parent

    Returns the resolved ref, or None for the default branch.

    The ref is resolved to a real SHA here rather than passed through
    as the user typed it, so the fixture records what was actually
    read instead of an abbreviation or a branch name that will move.
    """

    if commit and parent_of:
        raise SnapshotError(
            "Use either --commit or --parent-of, not both"
        )

    if not commit and not parent_of:
        return None

    target = commit or parent_of

    data = _get_commit(github, owner, repo, target)

    if not parent_of:
        return data["sha"]

    parents = data.get("parents") or []

    if not parents:
        raise SnapshotError(
            f"{target} has no parent commit; it is likely the "
            f"initial commit of {owner}/{repo}"
        )

    # First parent: on a merge commit this is the branch that was
    # merged INTO, which is the state the fix was applied to.
    return parents[0]["sha"]


def _get_commit(github, owner, repo, ref):
    try:
        data = github.get_commit(owner, repo, ref)
    except Exception as e:
        raise SnapshotError(
            f"Could not resolve {ref} in {owner}/{repo}: {e}"
        ) from e

    if not isinstance(data, dict) or "sha" not in data:
        raise SnapshotError(
            f"{ref} is not a commit in {owner}/{repo}"
        )

    return data


# =============================================================
# ISSUE SELECTION
# =============================================================

def _get_issue(github, owner, repo, issue_number):
    """
    Fetch one issue by NUMBER.

    Never by list position. GitHub returns issues newest-first, so an
    index means something different the moment another issue is
    filed — which is how a fixture ended up holding issue #3's text
    beside issue #1's pre-fix code.
    """

    if issue_number is None:
        issues = github.get_issues(owner, repo)

        if not issues:
            raise SnapshotError(
                f"{owner}/{repo} has no issues to snapshot"
            )

        return issues[0]

    try:
        issue = github.get_issue(owner, repo, issue_number)
    except Exception as e:
        raise SnapshotError(
            f"Could not fetch issue #{issue_number} from "
            f"{owner}/{repo}: {e}"
        ) from e

    if not isinstance(issue, dict) or "number" not in issue:
        raise SnapshotError(
            f"Issue #{issue_number} not found in {owner}/{repo}"
        )

    # GitHub serves pull requests from the issues endpoint. A PR is
    # not a bug report and must not become a benchmark case.
    if "pull_request" in issue:
        raise SnapshotError(
            f"#{issue_number} in {owner}/{repo} is a pull request, "
            f"not an issue"
        )

    if issue["number"] != issue_number:
        raise SnapshotError(
            f"asked for issue #{issue_number} but GitHub returned "
            f"#{issue['number']}"
        )

    return issue


# =============================================================
# CAPTURE
# =============================================================

def capture(
    github,
    owner,
    repo,
    issue_number=None,
    commit=None,
    parent_of=None,
):
    if issue_number is None and (commit or parent_of):
        raise SnapshotError(
            "--issue-number is required when pinning a commit. "
            "Pairing a specific repository state with whichever "
            "issue happens to be listed first produces a fixture "
            "that looks valid and measures the wrong bug."
        )

    ref = resolve_ref(
        github,
        owner,
        repo,
        commit=commit,
        parent_of=parent_of,
    )

    # The SAME ref is used for the file tree and for the recorded
    # SHA. Reading files from one commit while labelling the fixture
    # with another would make every result untraceable.
    # Tracked UTF-8 blobs at this ref — not a language include-list.
    # Production analysis still uses get_repository_source_files.
    files = github.get_repository_tracked_files(owner, repo, ref=ref)

    if ref is None:
        repository = github.get_repository(owner, repo)
        ref = repository["default_branch"]

    snapshot_commit = _get_commit(github, owner, repo, ref)["sha"]

    issue = _get_issue(github, owner, repo, issue_number)

    return {
        "owner": owner,
        "repo": repo,
        "commit": snapshot_commit,
        "issue": {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "body": issue.get("body") or "",
        },
        "files": [
            {
                "path": file["path"],
                "sha": file["sha"],
                "content": file["content"],
            }
            for file in sorted(
                files,
                key=lambda item: item["path"],
            )
        ],
    }


# =============================================================
# ENTRY POINT
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--issue-number",
        type=int,
        help=(
            "GitHub issue NUMBER (as in #1), not a list position. "
            "Required when --commit or --parent-of is used. Defaults "
            "to the first issue listed, which is only safe for "
            "casual HEAD snapshots."
        ),
    )

    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--commit",
        help="snapshot this commit instead of default-branch HEAD",
    )
    target.add_argument(
        "--parent-of",
        metavar="COMMIT",
        help=(
            "snapshot the FIRST PARENT of this commit -- the state "
            "before it landed. Use with a fix commit to capture the "
            "repository while the bug was still present."
        ),
    )

    parser.add_argument(
        "--out",
        help="fixture path (default: fixtures/<repo>.json)",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise SnapshotError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    snapshot = capture(
        GithubService(token),
        args.owner,
        args.repo,
        issue_number=args.issue_number,
        commit=args.commit,
        parent_of=args.parent_of,
    )

    out = Path(
        args.out
        or FIXTURE_DIR / f"{args.repo.replace('-', '_')}.json"
    )

    out.parent.mkdir(parents=True, exist_ok=True)

    out.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True)
    )

    print(f"wrote {out}")
    print(f"  commit : {snapshot['commit']}")
    print(f"  files  : {len(snapshot['files'])}")
    print(
        f"  issue  : #{snapshot['issue']['number']} "
        f"{snapshot['issue']['title']}"
    )


if __name__ == "__main__":
    # A refused snapshot is a normal outcome — a bad SHA, a missing
    # issue, a mismatched pairing. Report it as a message and a
    # non-zero exit, not a stack trace.
    try:
        main()
    except SnapshotError as error:
        print(f"snapshot failed: {error}", file=sys.stderr)
        raise SystemExit(1)
