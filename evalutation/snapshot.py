"""
Freeze a GitHub repository + issue into an offline fixture.

Calibration needs the pipeline to run dozens of times. Hitting the
GitHub API on every run is slow, rate-limited, and non-deterministic:
the repository can change underneath a comparison, which is exactly
what makes a before/after measurement meaningless.

This is the only module in `evalutation` that touches the network.
Run it deliberately, commit the result, and everything else runs
offline against a fixed input.

Usage
-----

    PYTHONPATH=backend python -m evalutation.snapshot \\
        --owner SanjayKParida \\
        --repo car-rental-app \\
        --issue-index 0
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService


FIXTURE_DIR = Path(__file__).parent / "fixtures"

BACKEND_ENV = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / ".env"
)


def capture(owner, repo, issue_index, token):
    github = GithubService(token)

    files = github.get_repository_source_files(
        owner,
        repo,
    )

    issues = github.get_issues(owner, repo)

    if not issues:
        raise RuntimeError(
            f"{owner}/{repo} has no issues to snapshot"
        )

    if issue_index >= len(issues):
        raise RuntimeError(
            f"issue index {issue_index} out of range "
            f"({len(issues)} issues available)"
        )

    issue = issues[issue_index]

    # Record the commit the snapshot was taken at, so a stale
    # fixture can be recognised rather than silently trusted.
    repository = github.get_repository(owner, repo)

    commit = github.get_commit(
        owner,
        repo,
        repository["default_branch"],
    )

    return {
        "owner": owner,
        "repo": repo,
        "commit": commit["sha"],
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


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue-index", type=int, default=0)
    parser.add_argument(
        "--out",
        help="fixture path (default: fixtures/<repo>.json)",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise RuntimeError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    snapshot = capture(
        args.owner,
        args.repo,
        args.issue_index,
        token,
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
    print(f"  commit : {snapshot['commit'][:12]}")
    print(f"  files  : {len(snapshot['files'])}")
    print(f"  issue  : {snapshot['issue']['title']}")


if __name__ == "__main__":
    main()
