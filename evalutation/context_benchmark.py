"""
Context recall benchmark over commit-grounded cases.

Measures whether the ContextBuilder shows a patch generator the files
and lines a fix actually touched — not whether the diagnosis prose was
eloquent. Ground truth comes from the fix commit; the pipeline runs
against the offline pre-fix snapshot exactly as production does.

    pre-fix snapshot  ->  analysis + diagnosis  ->  ContextPackage
    fix commit        ->  product files + changed lines
                                    ->  scored

This module orchestrates and scores. It does not rank, diagnose, slice,
or tune budgets.

Usage
-----

    PYTHONPATH=backend python -m evalutation.context_benchmark \\
        --case evalutation/cases/commit_grounded/task_refresh.json

    PYTHONPATH=backend python -m evalutation.context_benchmark \\
        --cases evalutation/cases/commit_grounded

    PYTHONPATH=backend python -m evalutation.context_benchmark \\
        --cases evalutation/cases/commit_grounded --json

Reproducibility
---------------

Cases pin their signals, so retrieval and ranking are deterministic.
Diagnosis is still a model call unless a harness injects a fake LLM.
ContextBuilder output is deterministic for the same diagnosis input.

Metrics (no pass/fail thresholds — baseline measurement only):

    context_file_recall = |fix files ∩ context files| / |fix files|
    line_recall         = |changed lines ∩ slice lines| / |changed lines|
    efficiency          = unique context lines / total repository lines
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.code_intelligence.registry import CodeIntelligenceRegistry
from app.services.analysis_runner import AnalysisRunner
from app.services.analyze_issue_service import (
    build_analyze_issue_service,
)
from app.services.context_budget import ContextBudget
from app.services.context_builder_service import ContextBuilderService
from app.services.github_service import GithubService
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.services.llm_service import LLMService
from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer
from app.utils.repository_graph import RepositoryGraph

from evalutation.commit_benchmark import (
    BenchmarkError,
    discover_cases,
    load_case,
    load_snapshot,
)
from evalutation.ground_truth import (
    derive_ground_truth,
    exclusion_reason,
    pre_fix_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = REPO_ROOT / "backend" / ".env"

HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


class ContextBenchmarkError(BenchmarkError):
    """A context benchmark case could not be run."""


# =============================================================
# SNAPSHOT VALIDATION
# =============================================================

def verify_snapshot_parent(snapshot, ground_truth):
    """
    The snapshot must be frozen at the fix commit's first parent.

    Comparing context against a tree from the wrong commit makes every
    metric meaningless while still printing numbers.
    """

    snapshot_commit = snapshot.get("commit")
    parent_commit = ground_truth.get("parent_commit")

    if not snapshot_commit or not parent_commit:
        raise ContextBenchmarkError(
            "snapshot and ground truth must both record a commit SHA"
        )

    if snapshot_commit != parent_commit:
        raise ContextBenchmarkError(
            f"snapshot commit {snapshot_commit} is not the fix parent "
            f"{parent_commit}; re-snapshot with --parent-of "
            f"{ground_truth.get('fix_commit')}"
        )


# =============================================================
# CHANGED LINES FROM THE FIX DIFF
# =============================================================

def parse_patch_changed_lines(patch):
    """
    Old-file line numbers touched by a unified diff hunk.

    Only deletions and modifications on the pre-fix side count: a
    pure addition has no anchor line in the snapshot.
    """

    if not patch:
        return set()

    changed = set()
    old_line = None

    for line in patch.splitlines():
        match = HUNK_HEADER.match(line)

        if match:
            old_line = int(match.group(1))
            continue

        if old_line is None:
            continue

        if line.startswith("\\"):
            continue

        prefix = line[:1]

        if prefix == "-":
            changed.add(old_line)
            old_line += 1
        elif prefix == " ":
            old_line += 1
        elif prefix == "+":
            continue

    return changed


def derive_changed_lines(github, owner, repo, fix_commit):
    """
    Product-file line changes expressed against the pre-fix snapshot.

    Uses the same path filtering as `ground_truth.py` but keeps line
    numbers instead of only file paths.
    """

    ground_truth = derive_ground_truth(github, owner, repo, fix_commit)

    comparison = github.compare_commits(
        owner,
        repo,
        ground_truth["parent_commit"],
        ground_truth["fix_commit"],
    )

    changed_lines = {}

    for entry in comparison.get("files") or []:
        path = pre_fix_path(entry)

        if not path:
            continue

        if entry.get("status") == "added":
            continue

        if exclusion_reason(path):
            continue

        lines = parse_patch_changed_lines(entry.get("patch"))

        if lines:
            changed_lines[path] = sorted(lines)

    return ground_truth, changed_lines


# =============================================================
# SCORING
# =============================================================

def union_lines(ranges):
    """Unique 1-based line numbers covered by inclusive ranges."""

    covered = set()

    for start, end in ranges:
        if end < start:
            continue
        covered.update(range(start, end + 1))

    return covered


def slice_ranges(slices):
    grouped = {}

    for item in slices:
        grouped.setdefault(item["path"], []).append(
            (item["start_line"], item["end_line"])
        )

    return grouped


def score_context_files(expected_files, slices):
    expected = set(expected_files)
    context = {item["path"] for item in slices}

    hits = sorted(expected & context)
    missing = sorted(expected - context)

    recall = len(hits) / len(expected) if expected else 1.0

    return {
        "expected_files": sorted(expected),
        "context_files": sorted(context),
        "missing_files": missing,
        "context_file_recall": recall,
    }


def score_line_recall(changed_lines, slices):
    """
    Fraction of changed product lines falling inside a context slice.

    Overlapping slices are unioned per file so the same line is never
    counted twice in the numerator or denominator of coverage.
    """

    ranges = slice_ranges(slices)
    total_changed = 0
    covered_changed = 0
    uncovered = {}

    for path in sorted(changed_lines):
        lines = changed_lines[path]
        total_changed += len(lines)
        covered = union_lines(ranges.get(path, ()))
        hit = [line for line in lines if line in covered]
        miss = [line for line in lines if line not in covered]
        covered_changed += len(hit)

        if miss:
            uncovered[path] = miss

    recall = (
        covered_changed / total_changed
        if total_changed
        else 1.0
    )

    return {
        "changed_lines": changed_lines,
        "uncovered_lines": uncovered,
        "line_recall": recall,
        "changed_line_count": total_changed,
        "covered_changed_line_count": covered_changed,
    }


def score_efficiency(slices, files):
    """
    Unique context lines divided by total repository lines.

    Extra files in the package reduce efficiency but do not affect
    recall metrics.
    """

    ranges = slice_ranges(slices)
    context_lines = sum(
        len(union_lines(ranges.get(path, ())))
        for path in ranges
    )

    repository_lines = sum(
        len((file.get("content") or "").splitlines())
        for file in files
    )

    efficiency = (
        context_lines / repository_lines
        if repository_lines
        else 0.0
    )

    return {
        "context_lines_used": context_lines,
        "repository_lines": repository_lines,
        "efficiency": efficiency,
    }


def score_context_package(changed_lines, expected_files, slices, files):
    files_score = score_context_files(expected_files, slices)
    lines_score = score_line_recall(changed_lines, slices)
    efficiency_score = score_efficiency(slices, files)

    return {
        **files_score,
        **lines_score,
        **efficiency_score,
    }


def serialize_slices(slices):
    return [
        {
            "path": item.path,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "tier": item.tier,
            "reason": item.reason,
            "symbols": list(item.symbols),
            "truncated": item.truncated,
            "language": item.language,
            "adapter": item.adapter,
        }
        for item in slices
    ]


# =============================================================
# RUN
# =============================================================

def budget_to_dict(budget):
    return {
        "max_files": budget.max_files,
        "max_lines_total": budget.max_lines_total,
        "max_lines_per_file": budget.max_lines_per_file,
        "max_tests": budget.max_tests,
    }


def build_context_package(
    snapshot,
    case,
    analysis,
    diagnosis,
    files,
    budget=None,
):
    graph = RepositoryGraph(
        DartStructureAnalyzer().analyze_repository(files)
    )

    budget = budget or ContextBudget()

    builder = ContextBuilderService(
        CodeIntelligenceRegistry.default(),
        budget=budget,
    )

    return builder.build(
        issue={
            "number": case["issue_number"],
            "title": snapshot["issue"].get("title") or case.get("title") or "",
            "body": snapshot["issue"].get("body") or case.get("body") or "",
        },
        diagnosis=diagnosis,
        ranked=analysis["ranked"],
        direct_evidence=analysis["direct_evidence"],
        graph=graph,
        files=files,
        budget=budget,
    )


def prepare_case(case, github, llm, snapshot=None, extract_signals=False):
    """
    Run analysis and diagnosis once for a case.

    Budget sweeps reuse this output so every configuration sees the
    same diagnosis input — the part that would otherwise vary with
    the model.
    """

    snapshot = snapshot or load_snapshot(case)
    files = snapshot["files"]

    issue = {
        "title": case.get("title") or snapshot["issue"].get("title") or "",
        "body": case.get("body") or snapshot["issue"].get("body") or "",
    }

    ground_truth, changed_lines = derive_changed_lines(
        github,
        case["owner"],
        case["repo"],
        case["fix_commit"],
    )

    verify_snapshot_parent(snapshot, ground_truth)

    service = build_analyze_issue_service(files, llm_service=llm)

    pinned = None if extract_signals else case.get("signals")

    analysis = service.analyze(
        files=files,
        issue=issue,
        signals=pinned,
        available_n=10,
    )

    diagnosis = IssueDiagnosisService(llm_service=llm).diagnose(
        analysis
    )

    AnalysisRunner.attach_locations(diagnosis, files)

    return {
        "case": case,
        "case_path": case.get("_path"),
        "snapshot": snapshot,
        "files": files,
        "issue": issue,
        "analysis": analysis,
        "diagnosis": diagnosis,
        "ground_truth": ground_truth,
        "changed_lines": changed_lines,
        "signals_pinned": pinned is not None,
    }


def evaluate_prepared(prepared, budget=None):
    """Build and score a ContextPackage for one prepared case."""

    budget = budget or ContextBudget()
    case = prepared["case"]
    snapshot = prepared["snapshot"]
    files = prepared["files"]

    package = build_context_package(
        snapshot,
        case,
        prepared["analysis"],
        prepared["diagnosis"],
        files,
        budget=budget,
    )

    slices = serialize_slices(package.slices)

    metrics = score_context_package(
        prepared["changed_lines"],
        prepared["ground_truth"]["affected_files"],
        slices,
        files,
    )

    return {
        "case": prepared.get("case_path"),
        "issue": {
            "number": case["issue_number"],
            "title": prepared["issue"]["title"],
        },
        "metrics": metrics,
        "budget": budget_to_dict(budget),
        "budget_usage": package.budget,
        "files_used": package.budget.files_used,
        "lines_used": package.budget.lines_used,
        "context_package": package.to_dict(),
        "slices": slices,
        "omitted": [
            {"path": item.path, "reason": item.reason}
            for item in package.omitted
        ],
        "warnings": package.warnings,
    }


def run_case(
    case,
    github,
    llm,
    snapshot=None,
    extract_signals=False,
    budget=None,
):
    prepared = prepare_case(
        case,
        github=github,
        llm=llm,
        snapshot=snapshot,
        extract_signals=extract_signals,
    )

    evaluated = evaluate_prepared(prepared, budget=budget)
    ground_truth = prepared["ground_truth"]

    return {
        "case": prepared.get("case_path"),
        "repository": ground_truth["repository"],
        "issue": evaluated["issue"],
        "fix_commit": ground_truth["fix_commit"],
        "snapshot_commit": prepared["snapshot"].get("commit"),
        "parent_commit": ground_truth["parent_commit"],
        "signals_pinned": prepared["signals_pinned"],
        "ground_truth": ground_truth,
        "context_package": evaluated["context_package"],
        "slices": evaluated["slices"],
        "metrics": evaluated["metrics"],
        "budget": evaluated["budget_usage"],
        "warnings": evaluated["warnings"],
        "omitted": evaluated["omitted"],
    }


# =============================================================
# REPORT
# =============================================================

def report(result):
    metrics = result["metrics"]

    print(f"\nCASE   {result['case']}")
    print(
        f"ISSUE  #{result['issue']['number']}  "
        f"{result['issue']['title']}"
    )
    print(f"REPO   {result['repository']}")
    print(
        f"       snapshot {str(result['snapshot_commit'])[:8]}  "
        f"fix {result['fix_commit'][:8]}  "
        f"parent {result['parent_commit'][:8]}"
    )

    print(f"\n{'=' * 70}\nFILES\n{'=' * 70}")
    print(f"  expected (fix diff)      : {metrics['expected_files']}")
    print(f"  in context package     : {metrics['context_files']}")

    if metrics["missing_files"]:
        print(f"  MISSING                  : {metrics['missing_files']}")

    print(
        f"  context_file_recall      : "
        f"{metrics['context_file_recall']:.3f}"
    )

    print(f"\n{'=' * 70}\nLINES\n{'=' * 70}")

    for path, lines in sorted(metrics["changed_lines"].items()):
        print(f"  changed  {path}: {lines}")

    if metrics["uncovered_lines"]:
        print("  uncovered:")
        for path, lines in sorted(metrics["uncovered_lines"].items()):
            print(f"     {path}: {lines}")

    print(f"  line_recall              : {metrics['line_recall']:.3f}")

    print(f"\n{'=' * 70}\nSLICES\n{'=' * 70}")

    for item in result["slices"]:
        print(
            f"  T{item['tier']}  {item['path']}:{item['start_line']}-"
            f"{item['end_line']}  ({item['language']}/{item['adapter']})"
        )
        if item["symbols"]:
            print(f"       symbols: {', '.join(item['symbols'])}")
        print(f"       {item['reason']}")

    print(f"\n{'=' * 70}\nMETRICS\n{'=' * 70}")
    print(
        f"  context lines (unique)   : {metrics['context_lines_used']}"
    )
    print(f"  repository lines         : {metrics['repository_lines']}")
    print(f"  efficiency               : {metrics['efficiency']:.4f}")
    print(
        f"  budget lines used        : {result['budget'].lines_used}  "
        f"files {result['budget'].files_used}/"
        f"{result['budget'].max_files}"
    )

    if result["omitted"]:
        print(
            "  omitted                  : "
            + ", ".join(
                f"{item['path']} ({item['reason']})"
                for item in result["omitted"]
            )
        )

    if result["warnings"]:
        print("  warnings                 : " + "; ".join(result["warnings"]))


def summarize(results):
    scored = [item for item in results if not item.get("failed")]

    def mean(values):
        return sum(values) / len(values) if values else 0.0

    return {
        "cases": len(results),
        "scored": len(scored),
        "failed": len(results) - len(scored),
        "context_file_recall": mean(
            [item["metrics"]["context_file_recall"] for item in scored]
        ),
        "line_recall": mean(
            [item["metrics"]["line_recall"] for item in scored]
        ),
        "efficiency": mean(
            [item["metrics"]["efficiency"] for item in scored]
        ),
    }


def report_rollup(results, aggregate):
    header = (
        f"{'ISSUE':<44} {'FILES':>7} {'LINES':>7} {'EFF':>7}"
    )

    print(f"\n{'=' * len(header)}")
    print(header)
    print("=" * len(header))

    for result in results:
        if result.get("failed"):
            name = Path(result["case"]).stem
            print(f"{name:<44} {'FAILED':>7}  {result['error'][:40]}")
            continue

        metrics = result["metrics"]
        label = f"#{result['issue']['number']} {result['issue']['title']}"

        print(
            f"{label[:44]:<44} "
            f"{metrics['context_file_recall']:>7.3f} "
            f"{metrics['line_recall']:>7.3f} "
            f"{metrics['efficiency']:>7.4f}"
        )

    print("=" * len(header))
    print(
        f"{'MEAN':<44} "
        f"{aggregate['context_file_recall']:>7.3f} "
        f"{aggregate['line_recall']:>7.3f} "
        f"{aggregate['efficiency']:>7.4f}"
    )

    if aggregate["failed"]:
        print(
            f"\ncases not scored : {aggregate['failed']} "
            f"(excluded from means above)"
        )


def run_all(paths, github, llm, extract_signals=False):
    results = []

    for path in paths:
        try:
            results.append(
                run_case(
                    load_case(path),
                    github=github,
                    llm=llm,
                    extract_signals=extract_signals,
                )
            )
        except Exception as error:
            results.append({
                "case": str(path),
                "failed": True,
                "error": str(error),
            })

    return results


# =============================================================
# ENTRY POINT
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--case", help="run a single case file")
    target.add_argument(
        "--cases",
        metavar="DIR",
        help="run every *.json case in this directory",
    )
    parser.add_argument(
        "--extract-signals",
        action="store_true",
        help="ignore pinned signals and run the real extractor",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print structured JSON",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    if not os.getenv("GITHUB_TOKEN"):
        raise ContextBenchmarkError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    github = GithubService(os.getenv("GITHUB_TOKEN"))
    llm = LLMService()

    if args.cases:
        results = run_all(
            discover_cases(args.cases),
            github=github,
            llm=llm,
            extract_signals=args.extract_signals,
        )
        aggregate = summarize(results)

        if args.json:
            print(
                json.dumps(
                    {"results": results, "aggregate": aggregate},
                    indent=2,
                    default=str,
                )
            )
            return

        for result in results:
            if not result.get("failed"):
                report(result)

        report_rollup(results, aggregate)
        return

    result = run_case(
        load_case(args.case),
        github=github,
        llm=llm,
        extract_signals=args.extract_signals,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        report(result)


if __name__ == "__main__":
    try:
        main()
    except ContextBenchmarkError as error:
        print(f"context benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1)
