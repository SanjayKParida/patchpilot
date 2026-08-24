import contextlib
import io
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.analyze_issue_service import AnalyzeIssueService
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.services.llm_service import LLMService

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
# RUN ONE CASE
# ============================================================

def run_case(case_name):

    case = load_case(
        case_name
    )

    files = load_repository()

    analysis_service = (
        build_analysis_service(
            files
        )
    )

    # Suppress noisy repository/ranking output.
    analysis_buffer = io.StringIO()

    with contextlib.redirect_stdout(
        analysis_buffer
    ):

        analysis = (
            analysis_service.analyze(
                files=files,
                issue={
                    "title": case["title"],
                    "body": ""
                },
                signals=case["signals"],
                top_n=5,
                available_n=10,
            )
        )

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

    return case, analysis, diagnosis


# ============================================================
# CONCEPT MATCHING
# ============================================================

def concept_group_matches(
    text,
    alternatives
):
    """
    OR within one concept group.

    Example:

        [
            "isCompleted",
            "!task.isCompleted",
            "non-completed"
        ]

    means any one of those surface forms can satisfy
    the same underlying concept.
    """

    normalized_text = text.lower()

    matches = []

    for alternative in alternatives:

        normalized_alternative = (
            alternative.lower()
        )

        if normalized_alternative in normalized_text:
            matches.append(
                alternative
            )

    return matches


def concepts_score(
    text,
    concept_groups
):
    """
    AND across concept groups.

    Each concept group represents one required
    idea. Any alternative within that group is
    sufficient.

    Example:

        [
            ["TaskFilter.active"],
            [
                "isCompleted",
                "non-completed",
                "incomplete",
                "!task.isCompleted"
            ]
        ]

    requires both concepts to be represented,
    while allowing multiple equivalent phrasings.
    """

    if not concept_groups:
        return 0.0, []

    matched_groups = 0

    matched_alternatives = []

    for group in concept_groups:

        matches = concept_group_matches(
            text,
            group
        )

        if matches:

            matched_groups += 1

            # Keep the first matching alternative
            # for readable reporting.
            matched_alternatives.append(
                matches[0]
            )

    score = (
        matched_groups
        / len(concept_groups)
    )

    return score, matched_alternatives


# ============================================================
# DIAGNOSIS EVALUATION
# ============================================================

def evaluate_diagnosis(
    case,
    diagnosis
):

    ground_truth = case[
        "diagnosis_ground_truth"
    ]

    # --------------------------------------------------------
    # ROOT-CAUSE FILE SCORE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MECHANISM SCORE
    # --------------------------------------------------------

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

    mechanism_concepts = (
        ground_truth.get(
            "mechanism_concepts",
            []
        )
    )

    (
        mechanism_score,
        mechanism_hits
    ) = concepts_score(
        mechanism_text,
        mechanism_concepts
    )

    # --------------------------------------------------------
    # FIX SCORE
    # --------------------------------------------------------

    fix_text = diagnosis.get(
        "suggested_fix",
        ""
    )

    fix_concepts = (
        ground_truth.get(
            "fix_concepts",
            []
        )
    )

    (
        fix_score,
        fix_hits
    ) = concepts_score(
        fix_text,
        fix_concepts
    )

    # --------------------------------------------------------
    # OVERALL
    # --------------------------------------------------------

    overall = (
        file_score
        + mechanism_score
        + fix_score
    ) / 3

    return {
        "expected_files": sorted(
            expected_files
        ),

        "predicted_files": sorted(
            predicted_files
        ),

        "correct_files": sorted(
            correct_files
        ),

        "file_score": file_score,

        "mechanism_score": mechanism_score,

        "mechanism_hits": mechanism_hits,

        "fix_score": fix_score,

        "fix_hits": fix_hits,

        "overall": overall,

        # For this phase, PASS means the actual
        # root-cause file was identified.
        #
        # We intentionally do not require a perfect
        # mechanism/fix score yet because these scores
        # are being calibrated.
        "passed": (
            file_score == 1.0
        ),
    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(
    case,
    analysis,
    diagnosis,
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
    # Signals
    # --------------------------------------------------------

    print(
        "\nSIGNALS:"
    )

    for signal in analysis["signals"]:

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

    for item in analysis["ranked"][:10]:

        print(
            f"{item['rank']}. "
            f"{item['path']} "
            f"(score={item['total_score']:.4f})"
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
    # Ground truth comparison
    # --------------------------------------------------------

    print(
        "\nGROUND TRUTH CHECK:"
    )

    print(
        "Expected affected files:"
    )

    for path in evaluation[
        "expected_files"
    ]:

        print(
            f"- {path}"
        )

    print(
        "\nPredicted relevant files:"
    )

    for path in evaluation[
        "predicted_files"
    ]:

        print(
            f"- {path}"
        )

    print(
        f"\nRoot-cause file score: "
        f"{evaluation['file_score']:.2f}"
    )

    print(
        f"Mechanism score: "
        f"{evaluation['mechanism_score']:.2f}"
    )

    print(
        f"Fix score: "
        f"{evaluation['fix_score']:.2f}"
    )

    print(
        f"Overall diagnosis score: "
        f"{evaluation['overall']:.2f}"
    )

    print(
        "\nMechanism evidence:"
    )

    if evaluation[
        "mechanism_hits"
    ]:

        for term in evaluation[
            "mechanism_hits"
        ]:

            print(
                f"- {term}"
            )

    else:

        print(
            "- none"
        )

    print(
        "\nFix evidence:"
    )

    if evaluation[
        "fix_hits"
    ]:

        for term in evaluation[
            "fix_hits"
        ]:

            print(
                f"- {term}"
            )

    else:

        print(
            "- none"
        )

    print(
        "\nDiagnosis evaluation:"
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
# GENERIC TEST HELPER
# ============================================================

def _run_and_assert(
    case_name
):

    case, analysis, diagnosis = (
        run_case(
            case_name
        )
    )

    evaluation = evaluate_diagnosis(
        case,
        diagnosis
    )

    print_result(
        case,
        analysis,
        diagnosis,
        evaluation
    )

    # --------------------------------------------------------
    # Basic LLM output validation
    # --------------------------------------------------------

    assert diagnosis[
        "root_cause"
    ]

    assert (
        0
        <= diagnosis["confidence"]
        <= 1
    )

    # --------------------------------------------------------
    # Ground-truth validation
    # --------------------------------------------------------

    assert (
        evaluation["file_score"]
        == 1.0
    )

    assert evaluation[
        "passed"
    ]


# ============================================================
# ISSUE 1
# ============================================================

def test_task_refresh_diagnosis():

    _run_and_assert(
        "task_refresh"
    )


# ============================================================
# ISSUE 2
# ============================================================

def test_empty_tasks_diagnosis():

    _run_and_assert(
        "empty_tasks"
    )


# ============================================================
# ISSUE 3
# ============================================================

def test_active_filter_diagnosis():

    _run_and_assert(
        "active_filter"
    )