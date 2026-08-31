"""
Context budget calibration over commit-grounded cases.

Finds the smallest practical ContextBudget that still preserves
context_file_recall = 1.0 and line_recall = 1.0 on every case in
the suite. Does not change production defaults — it only measures
and records.

    prepare cases once  ->  replay many budgets  ->  compare

Usage
-----

    PYTHONPATH=backend python -m evalutation.context_budget_benchmark

    PYTHONPATH=backend python -m evalutation.context_budget_benchmark \\
        --cases evalutation/cases/commit_grounded --json

Method
------

1. Vary one budget dimension at a time (others held at baseline).
2. Record the smallest passing value per dimension.
3. Test a small set of combinations of those values.
4. Report baseline, best passing config, and configs that lose recall.

These three cases are a narrow benchmark. Treat any recommendation
as provisional, not universally optimal.
"""

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from app.services.context_budget import ContextBudget
from app.services.github_service import GithubService
from app.services.llm_service import LLMService

from evalutation.commit_benchmark import discover_cases, load_case
from evalutation.context_benchmark import (
    ContextBenchmarkError,
    budget_to_dict,
    evaluate_prepared,
    prepare_case,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = REPO_ROOT / "backend" / ".env"

REPORT_PATH = (
    REPO_ROOT / "evalutation" / "baseline_context_budget_experiment.json"
)

BASELINE_PATH = REPO_ROOT / "evalutation" / "baseline_context.json"

DIMENSIONS = (
    "max_files",
    "max_lines_total",
    "max_lines_per_file",
    "max_tests",
)

# Candidate values for single-dimension sweeps. Sorted ascending so
# the smallest passing value is deterministic.
SWEEP_VALUES = {
    "max_files": [3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "max_lines_total": [200, 400, 600, 800, 1000, 1200],
    "max_lines_per_file": [50, 100, 150, 200, 250, 300, 350, 400],
    "max_tests": [0, 1, 2],
}


def baseline_budget():
    return ContextBudget()


def budget_key(budget):
    return (
        budget.max_files,
        budget.max_lines_total,
        budget.max_lines_per_file,
        budget.max_tests,
    )


def replace_budget(baseline, **overrides):
    return replace(baseline, **overrides)


def generate_single_dimension_experiments(baseline=None):
    """
    One dimension varies per experiment; the other three stay at
    baseline. Includes the baseline itself exactly once.
    """

    baseline = baseline or baseline_budget()
    experiments = []
    seen = set()

    def add(label, budget):
        key = budget_key(budget)
        if key in seen:
            return
        seen.add(key)
        experiments.append((label, budget))

    add("baseline", baseline)

    for dimension in DIMENSIONS:
        for value in SWEEP_VALUES[dimension]:
            add(
                f"{dimension}={value}",
                replace_budget(baseline, **{dimension: value}),
            )

    return experiments


def generate_combination_experiments(baseline, promising):
    """
    A small combination set built from the smallest passing value
    per dimension found in phase one.
    """

    baseline = baseline or baseline_budget()
    experiments = []
    seen = set()

    def add(label, budget):
        key = budget_key(budget)
        if key in seen:
            return
        seen.add(key)
        experiments.append((label, budget))

    merged = replace_budget(
        baseline,
        max_files=promising["max_files"],
        max_lines_total=promising["max_lines_total"],
        max_lines_per_file=promising["max_lines_per_file"],
        max_tests=promising["max_tests"],
    )
    add("promising", merged)

    for dimension in DIMENSIONS:
        relaxed = dict(promising)
        relaxed[dimension] = _next_sweep_value(
            dimension,
            promising[dimension],
            baseline,
        )
        add(
            f"promising+{dimension}",
            replace_budget(baseline, **relaxed),
        )

    return experiments


def generate_all_experiments(baseline=None):
    """
    Full experiment plan: single-dimension sweeps first, then a
    placeholder for combinations (filled after phase one runs).
    """

    return generate_single_dimension_experiments(baseline)


def _next_sweep_value(dimension, current, baseline):
    values = SWEEP_VALUES[dimension]
    baseline_value = getattr(baseline, dimension)

    for value in values:
        if value > current:
            return min(value, baseline_value)

    return baseline_value


def aggregate_configuration(label, budget, case_results):
    """
    Roll case metrics into one experiment row.

    Recall constraints require every case to pass, so the aggregate
    uses the minimum recall across cases.
    """

    file_recalls = [
        item["metrics"]["context_file_recall"] for item in case_results
    ]
    line_recalls = [
        item["metrics"]["line_recall"] for item in case_results
    ]
    efficiencies = [
        item["metrics"]["efficiency"] for item in case_results
    ]
    files_used = [item["files_used"] for item in case_results]
    lines_used = [item["lines_used"] for item in case_results]

    context_file_recall = min(file_recalls) if file_recalls else 0.0
    line_recall = min(line_recalls) if line_recalls else 0.0

    return {
        "label": label,
        "budget": budget_to_dict(budget),
        "context_file_recall": context_file_recall,
        "line_recall": line_recall,
        "efficiency": (
            sum(efficiencies) / len(efficiencies) if efficiencies else 0.0
        ),
        "files_used": max(files_used) if files_used else 0,
        "lines_used": max(lines_used) if lines_used else 0,
        "passes_recall": (
            context_file_recall >= 1.0 and line_recall >= 1.0
        ),
        "cases": [
            {
                "case": item["case"],
                "issue_number": item["issue"]["number"],
                "context_file_recall": item["metrics"]["context_file_recall"],
                "line_recall": item["metrics"]["line_recall"],
                "efficiency": item["metrics"]["efficiency"],
                "files_used": item["files_used"],
                "lines_used": item["lines_used"],
                "missing_files": item["metrics"]["missing_files"],
                "uncovered_lines": item["metrics"]["uncovered_lines"],
            }
            for item in case_results
        ],
    }


def passes_recall_constraint(row):
    return row.get("passes_recall") is True


def sort_experiments(rows):
    return sorted(
        rows,
        key=lambda item: (
            item["budget"]["max_files"],
            item["budget"]["max_lines_total"],
            item["budget"]["max_lines_per_file"],
            item["budget"]["max_tests"],
            item["label"],
        ),
    )


def select_best_configuration(rows, baseline_row):
    passing = [row for row in rows if passes_recall_constraint(row)]

    passing.sort(
        key=lambda item: (
            item["budget"]["max_files"],
            item["budget"]["max_lines_total"],
            item["budget"]["max_lines_per_file"],
            item["budget"]["max_tests"],
            item["efficiency"],
            item["label"],
        )
    )

    best = passing[0] if passing else None
    efficiency_gain = None

    if best and baseline_row:
        base_eff = baseline_row["efficiency"]
        if base_eff:
            efficiency_gain = (base_eff - best["efficiency"]) / base_eff

    return best, efficiency_gain


def minimum_passing_values(rows, baseline):
    """
    Smallest passing sweep value per dimension from phase-one rows.
    Falls back to baseline when no passing sweep exists.
    """

    promising = {
        dimension: getattr(baseline, dimension)
        for dimension in DIMENSIONS
    }

    for dimension in DIMENSIONS:
        passing_values = []

        for row in rows:
            if not row["label"].startswith(f"{dimension}="):
                continue
            if not passes_recall_constraint(row):
                continue
            passing_values.append(row["budget"][dimension])

        if passing_values:
            promising[dimension] = min(passing_values)

    return promising


def run_configuration(label, budget, prepared_cases):
    case_results = [
        evaluate_prepared(prepared, budget=budget)
        for prepared in prepared_cases
    ]
    return aggregate_configuration(label, budget, case_results)


def run_experiments(prepared_cases, experiments):
    rows = [
        run_configuration(label, budget, prepared_cases)
        for label, budget in experiments
    ]
    return sort_experiments(rows)


def load_reference_baseline():
    if not BASELINE_PATH.exists():
        return None

    return json.loads(BASELINE_PATH.read_text())


def build_report(prepared_cases):
    baseline = baseline_budget()
    phase_one = generate_single_dimension_experiments(baseline)
    phase_one_rows = run_experiments(prepared_cases, phase_one)

    promising = minimum_passing_values(phase_one_rows, baseline)
    phase_two = generate_combination_experiments(baseline, promising)

    # Only run combinations not already measured in phase one.
    measured = {budget_key(baseline_budget())}
    for row in phase_one_rows:
        measured.add(
            (
                row["budget"]["max_files"],
                row["budget"]["max_lines_total"],
                row["budget"]["max_lines_per_file"],
                row["budget"]["max_tests"],
            )
        )

    extra = []
    for label, budget in phase_two:
        if budget_key(budget) not in measured:
            extra.append((label, budget))
            measured.add(budget_key(budget))

    phase_two_rows = run_experiments(prepared_cases, extra)
    all_rows = sort_experiments(phase_one_rows + phase_two_rows)

    baseline_row = next(
        (row for row in all_rows if row["label"] == "baseline"),
        None,
    )
    best, efficiency_gain = select_best_configuration(
        all_rows,
        baseline_row,
    )

    failing = [
        row for row in all_rows if not passes_recall_constraint(row)
    ]

    return {
        "baseline": baseline_to_dict(baseline),
        "baseline_metrics": baseline_row,
        "reference_baseline_file": load_reference_baseline(),
        "promising_per_dimension": promising,
        "best": best,
        "efficiency_gain_vs_baseline": efficiency_gain,
        "experiments": all_rows,
        "configurations_that_lose_recall": failing,
        "recommendation": _recommendation(best, baseline, efficiency_gain),
        "note": (
            "Provisional calibration on three commit-grounded cases only. "
            "Production ContextBudget defaults are unchanged."
        ),
    }


def baseline_to_dict(budget):
    return budget_to_dict(budget)


def _recommendation(best, baseline, efficiency_gain):
    if best is None:
        return (
            "No configuration in the sweep preserved full recall on all "
            "three cases. Keep the current baseline defaults."
        )

    gain = ""
    if efficiency_gain is not None:
        gain = (
            f" Efficiency improves by {efficiency_gain * 100:.1f}% vs "
            f"baseline ({baseline.max_lines_total} total lines, "
            f"{baseline.max_files} files)."
        )

    return (
        "Smallest passing configuration in the sweep: "
        f"max_files={best['budget']['max_files']}, "
        f"max_lines_total={best['budget']['max_lines_total']}, "
        f"max_lines_per_file={best['budget']['max_lines_per_file']}, "
        f"max_tests={best['budget']['max_tests']}."
        f"{gain} Treat as provisional until approved."
    )


def report_table(report):
    rows = report["experiments"]
    header = (
        f"{'LABEL':<28} {'FILES':>5} {'LINES':>6} {'PFILE':>5} "
        f"{'TEST':>4} {'FREC':>5} {'LREC':>5} {'EFF':>7} "
        f"{'USED_F':>6} {'USED_L':>6} {'PASS':>4}"
    )

    print(f"\n{'=' * len(header)}")
    print(header)
    print("=" * len(header))

    for row in rows:
        budget = row["budget"]
        print(
            f"{row['label'][:28]:<28} "
            f"{budget['max_files']:>5} "
            f"{budget['max_lines_total']:>6} "
            f"{budget['max_lines_per_file']:>5} "
            f"{budget['max_tests']:>4} "
            f"{row['context_file_recall']:>5.3f} "
            f"{row['line_recall']:>5.3f} "
            f"{row['efficiency']:>7.4f} "
            f"{row['files_used']:>6} "
            f"{row['lines_used']:>6} "
            f"{'yes' if row['passes_recall'] else 'no':>4}"
        )

    print("=" * len(header))

    baseline = report["baseline_metrics"]
    best = report["best"]

    print("\nCURRENT BASELINE")
    print(f"  {json.dumps(report['baseline'], sort_keys=True)}")
    if baseline:
        print(
            f"  recall files={baseline['context_file_recall']:.3f} "
            f"lines={baseline['line_recall']:.3f} "
            f"efficiency={baseline['efficiency']:.4f}"
        )

    if best:
        print("\nBEST PASSING (smallest in sweep)")
        print(f"  label     : {best['label']}")
        print(f"  budget    : {json.dumps(best['budget'], sort_keys=True)}")
        print(
            f"  recall    : files={best['context_file_recall']:.3f} "
            f"lines={best['line_recall']:.3f}"
        )
        print(f"  efficiency: {best['efficiency']:.4f}")

        if report["efficiency_gain_vs_baseline"] is not None:
            print(
                f"  efficiency gain vs baseline: "
                f"{report['efficiency_gain_vs_baseline'] * 100:.1f}%"
            )

    print(f"\nRECOMMENDATION\n  {report['recommendation']}")

    failing = report["configurations_that_lose_recall"]
    print(f"\nCONFIGURATIONS THAT LOSE RECALL: {len(failing)}")

    for row in failing[:10]:
        print(
            f"  {row['label']}: "
            f"files={row['context_file_recall']:.3f} "
            f"lines={row['line_recall']:.3f}"
        )

    if len(failing) > 10:
        print(f"  ... and {len(failing) - 10} more")


def prepare_all(case_paths, github, llm, extract_signals=False):
    prepared = []

    for path in case_paths:
        prepared.append(
            prepare_case(
                load_case(path),
                github=github,
                llm=llm,
                extract_signals=extract_signals,
            )
        )

    return prepared


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cases",
        default="evalutation/cases/commit_grounded",
        help="directory of commit-grounded case files",
    )
    parser.add_argument(
        "--extract-signals",
        action="store_true",
        help="ignore pinned signals (not for before/after comparisons)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print structured JSON instead of a table",
    )
    parser.add_argument(
        "--out",
        default=str(REPORT_PATH),
        help="where to write the experiment report JSON",
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    if not os.getenv("GITHUB_TOKEN"):
        raise ContextBenchmarkError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    github = GithubService(os.getenv("GITHUB_TOKEN"))
    llm = LLMService()

    case_paths = discover_cases(args.cases)
    prepared = prepare_all(
        case_paths,
        github=github,
        llm=llm,
        extract_signals=args.extract_signals,
    )

    report = build_report(prepared)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True))

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        report_table(report)
        print(f"\nwrote {out}")


if __name__ == "__main__":
    try:
        main()
    except ContextBenchmarkError as error:
        print(f"context budget benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1)
