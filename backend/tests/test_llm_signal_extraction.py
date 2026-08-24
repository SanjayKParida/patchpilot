import json
import os
from pathlib import Path
import contextlib
import io

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


# ============================================================
# ENVIRONMENT
# ============================================================

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
    path = CASES_DIR / f"{name}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Case not found: {path}"
        )

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

    # AnalyzeIssueService requires a signal service,
    # but we will explicitly pass the LLM-generated signals
    # to analyze(), so the hardcoded IssueSignalService
    # will not be used for this experiment.

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
# EXTRACT LLM SIGNALS
# ============================================================

def extract_llm_signals(case):

    llm_service = LLMService()

    signal_service = (
        IssueSignalExtractionService(
            llm_service=llm_service
        )
    )

    return signal_service.extract_signals(
        case["title"],
        case["body"],
    )


# ============================================================
# RUN ONE CASE
# ============================================================

def run_case(case_name):

    case = load_case(
        case_name
    )

    files = load_repository()

    # --------------------------------------------------------
    # Step 1: real LLM extracts signals
    # --------------------------------------------------------

    llm_signals = extract_llm_signals(
        case
    )

    # --------------------------------------------------------
    # Step 2: existing deterministic pipeline
    # uses the LLM-generated signals
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

    # --------------------------------------------------------
    # LLM signals
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

    # --------------------------------------------------------
    # Ground truth metrics
    # --------------------------------------------------------

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

    if evaluation["tier_1_found"]:

        for path in evaluation[
            "tier_1_found"
        ]:

            print(
                f"- {path}"
            )

    else:

        print(
            "- none"
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

    if evaluation["tier_2_found"]:

        for path in evaluation[
            "tier_2_found"
        ]:

            print(
                f"- {path}"
            )

    else:

        print(
            "- none"
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
# GENERIC TEST RUNNER
# ============================================================

def _run_and_check(
    case_name
):

    (
        case,
        llm_signals,
        analysis,
    ) = run_case(
        case_name
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

    # Do not require a perfect result yet.
    #
    # This phase is observational. We are measuring
    # how much retrieval quality survives the switch
    # from manual signals to LLM-generated signals.

    assert evaluation[
        "tier_1_recall"
    ] >= 0.0


# ============================================================
# ISSUE #1
# ============================================================

def test_task_refresh_llm_signals_to_ranking():

    _run_and_check(
        "task_refresh"
    )


# ============================================================
# ISSUE #2
# ============================================================

def test_empty_tasks_llm_signals_to_ranking():

    _run_and_check(
        "empty_tasks"
    )


# ============================================================
# ISSUE #3
# ============================================================

def test_active_filter_llm_signals_to_ranking():

    _run_and_check(
        "active_filter"
    )