"""
Production-path integration tests.

issue → LLM signal extraction → retrieval/ranking → diagnosis

These tests observe the live pipeline. They do not enforce
retrieval or diagnosis ground truth; that belongs to the
controlled benchmark in test_task_diagnosis.py.
"""

import contextlib
import io

import pytest

from app.services.analyze_issue_service import (
    build_analyze_issue_service,
)
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.services.llm_service import LLMService
from tests.integration_helpers import (
    load_case,
    load_task_demo_files,
)


pytestmark = pytest.mark.integration


def evaluate_retrieval(case, analysis):
    ground_truth = case["retrieval_ground_truth"]
    tier_1 = set(ground_truth.get("tier_1", []))
    tier_2 = set(ground_truth.get("tier_2", []))
    forbidden_top_5 = set(ground_truth.get("forbidden_top_5", []))

    ranked = analysis["ranked"]
    top_5 = {item["path"] for item in ranked[:5]}
    top_10 = {item["path"] for item in ranked[:10]}

    tier_1_found = tier_1 & top_5
    tier_2_found = tier_2 & top_10
    violations = forbidden_top_5 & top_5

    return {
        "tier_1_recall": (
            len(tier_1_found) / len(tier_1) if tier_1 else 0.0
        ),
        "tier_2_recall": (
            len(tier_2_found) / len(tier_2) if tier_2 else 0.0
        ),
        "tier_1_found": sorted(tier_1_found),
        "tier_2_found": sorted(tier_2_found),
        "tier_1_missing": sorted(tier_1 - tier_1_found),
        "tier_2_missing": sorted(tier_2 - tier_2_found),
        "violations": sorted(violations),
    }


def concept_group_matches(text, alternatives):
    normalized_text = text.lower()
    return any(
        alternative.lower() in normalized_text
        for alternative in alternatives
    )


def concepts_score(text, concept_groups):
    if not concept_groups:
        return 0.0

    matched = sum(
        1
        for group in concept_groups
        if concept_group_matches(text, group)
    )
    return matched / len(concept_groups)


def evaluate_diagnosis(case, diagnosis):
    ground_truth = case["diagnosis_ground_truth"]
    expected_files = set(ground_truth.get("affected_files", []))
    predicted_files = set(diagnosis.get("relevant_files", []))
    correct_files = expected_files & predicted_files

    file_score = (
        len(correct_files) / len(expected_files)
        if expected_files
        else 0.0
    )

    mechanism_text = (
        diagnosis.get("root_cause", "")
        + " "
        + diagnosis.get("explanation", "")
    )
    mechanism_score = concepts_score(
        mechanism_text,
        ground_truth.get("mechanism_concepts", []),
    )
    fix_score = concepts_score(
        diagnosis.get("suggested_fix", ""),
        ground_truth.get("fix_concepts", []),
    )

    return {
        "file_score": file_score,
        "mechanism_score": mechanism_score,
        "fix_score": fix_score,
        "overall": (file_score + mechanism_score + fix_score) / 3,
        "expected_files": sorted(expected_files),
        "predicted_files": sorted(predicted_files),
    }


def run_case(case_name):
    case = load_case(case_name)
    files = load_task_demo_files()
    llm_service = LLMService()

    analysis_service = build_analyze_issue_service(
        files,
        llm_service=llm_service,
    )

    with contextlib.redirect_stdout(io.StringIO()):
        analysis = analysis_service.analyze(
            files=files,
            issue={
                "title": case["title"],
                "body": case["body"],
            },
            top_n=5,
            available_n=10,
        )

    diagnosis = IssueDiagnosisService(
        llm_service=llm_service,
    ).diagnose(analysis)

    return case, analysis["signals"], analysis, diagnosis


def print_result(
    case,
    llm_signals,
    analysis,
    diagnosis,
    retrieval,
    diagnosis_eval,
):
    print("\n========================================")
    print(f"ISSUE #{case['issue_number']}")
    print(case["title"])

    print("\nLLM SIGNALS:")
    for signal in llm_signals:
        print(f"- {signal['term']} [{signal['type']}]")

    print("\nTOP 10:")
    for item in analysis["ranked"][:10]:
        print(
            f"{item['rank']}. {item['path']} "
            f"(score={item['total_score']:.4f})"
        )

    print("\nRETRIEVAL:")
    print(f"Tier 1 recall: {retrieval['tier_1_recall']:.2f}")
    print(f"Tier 2 recall: {retrieval['tier_2_recall']:.2f}")
    print("Top-5 violations:")
    if retrieval["violations"]:
        for path in retrieval["violations"]:
            print(f"- {path}")
    else:
        print("- none")

    print("\nDIAGNOSIS:")
    print("\nRoot cause:")
    print(diagnosis["root_cause"])
    print("\nConfidence:")
    print(diagnosis["confidence"])
    print("\nRelevant files:")
    for path in diagnosis["relevant_files"]:
        print(f"- {path}")
    print("\nExplanation:")
    print(diagnosis["explanation"])
    print("\nSuggested fix:")
    print(diagnosis["suggested_fix"])

    print("\nDIAGNOSIS SCORES:")
    print(f"Root-cause file: {diagnosis_eval['file_score']:.2f}")
    print(f"Mechanism: {diagnosis_eval['mechanism_score']:.2f}")
    print(f"Fix: {diagnosis_eval['fix_score']:.2f}")
    print(f"Overall: {diagnosis_eval['overall']:.2f}")
    print("========================================")


def _run_case(case_name):
    case, llm_signals, analysis, diagnosis = run_case(case_name)
    retrieval = evaluate_retrieval(case, analysis)
    diagnosis_eval = evaluate_diagnosis(case, diagnosis)
    print_result(
        case,
        llm_signals,
        analysis,
        diagnosis,
        retrieval,
        diagnosis_eval,
    )

    assert llm_signals
    assert diagnosis["root_cause"]
    assert 0 <= diagnosis["confidence"] <= 1


def test_task_refresh_end_to_end():
    _run_case("task_refresh")


def test_empty_tasks_end_to_end():
    _run_case("empty_tasks")


def test_active_filter_end_to_end():
    _run_case("active_filter")
