import contextlib
import io
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.issue_signal_extraction_service import (
    IssueSignalExtractionService,
)
from app.services.llm_service import LLMService
from app.services.analyze_issue_service import AnalyzeIssueService
from app.services.issue_signal_service import IssueSignalService
from app.services.issue_diagnosis_service import (
    IssueDiagnosisService,
)
from app.services.repository_evidence_service import (
    RepositoryEvidenceService,
)
from app.services.repository_ranking_service import (
    RepositoryRankingService,
)
from app.services.repository_search_service import (
    RepositorySearchService,
)

from app.utils.dart.dart_evidence_analyzer import (
    DartEvidenceAnalyzer,
)
from app.utils.dart.dart_structure_analyzer import (
    DartStructureAnalyzer,
)
from app.utils.repository_graph import RepositoryGraph


load_dotenv()


# ============================================================
# CONFIG
# ============================================================

OWNER = "SanjayKParida"
REPO = "patchpilot-diagnosis-demo"

CASES_DIR = (
    Path(__file__).resolve().parents[2]
    / "evalutation"
    / "cases"
)


# ============================================================
# CASE
# ============================================================

def load_case(name):

    path = (
        CASES_DIR
        / f"{name}.json"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Case not found: {path}"
        )

    return json.loads(
        path.read_text()
    )


# ============================================================
# REPOSITORY
# ============================================================

def load_repository():

    token = os.getenv(
        "GITHUB_TOKEN"
    )

    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set"
        )

    github = GithubService(
        token
    )

    github.authenticate()

    files = github.get_repository_source_files(
        OWNER,
        REPO
    )

    if not files:
        raise RuntimeError(
            "No repository source files found"
        )

    return files


# ============================================================
# ANALYSIS SERVICE
# ============================================================

def build_analysis_service(files):

    # This dependency remains for AnalyzeIssueService's
    # constructor. We explicitly supply extracted signals
    # to analyze(), so the hardcoded extractor is bypassed.
    signal_service = IssueSignalService()

    search_service = RepositorySearchService()

    structure_analyzer = (
        DartStructureAnalyzer()
    )

    evidence_analyzer = (
        DartEvidenceAnalyzer()
    )

    ranking_service = (
        RepositoryRankingService()
    )

    relationships = (
        structure_analyzer.analyze_repository(
            files
        )
    )

    graph = RepositoryGraph(
        relationships
    )

    evidence_service = (
        RepositoryEvidenceService(
            evidence_analyzer=evidence_analyzer,
            graph=graph,
        )
    )

    return AnalyzeIssueService(
        signal_service=signal_service,
        search_service=search_service,
        evidence_service=evidence_service,
        ranking_service=ranking_service,
        structure_analyzer=structure_analyzer,
    )


# ============================================================
# SIGNAL EXTRACTION
# ============================================================

def extract_llm_signals(case):

    llm_service = LLMService()

    extractor = (
        IssueSignalExtractionService(
            llm_service=llm_service
        )
    )

    return extractor.extract_signals(
        case["title"],
        case["body"],
    )


# ============================================================
# RETRIEVAL EVALUATION
# ============================================================

def evaluate_retrieval(
    case,
    analysis
):

    ground_truth = case[
        "retrieval_ground_truth"
    ]

    tier_1 = set(
        ground_truth.get(
            "tier_1",
            []
        )
    )

    tier_2 = set(
        ground_truth.get(
            "tier_2",
            []
        )
    )

    forbidden_top_5 = set(
        ground_truth.get(
            "forbidden_top_5",
            []
        )
    )

    ranked = analysis[
        "ranked"
    ]

    top_5 = {
        item["path"]
        for item in ranked[:5]
    }

    top_10 = {
        item["path"]
        for item in ranked[:10]
    }

    tier_1_found = (
        tier_1 & top_5
    )

    tier_2_found = (
        tier_2 & top_10
    )

    violations = (
        forbidden_top_5 & top_5
    )

    tier_1_recall = (
        len(tier_1_found)
        / len(tier_1)
        if tier_1
        else 0.0
    )

    tier_2_recall = (
        len(tier_2_found)
        / len(tier_2)
        if tier_2
        else 0.0
    )

    return {
        "tier_1_recall": tier_1_recall,
        "tier_2_recall": tier_2_recall,
        "tier_1_found": sorted(
            tier_1_found
        ),
        "tier_2_found": sorted(
            tier_2_found
        ),
        "tier_1_missing": sorted(
            tier_1 - tier_1_found
        ),
        "tier_2_missing": sorted(
            tier_2 - tier_2_found
        ),
        "violations": sorted(
            violations
        ),
    }


