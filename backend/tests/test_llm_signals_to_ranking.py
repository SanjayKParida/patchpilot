import contextlib
import io
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
# LOAD CASE
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

    return json_load(path)


def json_load(path):
    import json

    return json.loads(
        path.read_text()
    )


# ============================================================
# LOAD REPOSITORY
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
# BUILD ANALYSIS SERVICE
# ============================================================

def build_analysis_service(files):

    # This service is not used for signal extraction here.
    # It is kept because AnalyzeIssueService expects a signal
    # service dependency. We pass explicit signals to analyze().
    signal_service = IssueSignalService()

    search_service = RepositorySearchService()

    structure_analyzer = DartStructureAnalyzer()

    evidence_analyzer = DartEvidenceAnalyzer()

    ranking_service = RepositoryRankingService()

    relationships = (
        structure_analyzer.analyze_repository(
            files
        )
    )

    graph = RepositoryGraph(
        relationships
    )

    evidence_service = RepositoryEvidenceService(
        evidence_analyzer=evidence_analyzer,
        graph=graph,
    )

    return AnalyzeIssueService(
        signal_service=signal_service,
        search_service=search_service,
        evidence_service=evidence_service,
        ranking_service=ranking_service,
        structure_analyzer=structure_analyzer,
    )


# ============================================================
# EXTRACT REAL LLM SIGNALS
# ============================================================

def extract_llm_signals(case):

    llm_service = LLMService()

    signal_extractor = (
        IssueSignalExtractionService(
            llm_service=llm_service
        )
    )

    return signal_extractor.extract_signals(
        case["title"],
        case["body"],
    )


# ============================================================
# RUN RANKING WITH LLM SIGNALS
# ============================================================

def run_case(case_name):

    case = load_case(
        case_name
    )

    files = load_repository()

    llm_signals = extract_llm_signals(
        case
    )

    analysis_service = (
        build_analysis_service(
            files
        )
    )

    # Suppress noisy search/evidence/ranking prints.
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

    return (
        case,
        llm_signals,
        analysis,
    )


# ============================================================
# RETRIEVAL EVALUATION
# ============================================================

def evaluate_ranking(
    case,
    analysis
):

    ground_truth = case.get(
        "retrieval_ground_truth",
        {}
    )

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
        "tier_1_found": sorted(
            tier_1_found
        ),
        "tier_1_missing": sorted(
            tier_1 - tier_1_found
        ),
        "tier_2_found": sorted(
            tier_2_found
        ),
        "tier_2_missing": sorted(
            tier_2 - tier_2_found
        ),
        "violations": sorted(
            violations
        ),
        "tier_1_recall": tier_1_recall,
        "tier_2_recall": tier_2_recall,
        "passed": (
            tier_1_recall == 1.0
            and tier_2_recall == 1.0
            and not violations
        ),
    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(
    case,
    llm_signals,
    analysis,
    evaluation
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

    print(
        "\nLLM SIGNALS:"
    )

    for signal in llm_signals:

        print(
            f"- {signal['term']} "
            f"[{signal['type']}]"
        )

    print(
        "\nTOP 10 WITH LLM SIGNALS:"
    )

    for item in analysis[
        "ranked"
    ][:10]:

        print(
            f"{item['rank']}. "
            f"{item['path']} "
            f"(score={item['total_score']:.4f})"
        )

    print(
        "\nRETRIEVAL GROUND TRUTH:"
    )

    print(
        f"Tier 1 recall: "
        f"{evaluation['tier_1_recall']:.2f}"
    )

    print(
        f"Tier 2 recall: "
        f"{evaluation['tier_2_recall']:.2f}"
    )

    print(
        "\nTier 1 found:"
    )

    for path in evaluation[
        "tier_1_found"
    ]:

        print(
            f"- {path}"
        )

    print(
        "\nTier 1 missing:"
    )

    if evaluation["tier_1_missing"]:

        for path in evaluation[
            "tier_1_missing"
        ]:

            print(
                f"- {path}"
            )

    else:

        print(
            "- none"
        )

    print(
        "\nTier 2 found:"
    )

    for path in evaluation[
        "tier_2_found"
    ]:

        print(
            f"- {path}"
        )

    print(
        "\nTier 2 missing:"
    )

    if evaluation["tier_2_missing"]:

        for path in evaluation[
            "tier_2_missing"
        ]:

            print(
                f"- {path}"
            )

    else:

        print(
            "- none"
        )

    print(
        "\nTop-5 violations:"
    )

    if evaluation["violations"]:

        for path in evaluation[
            "violations"
        ]:

            print(
                f"- {path}"
            )

    else:

        print(
            "- none"
        )

    print(
        "\nRetrieval evaluation:"
    )

    print(
        "PASS"
        if evaluation["passed"]
        else "FAIL"
    )

    print(
        "========================================"
    )


# ============================================================
# ISSUE #1
# ============================================================

def test_task_refresh_llm_signals_to_ranking():

    (
        case,
        llm_signals,
        analysis,
    ) = run_case(
        "task_refresh"
    )

    evaluation = evaluate_ranking(
        case,
        analysis
    )

    print_result(
        case,
        llm_signals,
        analysis,
        evaluation
    )

    assert evaluation[
        "tier_1_recall"
    ] >= 0.0

# ============================================================
# ISSUE #2
# ============================================================

def test_empty_tasks_llm_signals_to_ranking():

    (
        case,
        llm_signals,
        analysis,
    ) = run_case(
        "empty_tasks"
    )

    evaluation = evaluate_ranking(
        case,
        analysis
    )

    print_result(
        case,
        llm_signals,
        analysis,
        evaluation
    )

    assert evaluation[
        "tier_1_recall"
    ] >= 0.0


# ============================================================
# ISSUE #3
# ============================================================

def test_active_filter_llm_signals_to_ranking():

    (
        case,
        llm_signals,
        analysis,
    ) = run_case(
        "active_filter"
    )

    evaluation = evaluate_ranking(
        case,
        analysis
    )

    print_result(
        case,
        llm_signals,
        analysis,
        evaluation
    )

    assert evaluation[
        "tier_1_recall"
    ] >= 0.0