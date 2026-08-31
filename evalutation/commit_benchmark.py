"""
Commit-grounded benchmark runner.

Runs the real PatchPilot pipeline against a repository frozen as it was
BEFORE a fix landed, then scores it against what the fix actually
changed. The answer is not hand-labelled: `ground_truth.py` derives it
from the fix commit's diff.

    pre-fix snapshot  ->  pipeline  ->  ranked files + diagnosis
    fix commit        ->  ground truth
                                    ->  scored

This module orchestrates. It contains no retrieval, ranking, signal
extraction or diagnosis logic of its own, and calls exactly the
services production calls -- including the same location resolution --
because a benchmark that takes a different path measures something
other than the product.

Usage
-----

    PYTHONPATH=backend python3 -m evalutation.commit_benchmark \\
        --case evalutation/cases/task_refresh_commit.json

    # a whole directory of cases, with a summary table
    PYTHONPATH=backend python3 -m evalutation.commit_benchmark \\
        --cases evalutation/cases/commit_grounded

    # exercise the real signal extractor instead of pinned signals
    PYTHONPATH=backend python3 -m evalutation.commit_benchmark \\
        --cases evalutation/cases/commit_grounded --extract-signals

Reproducibility
---------------

Cases pin their signals. Signal extraction is a language-model call
and varies between runs -- the same case measured rank 3, 1, 1 on
three identical runs, flipping recall@1 between 0.00 and 1.00. With
signals held fixed, retrieval and ranking are deterministic, so a
before/after comparison measures the change rather than the weather.

What is NOT deterministic even with signals pinned: everything
downstream of `IssueDiagnosisService`, which is also a model call.
Root cause, cited files, precision and the PASS/FAIL verdict still
move between runs. The report labels which half is which.

`--extract-signals` ignores pinned signals and runs the real
extractor. Use it to measure extraction end to end; do not use it for
before/after comparisons of ranking.

    # structured output for a harness
    PYTHONPATH=backend python3 -m evalutation.commit_benchmark \\
        --case <case> --json
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.analysis_runner import AnalysisRunner
from app.services.analyze_issue_service import (
    build_analyze_issue_service,
)
from app.services.github_service import GithubService
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.services.llm_service import LLMService

from evalutation.ground_truth import derive_ground_truth

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = REPO_ROOT / "backend" / ".env"

# Ranks reported for retrieval recall. Anything past 10 is not a
# result a developer would scroll to.
RECALL_AT = (1, 3, 5, 10)

# A diagnosis "passes" when it named every file the fix actually
# changed, and -- where a case defines mechanism concepts -- described
# the failure in recognisable terms. Citing the right file for the
# wrong reason is not a correct diagnosis.
#
# The threshold is named rather than inlined because it is a judgement
# call, and a pass rate is only meaningful if the bar is visible.
MECHANISM_PASS_THRESHOLD = 0.5

REQUIRED_CASE_FIELDS = (
    "owner",
    "repo",
    "issue_number",
    "fix_commit",
    "snapshot",
)


class BenchmarkError(RuntimeError):
    """A benchmark case could not be run."""


# =============================================================
# CASE LOADING
# =============================================================

def load_case(path):
    """
    Load and validate a commit benchmark case.

    Every field is required up front rather than discovered halfway
    through: a case missing its fix commit cannot be scored, and
    finding that out after paying for two model calls is wasteful.
    """

    case_path = Path(path)

    if not case_path.exists():
        raise BenchmarkError(f"No case file at {case_path}")

    try:
        case = json.loads(case_path.read_text())
    except json.JSONDecodeError as e:
        raise BenchmarkError(f"{case_path} is not valid JSON: {e}") from e

    missing = [
        field
        for field in REQUIRED_CASE_FIELDS
        if not case.get(field)
    ]

    if missing:
        raise BenchmarkError(
            f"{case_path} is missing required field(s): "
            + ", ".join(missing)
        )

    case["_path"] = str(case_path)

    return case


def discover_cases(directory):
    """
    Every case file in a directory, in filename order.

    Sorted so a rollup is reproducible: an unordered listing makes two
    runs of the same suite print their rows differently, which makes
    diffing results needlessly hard.

    The runner has no built-in knowledge of which cases exist. A
    benchmark suite is a directory you point at, so adding a case
    means dropping in a file rather than editing this module.
    """

    path = Path(directory)

    if not path.is_absolute():
        path = REPO_ROOT / path

    if not path.exists():
        raise BenchmarkError(f"No case directory at {path}")

    if not path.is_dir():
        raise BenchmarkError(f"{path} is not a directory")

    cases = sorted(path.glob("*.json"))

    if not cases:
        raise BenchmarkError(
            f"{path} contains no .json case files"
        )

    return cases


def load_snapshot(case):
    """Load the pre-fix repository snapshot named by the case."""

    path = Path(case["snapshot"])

    if not path.is_absolute():
        path = REPO_ROOT / path

    if not path.exists():
        raise BenchmarkError(f"No snapshot at {path}")

    snapshot = json.loads(path.read_text())

    if not snapshot.get("files"):
        raise BenchmarkError(f"Snapshot {path} contains no files")

    return snapshot


# =============================================================
# SCORING
# =============================================================

def is_diagnosis_correct(files_score, mechanism):
    """
    Did the diagnosis actually get it right?

    Distinct from precision, which only says how much of what it named
    was relevant. This asks whether it found everything the fix
    touched, and understood why.
    """

    if not files_score["expected"]:
        return False

    if files_score["recall"] < 1.0:
        return False

    if mechanism is None:
        return True

    return mechanism["score"] >= MECHANISM_PASS_THRESHOLD


def worst_rank(files_score):
    """
    The deepest an expected file was buried, or None if any was
    missed entirely.

    Deliberately the WORST rather than the best: with two expected
    files, reporting the one at #1 would hide the one that never
    ranked at all.
    """

    ranks = list(files_score["rank_of_expected"].values())

    if not ranks or any(rank is None for rank in ranks):
        return None

    return max(ranks)


def score_files(expected, predicted, ranked):
    """
    Score retrieval and diagnosis against the files the fix changed.

    Two different questions are answered:

        recall_at   did RANKING surface the right file at all, and
                    how far down? This is the retrieval question.

        precision / recall
                    did the DIAGNOSIS cite the right files? This is
                    the reasoning question.

    They are reported separately because they fail for different
    reasons and are fixed in different places.
    """

    expected_set = set(expected)
    predicted_set = set(predicted)

    hits = sorted(expected_set & predicted_set)

    ranked_paths = [entry["path"] for entry in ranked]

    rank_of = {
        path: (
            ranked_paths.index(path) + 1
            if path in ranked_paths
            else None
        )
        for path in sorted(expected_set)
    }

    recall_at = {}

    for k in RECALL_AT:
        top_k = set(ranked_paths[:k])
        recall_at[k] = (
            len(expected_set & top_k) / len(expected_set)
            if expected_set
            else 0.0
        )

    return {
        "expected": sorted(expected_set),
        "predicted": sorted(predicted_set),
        "hits": hits,
        "missed": sorted(expected_set - predicted_set),
        "recall": (
            len(hits) / len(expected_set) if expected_set else 0.0
        ),
        "precision": (
            len(hits) / len(predicted_set) if predicted_set else 0.0
        ),
        "rank_of_expected": rank_of,
        "recall_at": recall_at,
    }


def score_concepts(groups, text):
    """
    Score diagnosis prose against concept groups.

    A group is a list of ALTERNATIVES: any one of them satisfies it.
    That lets ground truth accept "TaskLoaded" or "emit(TaskLoaded"
    without demanding a particular phrasing from the model.

    Matching is substring and case-insensitive on purpose. This
    measures whether the diagnosis is about the right thing, not
    whether it worded it a particular way.
    """

    if not groups:
        return None

    haystack = (text or "").lower()

    matched = []
    missed = []

    for group in groups:
        alternatives = group if isinstance(group, list) else [group]

        hit = next(
            (
                alternative
                for alternative in alternatives
                if str(alternative).lower() in haystack
            ),
            None,
        )

        if hit is not None:
            matched.append(hit)
        else:
            missed.append(alternatives)

    return {
        "score": len(matched) / len(groups),
        "matched": matched,
        "missed": missed,
    }


# =============================================================
# RUN
# =============================================================

def run_case(case, github, llm, snapshot=None, extract_signals=False):
    """
    Run one benchmark case and return a structured result.

    `github` is used only to derive ground truth from the fix commit.
    The pipeline itself runs entirely against the offline snapshot.

    `extract_signals` discards the case's pinned signals and runs the
    real extractor. That measures extraction, at the cost of making
    the run non-reproducible.
    """

    snapshot = snapshot or load_snapshot(case)

    files = snapshot["files"]

    issue = {
        "title": case.get("title") or snapshot["issue"].get("title") or "",
        "body": case.get("body") or snapshot["issue"].get("body") or "",
    }

    # --- pipeline: exactly the production services ---------------
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

    ranked = AnalysisRunner._describe(analysis)

    # --- ground truth from the fix commit -------------------------
    ground_truth = derive_ground_truth(
        github,
        case["owner"],
        case["repo"],
        case["fix_commit"],
    )

    expected = ground_truth["affected_files"]

    files_score = score_files(
        expected,
        diagnosis.get("relevant_files") or [],
        ranked,
    )

    truth = case.get("diagnosis_ground_truth") or {}

    mechanism = score_concepts(
        truth.get("mechanism_concepts"),
        " ".join(
            [
                diagnosis.get("root_cause") or "",
                diagnosis.get("explanation") or "",
            ]
        ),
    )

    fix = score_concepts(
        truth.get("fix_concepts"),
        diagnosis.get("suggested_fix") or "",
    )

    return {
        "case": case.get("_path"),
        "correct": is_diagnosis_correct(files_score, mechanism),
        "worst_rank": worst_rank(files_score),
        "repository": ground_truth["repository"],
        "issue": {
            "number": case["issue_number"],
            "title": issue["title"],
        },
        "fix_commit": ground_truth["fix_commit"],
        "snapshot_commit": snapshot.get("commit"),
        "parent_commit": ground_truth["parent_commit"],
        "signals": analysis["signals"],
        "signals_pinned": pinned is not None,
        "ranked": [
            {
                "rank": entry["rank"],
                "path": entry["path"],
                "total_score": entry["total_score"],
            }
            for entry in ranked
        ],
        "ground_truth": ground_truth,
        "files": files_score,
        "diagnosis": {
            "root_cause": diagnosis.get("root_cause"),
            "confidence": diagnosis.get("confidence"),
            "suggested_fix": diagnosis.get("suggested_fix"),
            "root_cause_locations": diagnosis.get(
                "root_cause_locations"
            ),
            "locations": diagnosis.get("locations"),
        },
        "mechanism": mechanism,
        "fix": fix,
    }


# =============================================================
# REPORT
# =============================================================

def report(result):
    files = result["files"]

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

    if result["snapshot_commit"] != result["parent_commit"]:
        print(
            "       WARNING: the snapshot is not the fix's parent; "
            "this case may be measuring the wrong code"
        )

    print(
        "\nSIGNALS  "
        + ", ".join(
            f"{signal['term']} ({signal['type']})"
            for signal in result["signals"]
        )
        + (
            "   [pinned]"
            if result.get("signals_pinned")
            else "   [EXTRACTED -- this run is not reproducible]"
        )
    )

    print(f"\n{'=' * 70}\nRANKED (top 10)\n{'=' * 70}")

    expected = set(files["expected"])

    for entry in result["ranked"][:10]:
        marker = "<-- EXPECTED" if entry["path"] in expected else ""
        print(
            f"{entry['rank']:>3}  {entry['path']:<52} "
            f"{entry['total_score']:>6.2f}  {marker}"
        )

    print(f"\n{'=' * 70}\nFILES\n{'=' * 70}")
    print(f"  expected (from fix diff) : {files['expected']}")
    print(f"  predicted (diagnosis)    : {files['predicted']}")

    if files["missed"]:
        print(f"  MISSED                   : {files['missed']}")

    print(
        f"  recall {files['recall']:.2f}   "
        f"precision {files['precision']:.2f}"
    )

    print(
        "  rank of expected         : "
        + ", ".join(
            f"{path.split('/')[-1]}="
            f"{'not ranked' if rank is None else f'#{rank}'}"
            for path, rank in files["rank_of_expected"].items()
        )
    )

    print(
        "  recall@k                 : "
        + "  ".join(
            f"@{k}={value:.2f}"
            for k, value in files["recall_at"].items()
        )
    )

    excluded = result["ground_truth"]["excluded"]

    if excluded:
        print(
            "  excluded from truth      : "
            + ", ".join(
                f"{item['path']} ({item['reason']})"
                for item in excluded
            )
        )

    diagnosis = result["diagnosis"]

    print(f"\n{'=' * 70}\nDIAGNOSIS\n{'=' * 70}")
    print(f"  confidence : {diagnosis['confidence']}")
    print(f"  root cause : {diagnosis['root_cause']}")

    locations = diagnosis["root_cause_locations"] or []

    if locations:
        print("  resolved   :")
        for location in locations:
            print(
                f"     {location['symbol']}  ->  "
                f"{location['path']}:{location['line']}  "
                f"({location['kind']})"
            )
    else:
        print("  resolved   : none (falls back to file level)")

    for label, score in (
        ("mechanism", result["mechanism"]),
        ("fix      ", result["fix"]),
    ):
        if score is None:
            continue

        print(f"\n  {label} score : {score['score']:.2f}")

        if score["missed"]:
            print(f"    missed : {score['missed']}")


# =============================================================
# ROLLUP
# =============================================================

def run_all(paths, github, llm, extract_signals=False):
    """
    Run several cases and collect their results.

    A case that blows up is recorded and the run continues. One
    unreachable commit or one model hiccup must not destroy the other
    results — a partial rollup is still evidence, and a crashed one
    is not.
    """

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


def summarize(results):
    """
    Aggregate a set of case results.

    Means are taken over the cases that RAN. Failed cases are counted
    separately rather than scored as zero, because "we could not
    measure this" and "we measured it and it was wrong" are different
    facts and averaging them together hides the first.
    """

    scored = [r for r in results if not r.get("failed")]
    failed = [r for r in results if r.get("failed")]

    def mean(values):
        return sum(values) / len(values) if values else 0.0

    recall_at = {}

    for k in RECALL_AT:
        recall_at[k] = mean(
            [r["files"]["recall_at"][k] for r in scored]
        )

    return {
        "cases": len(results),
        "scored": len(scored),
        "failed": len(failed),
        "recall_at": recall_at,
        "precision": mean(
            [r["files"]["precision"] for r in scored]
        ),
        "recall": mean([r["files"]["recall"] for r in scored]),
        "diagnosis_passed": sum(
            1 for r in scored if r.get("correct")
        ),
        "signals_pinned": sum(
            1 for r in scored if r.get("signals_pinned")
        ),
        "mechanism": mean(
            [
                r["mechanism"]["score"]
                for r in scored
                if r.get("mechanism")
            ]
        ),
    }


def report_rollup(results, aggregate):
    header = (
        f"{'ISSUE':<44} {'RANK':>5} "
        + " ".join(f"{'@' + str(k):>5}" for k in RECALL_AT)
        + f" {'PREC':>6} {'DIAG':>6}"
    )

    print(f"\n{'=' * len(header)}")
    print(header)
    print("=" * len(header))

    for result in results:

        if result.get("failed"):
            name = Path(result["case"]).stem
            print(f"{name:<44} {'FAILED':>5}  {result['error'][:40]}")
            continue

        files = result["files"]
        label = f"#{result['issue']['number']} {result['issue']['title']}"

        rank = result["worst_rank"]

        print(
            f"{label[:44]:<44} "
            f"{('-' if rank is None else rank):>5} "
            + " ".join(
                f"{files['recall_at'][k]:>5.2f}" for k in RECALL_AT
            )
            + f" {files['precision']:>6.2f}"
            + f" {'PASS' if result['correct'] else 'FAIL':>6}"
        )

    print("=" * len(header))

    print(
        f"{'MEAN':<44} {'':>5} "
        + " ".join(
            f"{aggregate['recall_at'][k]:>5.2f}" for k in RECALL_AT
        )
        + f" {aggregate['precision']:>6.2f}"
        + f" {aggregate['diagnosis_passed']}/{aggregate['scored']:<4}"
    )

    print(
        f"\ndiagnosis passed : "
        f"{aggregate['diagnosis_passed']}/{aggregate['scored']}"
    )
    print(f"file recall      : {aggregate['recall']:.2f}")

    if aggregate["mechanism"]:
        print(f"mechanism        : {aggregate['mechanism']:.2f}")

    if aggregate["failed"]:
        print(
            f"cases not scored : {aggregate['failed']} "
            f"(excluded from every mean above)"
        )

    # Say plainly which numbers can be compared between runs. A
    # reader who treats a stochastic metric as a regression will
    # chase noise.
    if aggregate["signals_pinned"] == aggregate["scored"]:
        print(
            "\nRANK and @k are reproducible (signals pinned). "
            "PREC and DIAG depend on the diagnosis model and still "
            "vary between runs."
        )
    else:
        print(
            f"\nWARNING: {aggregate['scored'] - aggregate['signals_pinned']}"
            f"/{aggregate['scored']} case(s) extracted signals live. "
            "No metric in this table is reproducible; do not use it "
            "for a before/after comparison."
        )


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
        help=(
            "run every *.json case in this directory, in filename "
            "order, and print a summary table with aggregate means"
        ),
    )

    parser.add_argument(
        "--extract-signals",
        action="store_true",
        help=(
            "ignore pinned signals and run the real extractor. "
            "Measures extraction end to end, but the run is no "
            "longer reproducible -- not for before/after comparisons"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the structured result as JSON",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    if not os.getenv("GITHUB_TOKEN"):
        raise BenchmarkError(
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
    except BenchmarkError as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1)