# ============================================================
# DIAGNOSIS EVALUATION
# ============================================================

def concept_group_matches(
    text,
    alternatives
):

    normalized_text = text.lower()

    for alternative in alternatives:

        if (
            alternative.lower()
            in normalized_text
        ):
            return True

    return False


def concepts_score(
    text,
    concept_groups
):

    if not concept_groups:
        return 0.0

    matched = 0

    for group in concept_groups:

        if concept_group_matches(
            text,
            group
        ):
            matched += 1

    return (
        matched
        / len(concept_groups)
    )


def evaluate_diagnosis(
    case,
    diagnosis
):

    ground_truth = case[
        "diagnosis_ground_truth"
    ]

    expected_files = set(
        ground_truth.get(
            "affected_files",
            []
        )
    )

    predicted_files = set(
        diagnosis.get(
            "relevant_files",
            []
        )
    )

    correct_files = (
        expected_files
        & predicted_files
    )

    file_score = (
        len(correct_files)
        / len(expected_files)
        if expected_files
        else 0.0
    )

    mechanism_text = (
        diagnosis.get(
            "root_cause",
            ""
        )
        + " "
        + diagnosis.get(
            "explanation",
            ""
        )
    )

    mechanism_score = concepts_score(
        mechanism_text,
        ground_truth.get(
            "mechanism_concepts",
            []
        )
    )

    fix_score = concepts_score(
        diagnosis.get(
            "suggested_fix",
            ""
        ),
        ground_truth.get(
            "fix_concepts",
            []
        )
    )

    overall = (
        file_score
        + mechanism_score
        + fix_score
    ) / 3

    return {
        "file_score": file_score,
        "mechanism_score": mechanism_score,
        "fix_score": fix_score,
        "overall": overall,
        "expected_files": sorted(
            expected_files
        ),
        "predicted_files": sorted(
            predicted_files
        ),
    }


# ============================================================
# RUN ONE CASE
# ============================================================

def run_case(case_name):

    case = load_case(
        case_name
    )

    files = load_repository()

    # --------------------------------------------------------
    # 1. REAL LLM SIGNAL EXTRACTION
    # --------------------------------------------------------

    llm_signals = extract_llm_signals(
        case
    )

    # --------------------------------------------------------
    # 2. EXISTING DETERMINISTIC RETRIEVAL
    # --------------------------------------------------------

    analysis_service = (
        build_analysis_service(
            files
        )
    )

    buffer = io.StringIO()

    with contextlib.redirect_stdout(
        buffer
    ):

        analysis = (
            analysis_service.analyze(
                files=files,
                issue={
                    "title": case["title"],
                    "body": case["body"],
                },
                signals=llm_signals,
                top_n=5,
                available_n=10,
            )
        )

    # --------------------------------------------------------
    # 3. REAL LLM DIAGNOSIS
    # --------------------------------------------------------

    llm_service = LLMService()

    diagnosis_service = (
        IssueDiagnosisService(
            llm_service=llm_service
        )
    )

    diagnosis = (
        diagnosis_service.diagnose(
            analysis
        )
    )

    return (
        case,
        llm_signals,
        analysis,
        diagnosis,
    )


# ============================================================
# PRINT
# ============================================================

