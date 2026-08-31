"""
Generate a commit-grounded benchmark case in one command.

Adding a case by hand is three steps -- resolve the fix commit, freeze
the pre-fix snapshot, hand-write the case JSON -- and each is a place
to pair the wrong issue with the wrong code. That has already happened
once. This does all three, applies every validation rule the pieces
already enforce, and refuses rather than emitting a case that cannot
be scored.

    repo + issue + fix commit
        -> pre-fix snapshot   (evalutation/fixtures/<name>_pre_fix.json)
        -> case JSON          (evalutation/cases/commit_grounded/<name>.json)

It composes existing modules and adds no pipeline logic:
`ground_truth.derive_ground_truth` for the answer, `snapshot.capture`
for the code, `IssueSignalExtractionService` for the signals.

Examples
--------

    PYTHONPATH=backend python3 -m evalutation.generate_case \\
        --owner flutter --repo samples \\
        --issue-number 12345 \\
        --fix-commit abcdef1234567890abcdef1234567890abcdef12

    # choose the file name instead of deriving it from the title
    PYTHONPATH=backend python3 -m evalutation.generate_case \\
        --owner O --repo R --issue-number 1 --fix-commit <sha> \\
        --name task_refresh --force
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.issue_signal_extraction_service import (
    IssueSignalExtractionService,
)
from app.services.llm_service import LLMService

from evalutation.ground_truth import derive_ground_truth
from evalutation.snapshot import capture

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = REPO_ROOT / "backend" / ".env"

FIXTURE_DIR = REPO_ROOT / "evalutation" / "fixtures"

CASE_DIR = REPO_ROOT / "evalutation" / "cases" / "commit_grounded"

SIGNALS_NOTE = (
    "Captured once at case generation and pinned. Signal extraction "
    "is a model call and varies between runs, which makes ranking "
    "measurements irreproducible. Review these terms; edit them if "
    "they are wrong. Do not remove the pinning."
)

MAX_NAME_WORDS = 5


class GenerationError(RuntimeError):
    """A case could not be generated."""


# =============================================================
# NAMING
# =============================================================

def slugify(title, issue_number):
    """
    A short, stable file name derived from the issue title.

    Kept to a few words so a directory listing stays readable; the
    issue number keeps it unique when two titles collapse to the same
    words.
    """

    words = re.findall(r"[a-z0-9]+", (title or "").lower())

    skip = {
        "the", "a", "an", "is", "are", "on", "in", "to", "of", "and",
        "after", "when", "with", "for", "app", "it", "not", "but",
    }

    kept = [word for word in words if word not in skip]

    if not kept:
        return f"issue_{issue_number}"

    return "_".join(kept[:MAX_NAME_WORDS])


# =============================================================
# GENERATION
# =============================================================

def generate(
    github,
    llm,
    owner,
    repo,
    issue_number,
    fix_commit,
    name=None,
    force=False,
    fixture_dir=None,
    case_dir=None,
):
    """
    Build a snapshot and case for one (repo, issue, fix commit).

    Returns the paths written and the derived ground truth.
    """

    fixture_dir = Path(fixture_dir or FIXTURE_DIR)
    case_dir = Path(case_dir or CASE_DIR)

    # ---- the answer, first -------------------------------------
    #
    # Derived before anything is downloaded or written. A commit that
    # changes no product file cannot be scored, and finding that out
    # after freezing a snapshot wastes the work.
    ground_truth = derive_ground_truth(
        github,
        owner,
        repo,
        fix_commit,
    )

    if not ground_truth["affected_files"]:
        raise GenerationError(
            f"{fix_commit[:8]} changes no product source file, so "
            f"there is nothing for retrieval to find. Changed: "
            f"{ground_truth['changed_files']}"
        )

    # ---- the code, as it was before the fix --------------------
    snapshot = capture(
        github,
        owner,
        repo,
        issue_number=issue_number,
        parent_of=fix_commit,
    )

    # The pairing check. A snapshot taken at anything other than the
    # fix's parent measures the wrong code, and the resulting case
    # looks perfectly valid.
    if snapshot["commit"] != ground_truth["parent_commit"]:
        raise GenerationError(
            f"snapshot is at {snapshot['commit'][:8]} but the fix's "
            f"parent is {ground_truth['parent_commit'][:8]}"
        )

    issue = snapshot["issue"]

    name = name or slugify(issue.get("title"), issue_number)

    fixture_path = fixture_dir / f"{name}_pre_fix.json"
    case_path = case_dir / f"{name}.json"

    for path in (fixture_path, case_path):
        if path.exists() and not force:
            raise GenerationError(
                f"{path} already exists; pass --force to overwrite"
            )

    # ---- signals, captured once and pinned ---------------------
    try:
        signals = IssueSignalExtractionService(
            llm_service=llm,
        ).extract_signals(
            issue.get("title") or "",
            issue.get("body") or "",
        )
    except Exception as e:
        raise GenerationError(
            f"Signal extraction failed, so the case would not be "
            f"reproducible: {e}"
        ) from e

    if not signals:
        raise GenerationError(
            "Signal extraction returned nothing, so the case would "
            "not be reproducible"
        )

    case = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue["number"],
        "fix_commit": ground_truth["fix_commit"],
        "snapshot": str(
            fixture_path.relative_to(REPO_ROOT)
            if fixture_path.is_relative_to(REPO_ROOT)
            else fixture_path
        ),
        "title": issue.get("title") or "",
        "body": issue.get("body") or "",
        "signals_note": SIGNALS_NOTE,
        "signals": signals,
    }

    fixture_dir.mkdir(parents=True, exist_ok=True)
    case_dir.mkdir(parents=True, exist_ok=True)

    fixture_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True)
    )
    case_path.write_text(json.dumps(case, indent=2) + "\n")

    return {
        "name": name,
        "fixture": fixture_path,
        "case": case_path,
        "ground_truth": ground_truth,
        "snapshot": snapshot,
        "signals": signals,
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
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--fix-commit", required=True)
    parser.add_argument(
        "--name",
        help="file name stem (default: derived from the issue title)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing fixture and case",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    if not os.getenv("GITHUB_TOKEN"):
        raise GenerationError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    result = generate(
        GithubService(os.getenv("GITHUB_TOKEN")),
        LLMService(),
        args.owner,
        args.repo,
        args.issue_number,
        args.fix_commit,
        name=args.name,
        force=args.force,
    )

    ground_truth = result["ground_truth"]

    print(f"generated {result['name']}")
    print(f"  fixture : {result['fixture']}")
    print(f"  case    : {result['case']}")
    print(
        f"  issue   : #{result['snapshot']['issue']['number']} "
        f"{result['snapshot']['issue']['title']}"
    )
    print(
        f"  commits : fix {ground_truth['fix_commit'][:8]} "
        f"-> parent {ground_truth['parent_commit'][:8]}"
    )
    print(f"  files   : {len(result['snapshot']['files'])}")
    print(f"  expected: {ground_truth['affected_files']}")

    if ground_truth["excluded"]:
        print(
            "  excluded: "
            + ", ".join(
                f"{item['path']} ({item['reason']})"
                for item in ground_truth["excluded"]
            )
        )

    print(
        "  signals : "
        + ", ".join(
            f"{signal['term']} ({signal['type']})"
            for signal in result["signals"]
        )
    )
    print("\nReview the pinned signals before trusting the case.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"generation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
