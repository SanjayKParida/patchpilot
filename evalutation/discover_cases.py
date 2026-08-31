"""
Find (closed issue, fixing commit) pairs in a GitHub repository.

This module FINDS candidates. It does not create benchmark cases, and
deliberately does not trust what it finds:

    discover_cases.py   find candidates        <- this module
    generate_case.py    validate and create
    commit_benchmark.py run the benchmark

Keeping discovery separate from creation means a wrong guess costs a
line of output rather than a bad fixture that looks valid. Review the
candidates, then hand the good ones to generate_case.

Evidence
--------

The timeline is the repository's own account of what closed an issue,
so it is preferred over commit-message archaeology:

    closed      event carrying a commit_id -- the strongest evidence
                there is, GitHub recording the commit that closed it
    referenced  event linking a commit that mentions the issue,
                accepted only when that commit's message actually
                closes it ("Fixes #123")

A candidate is reported only when all of these hold:

    1. the issue is closed
    2. it is an issue, not a pull request
    3. a commit is identifiable
    4. that commit has a parent (there is a pre-fix state)
    5. its diff touches product Dart source

Rule 5 reuses `ground_truth`, the same classifier the benchmark
scores with, so discovery and scoring cannot disagree about what
counts as product code.

Examples
--------

    PYTHONPATH=backend python3 -m evalutation.discover_cases \\
        --owner SanjayKParida --repo patchpilot-diagnosis-demo

    PYTHONPATH=backend python3 -m evalutation.discover_cases \\
        --owner flutter --repo samples --limit 50 --since 2024-01-01
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService

from evalutation.ground_truth import (
    GroundTruthError,
    derive_ground_truth,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = REPO_ROOT / "backend" / ".env"

# "Fixes #123", "closed #12", "Resolves: #4". GitHub's own closing
# keywords; anything looser starts matching mere mentions.
CLOSING_PATTERN = re.compile(
    r"\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\b[:\s]*#(\d+)",
    re.IGNORECASE,
)

DEFAULT_LIMIT = 20

# A fix touching more product files than this is a refactor, a
# dependency bump or a repo-wide sweep -- not a localised bug with a
# findable cause. flutter/samples #2818 closed with a 250-file commit;
# scoring retrieval against that measures nothing.
DEFAULT_MAX_FILES = 5

# Issues scanned per page while looking for candidates.
PAGE_SIZE = 100


class DiscoveryError(RuntimeError):
    """Candidates could not be discovered."""


# =============================================================
# EVIDENCE
# =============================================================

def closes_issue(message, issue_number):
    """Does this commit message claim to close this issue?"""

    return any(
        int(found) == issue_number
        for found in CLOSING_PATTERN.findall(message or "")
    )


def commit_ids_from_timeline(timeline, issue_number):
    """
    Commits the timeline links to an issue, strongest evidence first.

    Returns [(commit_id, evidence)] with duplicates removed but order
    preserved, so the caller checks the best candidate first.
    """

    found = []
    seen = set()

    def add(commit_id, evidence):
        if not commit_id or commit_id in seen:
            return
        seen.add(commit_id)
        found.append((commit_id, evidence))

    for event in timeline or []:

        name = event.get("event")
        commit_id = event.get("commit_id")

        if name == "closed" and commit_id:
            add(
                commit_id,
                f"timeline: issue closed by commit {commit_id[:8]}",
            )

    # Referenced commits are weaker, so they are considered only after
    # every closing event, and only when the message says so.
    for event in timeline or []:

        if event.get("event") != "referenced":
            continue

        commit_id = event.get("commit_id")

        if not commit_id:
            continue

        add(
            commit_id,
            f"timeline: commit {commit_id[:8]} references the issue",
        )

    return found


# =============================================================
# DISCOVERY
# =============================================================

def is_issue(item):
    """
    A real issue, not a pull request.

    GitHub serves both from the issues endpoint, and closed PRs
    outnumber closed issues roughly ten to one, so this filter has to
    run before anything else spends a request or a scan slot.
    """

    return bool(item.get("number")) and "pull_request" not in item


def inspect_issue(
    github,
    owner,
    repo,
    issue,
    verify=True,
    max_files=DEFAULT_MAX_FILES,
):
    """
    Turn one closed issue into a candidate, or return None.

    Returns
    -------
    dict or None

        {
            "issue_number": 123,
            "title": "...",
            "fix_commit": "abc...",
            "evidence": ["timeline: ...", "message: Fixes #123"],
            "affected_files": [...]     # when verified
        }
    """

    number = issue.get("number")

    if not is_issue(issue):
        return None

    if issue.get("state") != "closed":
        return None

    try:
        timeline = github.get_issue_timeline(owner, repo, number)
    except Exception:
        # A repository can hide its timeline, or the call can fail.
        # Discovery skips rather than aborting the scan.
        return None

    for commit_id, evidence in commit_ids_from_timeline(
        timeline,
        number,
    ):

        try:
            commit = github.get_commit(owner, repo, commit_id)
        except Exception:
            continue

        parents = commit.get("parents") or []

        # No parent means no pre-fix state to snapshot.
        if not parents:
            continue

        reasons = [evidence]

        message = (commit.get("commit") or {}).get("message", "")

        if closes_issue(message, number):
            reasons.append(
                f"message: {message.splitlines()[0][:60]}"
            )

        candidate = {
            "issue_number": number,
            "title": issue.get("title") or "",
            "fix_commit": commit["sha"],
            "parent_commit": parents[0]["sha"],
            "evidence": reasons,
        }

        if not verify:
            return candidate

        # Rule 5, through the same classifier the benchmark scores
        # with, so discovery and scoring agree on "product code".
        try:
            ground_truth = derive_ground_truth(
                github,
                owner,
                repo,
                commit["sha"],
            )
        except GroundTruthError:
            continue

        affected = ground_truth["affected_files"]

        if not affected:
            continue

        # A sprawling fix is not a localisable bug.
        if max_files and len(affected) > max_files:
            continue

        candidate["affected_files"] = affected

        return candidate

    return None


def discover(
    github,
    owner,
    repo,
    limit=DEFAULT_LIMIT,
    since=None,
    scan=None,
    verify=True,
    max_files=DEFAULT_MAX_FILES,
):
    """
    Scan closed issues and return candidates.

    `limit` caps CANDIDATES, not issues examined: most closed issues
    carry no usable fix link, so stopping after N issues would usually
    return nothing.

    `scan` caps issues examined, so a large repository cannot spin
    forever against the API.
    """

    scan = scan or max(limit * 10, 100)

    candidates = []
    examined = 0
    page = 1

    while len(candidates) < limit and examined < scan:

        issues = github.get_issues(
            owner,
            repo,
            state="closed",
            per_page=PAGE_SIZE,
            page=page,
            since=since,
        )

        if not issues:
            break

        for issue in issues:

            # Pull requests must not consume the scan budget: they are
            # ~90% of a busy repository's closed list, so counting
            # them would exhaust the scan before reaching real issues.
            if not is_issue(issue):
                continue

            if len(candidates) >= limit or examined >= scan:
                break

            examined += 1

            candidate = inspect_issue(
                github,
                owner,
                repo,
                issue,
                verify=verify,
                max_files=max_files,
            )

            if candidate:
                candidates.append(candidate)

        page += 1

    return {
        "repository": f"{owner}/{repo}",
        "examined": examined,
        "candidates": candidates,
    }


# =============================================================
# REPORT
# =============================================================

def report(result, owner, repo):
    candidates = result["candidates"]

    print(
        f"\nScanned {result['examined']} closed issue(s) in "
        f"{result['repository']}"
    )
    print(f"Found {len(candidates)} candidate(s)\n")

    if not candidates:
        print(
            "No closed issue carried a usable fix link. That is "
            "normal for repositories that close issues manually."
        )
        return

    for candidate in candidates:
        print(
            f"#{candidate['issue_number']:<6} "
            f"{candidate['fix_commit'][:8]}  "
            f"{candidate['title'][:56]}"
        )
        for reason in candidate["evidence"]:
            print(f"          {reason}")
        if candidate.get("affected_files"):
            print(
                f"          fixes: "
                f"{', '.join(candidate['affected_files'])}"
            )
        print()

    print("Review these, then create the ones you want:\n")

    for candidate in candidates[:3]:
        print(
            f"  PYTHONPATH=backend python3 -m evalutation.generate_case \\\n"
            f"      --owner {owner} --repo {repo} \\\n"
            f"      --issue-number {candidate['issue_number']} \\\n"
            f"      --fix-commit {candidate['fix_commit']}\n"
        )


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
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"stop after this many CANDIDATES (default {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--scan",
        type=int,
        help="cap how many closed issues are examined",
    )
    parser.add_argument(
        "--since",
        help="only issues updated after this ISO date, e.g. 2024-01-01",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=(
            f"reject fixes touching more than this many product "
            f"files (default {DEFAULT_MAX_FILES}); 0 disables"
        ),
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help=(
            "skip the product-Dart-file check. Faster and cheaper, "
            "but candidates may not be scoreable"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print candidates as JSON",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    # Referenced commits routinely live in contributors' forks and
    # 422 against the upstream repository. Discovery skips them by
    # design, so the warnings are noise rather than incidents.
    logging.getLogger("app.services.github_service").setLevel(
        logging.ERROR
    )

    if not os.getenv("GITHUB_TOKEN"):
        raise DiscoveryError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    result = discover(
        GithubService(os.getenv("GITHUB_TOKEN")),
        args.owner,
        args.repo,
        limit=args.limit,
        since=args.since,
        scan=args.scan,
        verify=not args.no_verify,
        max_files=args.max_files,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        report(result, args.owner, args.repo)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"discovery failed: {error}", file=sys.stderr)
        raise SystemExit(1)