def print_result(
    case,
    llm_signals,
    analysis,
    diagnosis,
    retrieval,
    diagnosis_eval
):

    print(
        "\n========================================"
    )

    print(
        f"ISSUE #{case['issue_number']}"
    )

    print(
        case["title"]
    )

    # --------------------------------------------------------
    # Signals
    # --------------------------------------------------------

    print(
        "\nLLM SIGNALS:"
    )

    for signal in llm_signals:

        print(
            f"- {signal['term']} "
            f"[{signal['type']}]"
        )

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    print(
        "\nTOP 10:"
    )

    for item in analysis[
        "ranked"
    ][:10]:

        print(
            f"{item['rank']}. "
            f"{item['path']} "
            f"(score={item['total_score']:.4f})"
        )

    # --------------------------------------------------------
    # Retrieval
    # --------------------------------------------------------

    print(
        "\nRETRIEVAL:"
    )

    print(
        f"Tier 1 recall: "
        f"{retrieval['tier_1_recall']:.2f}"
    )

    print(
        f"Tier 2 recall: "
        f"{retrieval['tier_2_recall']:.2f}"
    )

    print(
        "Top-5 violations:"
    )

    if retrieval["violations"]:

        for path in retrieval[
            "violations"
        ]:

            print(
                f"- {path}"
            )

    else:

        print(
            "- none"
        )

    # --------------------------------------------------------
    # Diagnosis
    # --------------------------------------------------------

    print(
        "\nDIAGNOSIS:"
    )

    print(
        "\nRoot cause:"
    )

    print(
        diagnosis["root_cause"]
    )

    print(
        "\nConfidence:"
    )

    print(
        diagnosis["confidence"]
    )

    print(
        "\nRelevant files:"
    )

    for path in diagnosis[
        "relevant_files"
    ]:

        print(
            f"- {path}"
        )

    print(
        "\nExplanation:"
    )

    print(
        diagnosis["explanation"]
    )

    print(
        "\nSuggested fix:"
    )

    print(
        diagnosis["suggested_fix"]
    )

    # --------------------------------------------------------
    # Diagnosis scores
    # --------------------------------------------------------

    print(
        "\nDIAGNOSIS SCORES:"
    )

    print(
        f"Root-cause file: "
        f"{diagnosis_eval['file_score']:.2f}"
    )

    print(
        f"Mechanism: "
        f"{diagnosis_eval['mechanism_score']:.2f}"
    )

    print(
        f"Fix: "
        f"{diagnosis_eval['fix_score']:.2f}"
    )

    print(
        f"Overall: "
        f"{diagnosis_eval['overall']:.2f}"
    )

    print(
        "========================================"
    )


# ============================================================
# GENERIC TEST
# ============================================================

def _run_case(
    case_name
):

    (
        case,
        llm_signals,
        analysis,
        diagnosis,
    ) = run_case(
        case_name
    )

    retrieval = evaluate_retrieval(
        case,
        analysis
    )

    diagnosis_eval = (
        evaluate_diagnosis(
            case,
            diagnosis
        )
    )

    print_result(
        case,
        llm_signals,
        analysis,
        diagnosis,
        retrieval,
        diagnosis_eval,
    )

    # We are observing the end-to-end behavior
    # at this stage, not enforcing a hard pass/fail
    # on retrieval or diagnosis quality.

    assert llm_signals

    assert diagnosis[
        "root_cause"
    ]

    assert (
        0
        <= diagnosis["confidence"]
        <= 1
    )


# ============================================================
# ISSUE 1
# ============================================================

def test_task_refresh_end_to_end():

    _run_case(
        "task_refresh"
    )


# ============================================================
# ISSUE 2
# ============================================================

def test_empty_tasks_end_to_end():

    _run_case(
        "empty_tasks"
    )


# ============================================================
# ISSUE 3
# ============================================================

def test_active_filter_end_to_end():

    _run_case(
        "active_filter"
    )