import contextlib
import io
import os

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.issue_signal_service import IssueSignalService
from app.services.analyze_issue_service import AnalyzeIssueService
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.services.llm_service import LLMService
from app.services.repository_evidence_service import RepositoryEvidenceService
from app.services.repository_ranking_service import RepositoryRankingService
from app.services.repository_search_service import RepositorySearchService

from app.utils.dart.dart_evidence_analyzer import DartEvidenceAnalyzer
from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer
from app.utils.repository_graph import RepositoryGraph


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIG
# ============================================================

OWNER = "SanjayKParida"
REPO = "car-rental-app"


# ============================================================
# LOAD REPOSITORY + ISSUE
# ============================================================

def load_repository():

    github_token = os.getenv(
        "GITHUB_TOKEN"
    )

    if not github_token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set"
        )

    github = GithubService(
        github_token
    )

    github.authenticate()

    files = (
        github.get_repository_source_files(
            OWNER,
            REPO
        )
    )

    issues = (
        github.get_issues(
            OWNER,
            REPO
        )
    )

    if not files:
        raise RuntimeError(
            "No repository source files found"
        )

    if not issues:
        raise RuntimeError(
            "No GitHub issues found"
        )

    return files, issues[0]


# ============================================================
# BUILD ANALYSIS SERVICE
# ============================================================

def build_analysis_service(files):

    signal_service = (
        IssueSignalService()
    )

    search_service = (
        RepositorySearchService()
    )

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
# MAIN EXPERIMENT
# ============================================================

def main():

    print(
        "\n========================================"
    )
    print(
        "PATCHPILOT REAL DIAGNOSIS EXPERIMENT"
    )
    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Repository
    # --------------------------------------------------------

    print(
        "\nLoading repository..."
    )

    files, issue = load_repository()

    print(
        f"Repository files: {len(files)}"
    )

    # --------------------------------------------------------
    # Analysis
    # --------------------------------------------------------

    analyze_service = (
        build_analysis_service(
            files
        )
    )

    print(
        "\nRunning deterministic analysis..."
    )

    # Suppress the ranking/search diagnostics.
    buffer = io.StringIO()

    with contextlib.redirect_stdout(
        buffer
    ):

        analysis = (
            analyze_service.analyze(
                files=files,
                issue=issue,
                top_n=5,
                available_n=10,
            )
        )

    # --------------------------------------------------------
    # Print issue
    # --------------------------------------------------------

    print(
        "\n============ ISSUE ============"
    )

    print(
        "TITLE:",
        issue["title"]
    )

    print(
        "\nBODY:"
    )

    print(
        issue["body"]
    )

    # --------------------------------------------------------
    # Signals
    # --------------------------------------------------------

    print(
        "\n============ SIGNALS ============"
    )

    for signal in analysis[
        "signals"
    ]:

        print(
            f"- {signal['term']} "
            f"[{signal['type']}]"
        )

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    print(
        "\n============ TOP 10 ============"
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
    # Diagnosis
    # --------------------------------------------------------

    print(
        "\n============ LLM DIAGNOSIS ============"
    )

    llm_service = (
        LLMService()
    )

    diagnosis_service = (
        IssueDiagnosisService(
            llm_service=llm_service
        )
    )

    print(
        "\nSending analysis package to LLM..."
    )

    diagnosis = (
        diagnosis_service.diagnose(
            analysis
        )
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

    print(
        "\n========================================"
    )
    print(
        "EXPERIMENT COMPLETE"
    )
    print(
        "========================================"
    )


if __name__ == "__main__":
    main()