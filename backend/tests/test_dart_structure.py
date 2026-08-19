import os

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.issue_signal_service import IssueSignalService
from app.services.repository_search_service import RepositorySearchService
from app.services.repository_evidence_service import RepositoryEvidenceService
from app.services.repository_ranking_service import RepositoryRankingService

from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer
from app.utils.dart.dart_evidence_analyzer import DartEvidenceAnalyzer
from app.utils.repository_graph import RepositoryGraph

def _convert_structural_results(
    structural_results,
    files
):
    """
    Convert RepositoryGraph structural relationships into the
    file-based format expected by RepositoryRankingService.
    """

    files_by_path = {
        file["path"]: file
        for file in files
    }

    converted = []

    for result in structural_results:

        target_path = result["target"]

        target_file = files_by_path.get(
            target_path
        )

        if target_file is None:
            continue

        converted.append({
            "file": target_file,
            "source": result["source"],
            "target": target_path,
            "relationship": result["relationship"],
            "distance": result["distance"]
        })

    return converted

# ============================================================
# SETUP
# ============================================================

load_dotenv()

token = os.getenv("GITHUB_TOKEN")

if not token:
    raise RuntimeError(
        "GITHUB_TOKEN is not set"
    )

github = GithubService(token)

owner = "SanjayKParida"
repo = "car-rental-app"


# ============================================================
# SERVICES
# ============================================================

search = RepositorySearchService()

signal_service = IssueSignalService()

structure_analyzer = DartStructureAnalyzer()

evidence_analyzer = DartEvidenceAnalyzer()

ranking_service = RepositoryRankingService()


# ============================================================
# AUTHENTICATION
# ============================================================

user = github.authenticate()

print(
    "Authenticated as:",
    user["login"]
)


# ============================================================
# GET REPOSITORY FILES
# ============================================================

files = github.get_repository_source_files(
    owner,
    repo
)

print(
    f"Total files: {len(files)}"
)


# ============================================================
# BUILD REPOSITORY RELATIONSHIPS
# ============================================================

relationships = (
    structure_analyzer.analyze_repository(
        files
    )
)

print(
    "\n========== IMPLEMENTATION / "
    "STRUCTURAL RELATIONSHIPS =========="
)

for relationship in relationships:

    print(
        relationship["source"],
        "--",
        relationship["relationship"],
        "-->",
        relationship["target"]
    )


# ============================================================
# BUILD GRAPH
# ============================================================

graph = RepositoryGraph(
    relationships
)


# ============================================================
# EVIDENCE SERVICE
# ============================================================

evidence_service = RepositoryEvidenceService(
    evidence_analyzer=evidence_analyzer,
    graph=graph
)


# ============================================================
# GET ISSUE
# ============================================================

issues = github.get_issues(
    owner,
    repo
)

if not issues:
    raise RuntimeError(
        "No GitHub issues found"
    )

issue = issues[0]


print(
    "\n========== ISSUE =========="
)

print(
    "TITLE:",
    issue["title"]
)

print(
    "BODY:",
    issue["body"]
)


# ============================================================
# EXTRACT ISSUE SIGNALS
# ============================================================

signals = signal_service.extract_signals(
    issue["title"],
    issue["body"]
)


print(
    "\n========== SIGNALS =========="
)

for signal in signals:

    print(
        signal["term"],
        "(",
        signal["type"],
        ")"
    )


# ============================================================
# DIRECT + STRUCTURAL EVIDENCE
# ============================================================

print(
    "\n========== "
    "DIRECT CODE EVIDENCE "
    "=========="
)

direct_evidence = (
    evidence_service.analyze_files(
        files,
        signals
    )
)

for item in direct_evidence:

    print(
        f"{item['file']['path']} "
        f"| {item['evidence_type']} "
        f"| concept={item['concept']} "
        f"| strength={item['strength']} "
        f"| line={item['line']} "
        f"| identifier={item['identifier']}"
    )


print(
    "\n========== "
    "DIRECT EVIDENCE SUMMARY "
    "=========="
)

direct_by_file = (
    evidence_service.group_direct_evidence(
        direct_evidence
    )
)

for path, evidence in direct_by_file.items():

    print(
        f"\n{path}"
    )

    for item in evidence:

        print(
            f"  -> {item['evidence_type']} "
            f"| {item['concept']} "
            f"| strength={item['strength']} "
            f"| line={item['line']} "
            f"| {item['identifier']}"
        )


# ============================================================
# RETRIEVAL
# ============================================================

