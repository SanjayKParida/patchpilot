import contextlib
import io
import os

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.issue_signal_service import IssueSignalService
from app.services.analyze_issue_service import AnalyzeIssueService
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
REPO = "car-rental-app"


# ============================================================
# LIVE REPOSITORY
# ============================================================

def load_repository():
    """
    Load the repository and first GitHub issue using the same
    source used by the existing live harness.
    """

    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. "
            "Check your .env file and make sure it contains "
            "GITHUB_TOKEN=..."
        )

    github = GithubService(token)

    github.authenticate()

    files = github.get_repository_source_files(
        OWNER,
        REPO
    )

    issues = github.get_issues(
        OWNER,
        REPO
    )

    if not files:
        raise RuntimeError(
            "Repository returned no source files"
        )

    if not issues:
        raise RuntimeError(
            "Repository returned no issues"
        )

    # Keep this consistent with the existing live harness.
    issue = issues[0]

    return files, issue


# ============================================================
# SERVICE CONSTRUCTION
# ============================================================

def build_service(files):
    """
    Build AnalyzeIssueService using the existing production
    components.
    """

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
# RUN ANALYSIS
# ============================================================

def run_analysis():
    """
    Run AnalyzeIssueService quietly so pytest output remains readable.
    """

    files, issue = load_repository()

    service = build_service(files)

    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):

        result = service.analyze(
            files=files,
            issue=issue,
            top_n=5,
            available_n=10,
        )

    return files, issue, result


# ============================================================
# RESULT SHAPE
# ============================================================

def test_analyze_issue_service_returns_expected_shape():

    files, issue, result = run_analysis()

    assert result["issue"] == issue

    assert "signals" in result
    assert "ranked" in result
    assert "primary_files" in result
    assert "available_files" in result
    assert "direct_evidence" in result
    assert "structural_results" in result
    assert "seed_paths" in result

    assert result["ranked"]


# ============================================================
# CURRENT SIGNAL CONTRACT
# ============================================================

def test_current_signal_contract():

    _, _, result = run_analysis()

    signal_terms = {
        signal["term"]
        for signal in result["signals"]
    }

    expected = {
        "firebase",
        "firestore",
        "loading",
        "car",
        "repository",
        "bloc",
    }

    assert signal_terms == expected


# ============================================================
# RANKING EXISTS
# ============================================================

def test_ranked_results_are_sorted():

    _, _, result = run_analysis()

    ranked = result["ranked"]

    assert ranked

    assert ranked[0]["rank"] == 1

    scores = [
        item["total_score"]
        for item in ranked
    ]

    assert scores == sorted(
        scores,
        reverse=True
    )


# ============================================================
# PHASE 5 TIER 1
# ============================================================

def test_phase5_tier_one_is_in_top_five():

    _, _, result = run_analysis()

    top_5 = {
        item["path"]
        for item in result["ranked"][:5]
    }

    expected = {
        "lib/presentation/pages/car_list_screen.dart",
        "lib/presentation/bloc/car_bloc.dart",
        "lib/data/repositories/car_repository_impl.dart",
        "lib/data/datasources/firebase_car_data_source.dart",
        "lib/presentation/bloc/car_state.dart",
    }

    assert expected.issubset(
        top_5
    )


# ============================================================
# PHASE 5 TIER 2
# ============================================================

def test_phase5_tier_two_is_in_top_ten():

    _, _, result = run_analysis()

    top_10 = {
        item["path"]
        for item in result["ranked"][:10]
    }

    expected = {
        "lib/domain/repositories/car_repository.dart",
        "lib/domain/usecases/get_cars.dart",
        "lib/main.dart",
        "lib/injection_container.dart",
        "lib/presentation/bloc/car_event.dart",
    }

    assert expected.issubset(
        top_10
    )


# ============================================================
# DISTRACTOR GUARD
# ============================================================

