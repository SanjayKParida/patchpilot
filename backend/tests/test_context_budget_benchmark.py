"""
Tests for context budget calibration.

Pure configuration and aggregation logic is tested without calling
GitHub or a language model.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.context_budget import ContextBudget  # noqa: E402

from evalutation.context_budget_benchmark import (  # noqa: E402
    aggregate_configuration,
    baseline_budget,
    budget_key,
    generate_all_experiments,
    generate_combination_experiments,
    generate_single_dimension_experiments,
    minimum_passing_values,
    passes_recall_constraint,
    select_best_configuration,
    sort_experiments,
)
from evalutation.context_benchmark import budget_to_dict  # noqa: E402


def _case_result(
    file_recall=1.0,
    line_recall=1.0,
    efficiency=0.5,
    files_used=8,
    lines_used=400,
    case="case.json",
    issue_number=1,
):
    return {
        "case": case,
        "issue": {"number": issue_number, "title": "x"},
        "metrics": {
            "context_file_recall": file_recall,
            "line_recall": line_recall,
            "efficiency": efficiency,
            "missing_files": [],
            "uncovered_lines": {},
        },
        "files_used": files_used,
        "lines_used": lines_used,
    }


def test_single_dimension_experiments_are_deterministically_ordered():
    first = generate_single_dimension_experiments()
    second = generate_single_dimension_experiments()

    assert first == second
    assert first[0][0] == "baseline"
    assert first[0][1] == baseline_budget()
    assert first[1][0] == "max_files=3"


def test_generate_all_experiments_matches_phase_one():
    assert generate_all_experiments() == generate_single_dimension_experiments()


def test_budget_key_deduplicates_identical_configurations():
    baseline = baseline_budget()
    assert budget_key(baseline) == budget_key(baseline)


def test_aggregate_configuration_uses_minimum_recall_across_cases():
    row = aggregate_configuration(
        "test",
        ContextBudget(max_files=6),
        [
            _case_result(file_recall=1.0, line_recall=1.0, issue_number=1),
            _case_result(file_recall=0.5, line_recall=1.0, issue_number=2),
        ],
    )

    assert row["context_file_recall"] == 0.5
    assert row["line_recall"] == 1.0
    assert row["passes_recall"] is False
    assert row["files_used"] == 8
    assert row["lines_used"] == 400


def test_aggregate_configuration_marks_full_recall_as_passing():
    row = aggregate_configuration(
        "baseline",
        baseline_budget(),
        [
            _case_result(file_recall=1.0, line_recall=1.0, efficiency=0.48),
            _case_result(file_recall=1.0, line_recall=1.0, efficiency=0.52),
        ],
    )

    assert row["passes_recall"] is True
    assert row["efficiency"] == pytest.approx(0.5)


def test_passes_recall_constraint_requires_both_metrics():
    assert passes_recall_constraint({"passes_recall": True}) is True
    assert passes_recall_constraint({"passes_recall": False}) is False


def test_minimum_passing_values_picks_the_smallest_passing_sweep():
    baseline = baseline_budget()
    rows = [
        {
            "label": "baseline",
            "budget": budget_to_dict(baseline),
            "passes_recall": True,
        },
        {
            "label": "max_files=12",
            "budget": {"max_files": 12, "max_lines_total": 1200,
                       "max_lines_per_file": 400, "max_tests": 2},
            "passes_recall": True,
        },
        {
            "label": "max_files=8",
            "budget": {"max_files": 8, "max_lines_total": 1200,
                       "max_lines_per_file": 400, "max_tests": 2},
            "passes_recall": True,
        },
        {
            "label": "max_files=6",
            "budget": {"max_files": 6, "max_lines_total": 1200,
                       "max_lines_per_file": 400, "max_tests": 2},
            "passes_recall": False,
        },
    ]

    promising = minimum_passing_values(rows, baseline)

    assert promising["max_files"] == 8
    assert promising["max_lines_total"] == 1200


def test_select_best_configuration_prefers_smaller_budget():
    baseline_row = {
        "label": "baseline",
        "budget": {
            "max_files": 12,
            "max_lines_total": 1200,
            "max_lines_per_file": 400,
            "max_tests": 2,
        },
        "efficiency": 0.48,
        "passes_recall": True,
    }
    rows = [
        baseline_row,
        {
            "label": "smaller",
            "budget": {
                "max_files": 8,
                "max_lines_total": 800,
                "max_lines_per_file": 300,
                "max_tests": 1,
            },
            "efficiency": 0.40,
            "passes_recall": True,
        },
        {
            "label": "too_small",
            "budget": {
                "max_files": 4,
                "max_lines_total": 400,
                "max_lines_per_file": 100,
                "max_tests": 0,
            },
            "efficiency": 0.20,
            "passes_recall": False,
        },
    ]

    best, gain = select_best_configuration(rows, baseline_row)

    assert best["label"] == "smaller"
    assert gain == pytest.approx((0.48 - 0.40) / 0.48)


def test_sort_experiments_orders_by_budget_then_label():
    rows = sort_experiments([
        {
            "label": "b",
            "budget": {
                "max_files": 10,
                "max_lines_total": 1200,
                "max_lines_per_file": 400,
                "max_tests": 2,
            },
        },
        {
            "label": "a",
            "budget": {
                "max_files": 8,
                "max_lines_total": 1200,
                "max_lines_per_file": 400,
                "max_tests": 2,
            },
        },
    ])

    assert rows[0]["label"] == "a"
    assert rows[1]["label"] == "b"


def test_combination_experiments_include_promising_and_relaxed_variants():
    baseline = baseline_budget()
    promising = {
        "max_files": 8,
        "max_lines_total": 800,
        "max_lines_per_file": 200,
        "max_tests": 1,
    }

    combos = generate_combination_experiments(baseline, promising)
    labels = [label for label, _budget in combos]

    assert labels[0] == "promising"
    assert "promising+max_files" in labels