print(
    "\n========== "
    "RETRIEVAL "
    "=========="
)


rankings = []


for signal in signals:

    term = signal["term"]
    signal_type = signal["type"]

    print(
        f"\n--- {term} ({signal_type}) ---"
    )

    # --------------------------------------------------------
    # PATH SEARCH
    # --------------------------------------------------------

    path_results = search.search(
        files,
        term
    )

    path_seed_paths = {
        file["path"]
        for file in path_results
    }

    print(
        "\nPath matches:"
    )

    if path_seed_paths:

        for path in sorted(
            path_seed_paths
        ):
            print(
                "  ->",
                path
            )

    else:

        print(
            "  None"
        )

    # --------------------------------------------------------
    # CONTENT SEARCH
    # --------------------------------------------------------

    content_results = (
        search.search_content(
            files,
            term
        )
    )

    content_seed_paths = {
        result["file"]["path"]
        for result in content_results
    }

    print(
        "\nContent matches:"
    )

    if content_seed_paths:

        for path in sorted(
            content_seed_paths
        ):
            print(
                "  ->",
                path
            )

    else:

        print(
            "  None"
        )

    # --------------------------------------------------------
    # COMBINE RETRIEVAL SEEDS
    # --------------------------------------------------------

    seed_paths = (
        path_seed_paths |
        content_seed_paths
    )

    print(
        "\nCombined seed files:"
    )

    if seed_paths:

        for path in sorted(
            seed_paths
        ):
            print(
                "  ->",
                path
            )

    else:

        print(
            "  None"
        )

    # --------------------------------------------------------
    # STRUCTURAL EXPANSION
    # --------------------------------------------------------

    structural_results = (
        evidence_service.expand_candidates(
            seed_paths,
            max_depth=2,
            include_reverse=True
        )
    )

    structural_paths = {
        result["target"]
        for result in structural_results
    }

    structural_paths -= seed_paths

    print(
        "\nStructural candidates:"
    )

    if structural_paths:

        for path in sorted(
            structural_paths
        ):
            print(
                "  ->",
                path
            )

    else:

        print(
            "  None"
        )

    # --------------------------------------------------------
    # STRUCTURAL EVIDENCE
    # --------------------------------------------------------

    print(
        "\nStructural evidence:"
    )

    if structural_results:

        for result in structural_results:

            print(
                f"  -> "
                f"{result['source']} "
                f"-- {result['relationship']} --> "
                f"{result['target']} "
                f"| distance={result['distance']}"
            )

    else:

        print(
            "  None"
        )

    # --------------------------------------------------------
    # RANK THIS SIGNAL
    # --------------------------------------------------------

    ranking = ranking_service.rank(
        signal=signal,
        path_results=path_results,
        content_results=content_results,
        structural_results=_convert_structural_results(
            structural_results,
            files
        )
    )

    rankings.append(
        ranking
    )


# ============================================================
# AGGREGATE RANKINGS
# ============================================================

final_scores = (
    ranking_service.aggregate(
        rankings
    )
)


# ============================================================
# FINAL RANKING
# ============================================================

print(
    "\n========== "
    "FINAL RANKING "
    "=========="
)

sorted_scores = sorted(
    final_scores.items(),
    key=lambda item: item[1]["total_score"],
    reverse=True
)


for index, (
    sha,
    score
) in enumerate(
    sorted_scores,
    start=1
):

    print(
        f"\n{index}. {score['path']}"
    )

    print(
        f"   path_score="
        f"{score['path_score']:.3f}"
    )

    print(
        f"   content_score="
        f"{score['content_score']:.3f}"
    )

    print(
        f"   structural_score="
        f"{score.get('structural_score', 0):.3f}"
    )

    print(
        f"   total_score="
        f"{score['total_score']:.3f}"
    )


# ============================================================
# DEPENDENCY TEST
# ============================================================

print(
    "\n========== "
    "DEPENDENCY TEST "
    "=========="
)

target = (
    "lib/presentation/bloc/car_bloc.dart"
)

print(
    "Target:",
    target
)

for depth in [1, 2, 3]:

    print(
        f"\nDepth {depth}:"
    )

    dependencies = (
        graph.get_dependencies(
            target,
            max_depth=depth
        )
    )

    if not dependencies:

        print(
            "-> None"
        )

    else:

        for dependency, distance in (
            dependencies.items()
        ):

            print(
                f"-> {dependency} "
                f"| distance: {distance}"
            )