def test_known_distractors_are_not_in_top_five():

    _, _, result = run_analysis()

    top_5 = {
        item["path"]
        for item in result["ranked"][:5]
    }

    forbidden = {
        "lib/firebase_options.dart",
        "lib/injection_container.dart",
        "lib/presentation/pages/car_details_page.dart",
        "lib/presentation/widgets/car_card.dart",
        "lib/presentation/widgets/more_card.dart",
        "lib/presentation/pages/MapsDetailsPage.dart",
        "lib/presentation/pages/onboarding_page.dart",
    }

    assert top_5.isdisjoint(
        forbidden
    )


# ============================================================
# PRIMARY FILES
# ============================================================

def test_primary_files_are_full_files():

    _, _, result = run_analysis()

    primary_files = result["primary_files"]

    assert len(primary_files) == 5

    for file in primary_files:

        assert "path" in file
        assert "content" in file

        assert isinstance(
            file["content"],
            str
        )

        assert file["content"].strip()


# ============================================================
# PRIMARY FILES MATCH TOP FIVE
# ============================================================

def test_primary_files_match_top_five():

    _, _, result = run_analysis()

    expected = [
        item["path"]
        for item in result["ranked"][:5]
    ]

    actual = [
        file["path"]
        for file in result["primary_files"]
    ]

    assert actual == expected


# ============================================================
# AVAILABLE FILES = RANK 6-10
# ============================================================

def test_available_files_match_rank_six_to_ten():

    _, _, result = run_analysis()

    expected = [
        item["path"]
        for item in result["ranked"][5:10]
    ]

    assert result["available_files"] == expected


# ============================================================
# PRIMARY / AVAILABLE DISJOINT
# ============================================================

def test_primary_and_available_files_do_not_overlap():

    _, _, result = run_analysis()

    primary = {
        file["path"]
        for file in result["primary_files"]
    }

    available = set(
        result["available_files"]
    )

    assert primary.isdisjoint(
        available
    )


# ============================================================
# DIRECT EVIDENCE
# ============================================================

def test_direct_evidence_exists():

    _, _, result = run_analysis()

    evidence = result["direct_evidence"]

    assert evidence

    evidence_paths = {
        item["file"]["path"]
        for item in evidence
    }

    assert (
        "lib/data/datasources/"
        "firebase_car_data_source.dart"
    ) in evidence_paths


# ============================================================
# STRUCTURAL EVIDENCE
# ============================================================

def test_structural_evidence_exists():

    _, _, result = run_analysis()

    structural = result["structural_results"]

    assert structural

    relationship_types = {
        item["relationship"]
        for item in structural
    }

    assert "imports" in relationship_types
    assert "implements" in relationship_types


# ============================================================
# RANKED PATHS EXIST
# ============================================================

def test_all_ranked_paths_exist():

    files, _, result = run_analysis()

    repository_paths = {
        file["path"]
        for file in files
    }

    for item in result["ranked"]:

        assert (
            item["path"]
            in repository_paths
        )


# ============================================================
# DETERMINISTIC FOR SAME SNAPSHOT
# ============================================================

def test_repeated_analysis_has_same_ranking():

    files, issue = load_repository()

    service = build_service(files)

    buffer_one = io.StringIO()
    buffer_two = io.StringIO()

    with contextlib.redirect_stdout(
        buffer_one
    ):

        first = service.analyze(
            files=files,
            issue=issue,
            top_n=5,
            available_n=10,
        )

    with contextlib.redirect_stdout(
        buffer_two
    ):

        second = service.analyze(
            files=files,
            issue=issue,
            top_n=5,
            available_n=10,
        )

    first_ranking = [
        (
            item["path"],
            round(
                item["total_score"],
                10
            ),
        )
        for item in first["ranked"]
    ]

    second_ranking = [
        (
            item["path"],
            round(
                item["total_score"],
                10
            ),
        )
        for item in second["ranked"]
    ]

    assert first_ranking == second_ranking