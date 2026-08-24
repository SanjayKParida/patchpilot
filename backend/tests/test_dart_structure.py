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


# ============================================================
# HELPERS
# ============================================================

def print_candidate_diagnostics(
    sorted_scores,
    files,
    direct_evidence,
    structural_results,
    top_n=5
):
    """
    Print a compact explanation of why the highest-ranked files
    were considered relevant.

    This is diagnostic only.
    It does NOT affect ranking.
    """

    files_by_path = {
        file["path"]: file
        for file in files
    }

    direct_by_file = {}

    for evidence in direct_evidence:

        file = evidence.get("file")

        if not file:
            continue

        path = file.get("path")

        if not path:
            continue

        direct_by_file.setdefault(
            path,
            []
        ).append(evidence)

    structural_by_target = {}

    for relationship in structural_results:

        target = relationship.get("target")

        if not target:
            continue

        structural_by_target.setdefault(
            target,
            []
        ).append(relationship)

    print(
        "\n============ "
        "TOP CANDIDATE DIAGNOSTICS "
        "============"
    )

    for rank, (sha, score) in enumerate(
        sorted_scores[:top_n],
        start=1
    ):

        path = score["path"]

        print(
            f"\n{rank}. {path}"
        )

        print(
            f"   Score: "
            f"{score['total_score']:.3f}"
        )

        # Confidences accumulate once per matched signal; show the
        # mean so the channels stay comparable between files.
        matched = max(
            score.get("signals_matched", 0),
            1
        )

        print(
            f"   Direct: "
            f"{score['direct_score']:.3f} | "
            f"Structural: "
            f"{score.get('structural_score', 0):.3f} | "
            f"signals={score.get('signals_matched', 0)}"
        )

        print(
            f"   Mean confidence — "
            f"evidence={score['evidence_confidence'] / matched:.2f} "
            f"content={score['content_confidence'] / matched:.2f} "
            f"path={score['path_confidence'] / matched:.2f}"
        )

        # ----------------------------------------------------
        # Direct evidence
        # ----------------------------------------------------

        evidence = direct_by_file.get(
            path,
            []
        )

        if evidence:

            print(
                "   Direct evidence:"
            )

            # Strongest evidence first.
            strongest = sorted(
                evidence,
                key=lambda item: item.get(
                    "strength",
                    0
                ),
                reverse=True
            )[:6]

            for item in strongest:

                print(
                    f"     - "
                    f"{item['concept']} → "
                    f"{item['evidence_type']} "
                    f"'{item['identifier']}' "
                    f"(strength={item['strength']}, "
                    f"line={item['line']})"
                )

        else:

            print(
                "   Direct evidence: none"
            )

        # ----------------------------------------------------
        # Structural evidence
        # ----------------------------------------------------

        relationships = (
            structural_by_target.get(
                path,
                []
            )
        )

        if relationships:

            print(
                "   Structural evidence:"
            )

            # Only show the closest / strongest
            # structural relationships.
            relationships = sorted(
                relationships,
                key=lambda item: item.get(
                    "distance",
                    999
                )
            )[:5]

            for relationship in relationships:

                print(
                    f"     - "
                    f"{relationship['relationship']} "
                    f"from "
                    f"{relationship['source']} "
                    f"(distance="
                    f"{relationship['distance']})"
                )

        else:

            print(
                "   Structural evidence: none"
            )

        # ----------------------------------------------------
        # File existence sanity check
        # ----------------------------------------------------

        if path not in files_by_path:

            print(
                "   WARNING: file not found "
                "in repository file set"
            )

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


def _print_section(title):
    print(
        f"\n{'=' * 12} {title} {'=' * 12}"
    )


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
    f"Authenticated as: {user['login']}"
)


# ============================================================
# GET REPOSITORY
# ============================================================

files = github.get_repository_source_files(
    owner,
    repo
)

print(
    f"Repository: {owner}/{repo}"
)

print(
    f"Source files: {len(files)}"
)


# ============================================================
# BUILD STRUCTURAL GRAPH
# ============================================================

relationships = (
    structure_analyzer.analyze_repository(
        files
    )
)

graph = RepositoryGraph(
    relationships
)

print(
    f"Structural relationships: "
    f"{len(relationships)}"
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


# ============================================================
# ISSUE
# ============================================================

_print_section("ISSUE")

print(
    issue["title"]
)


# ============================================================
# SIGNALS
# ============================================================

signals = signal_service.extract_signals(
    issue["title"],
    issue["body"]
)

_print_section("SIGNALS")

for signal in signals:

    print(
        f"- {signal['term']} "
        f"[{signal['type']}]"
    )


# ============================================================
# DIRECT EVIDENCE
# ============================================================

direct_evidence = (
    evidence_service.analyze_files(
        files,
        signals
    )
)

# Path, content and structural retrieval all drop test files.
# Evidence must use the same filter or tests re-enter the ranking.
direct_evidence = [
    item
    for item in direct_evidence
    if search.is_candidate_file(
        item["file"]
    )
]

direct_by_file = (
    evidence_service.group_direct_evidence(
        direct_evidence
    )
)

_print_section("DIRECT EVIDENCE")

print(
    f"Evidence records: {len(direct_evidence)}"
)

print(
    f"Files with evidence: {len(direct_by_file)}"
)

# Only print files that actually contain evidence.
for path, evidence in sorted(
    direct_by_file.items()
):

    print(
        f"\n{path}"
    )

    # Show only the strongest few pieces of evidence.
    strongest = sorted(
        evidence,
        key=lambda item: item.get(
            "strength",
            0
        ),
        reverse=True
    )[:5]

    for item in strongest:

        print(
            f"  - {item['evidence_type']} "
            f"{item['identifier']} "
            f"(concept={item['concept']}, "
            f"strength={item['strength']}, "
            f"line={item['line']})"
        )


# ============================================================
# RETRIEVAL + RANKING
# ============================================================

rankings = []

all_seed_paths = set()

all_structural_results = []

for signal in signals:

    term = signal["term"]

    path_results = search.search(
        files,
        term
    )

    content_results = (
        search.search_content(
            files,
            term
        )
    )

    path_seed_paths = {
        file["path"]
        for file in path_results
    }

    content_seed_paths = {
        result["file"]["path"]
        for result in content_results
    }

    seed_paths = (
        path_seed_paths |
        content_seed_paths
    )

    all_seed_paths.update(
        seed_paths
    )

    # --------------------------------------------------------
    # Filter production candidates
    # --------------------------------------------------------

    seed_paths = {
        path
        for path in seed_paths
        if search.is_candidate_file({
            "path": path
        })
    }

    structural_results = (
        evidence_service.expand_candidates(
            seed_paths,
            max_depth=2,
            include_reverse=True
        )
    )

    structural_results = [
        result
        for result in structural_results
        if search.is_candidate_file({
            "path": result["target"]
        })
    ]

    all_structural_results.extend(
        structural_results
    )

    ranking = ranking_service.rank(
        signal=signal,
        path_results=path_results,
        content_results=content_results,
        structural_results=_convert_structural_results(
            structural_results,
            files
        ),
        direct_evidence=direct_evidence
    )

    rankings.append(
        ranking
    )


# ============================================================
# RETRIEVAL SUMMARY
# ============================================================

structural_paths = {
    result["target"]
    for result in all_structural_results
}

structural_paths -= all_seed_paths

_print_section("RETRIEVAL SUMMARY")

print(
    f"Direct seed files: "
    f"{len(all_seed_paths)}"
)

print(
    f"Structural candidates: "
    f"{len(structural_paths)}"
)

if all_seed_paths:

    print("\nSeed files:")

    for path in sorted(
        all_seed_paths
    ):

        print(
            f"  - {path}"
        )

if structural_paths:

    print("\nStructural candidates:")

    for path in sorted(
        structural_paths
    ):

        print(
            f"  - {path}"
        )


# ============================================================
# AGGREGATE RANKING
# ============================================================

final_scores = (
    ranking_service.aggregate(
        rankings
    )
)


# ============================================================
# FINAL RANKING
# ============================================================

sorted_scores = sorted(
    final_scores.items(),
    key=lambda item: item[1]["total_score"],
    reverse=True
)

_print_section("FINAL RANKING")

for index, (
    sha,
    score
) in enumerate(
    sorted_scores[:10],
    start=1
):

    print(
        f"{index}. {score['path']}"
    )

    matched = score.get("signals_matched", 0)

    print(
        f"   total={score['total_score']:.3f} "
        f"(direct={score['direct_score']:.3f}, "
        f"structural={score.get('structural_score', 0):.3f}) "
        f"signals={matched}"
    )


# ============================================================
# TOP CANDIDATE DIAGNOSTICS
# ============================================================

print_candidate_diagnostics(
    sorted_scores,
    files,
    direct_evidence,
    all_structural_results
)


# ============================================================
# TOP CANDIDATE DEPENDENCIES
# ============================================================

_print_section("TOP CANDIDATE DEPENDENCIES")

if sorted_scores:

    top_sha, top_score = (
        sorted_scores[0]
    )

    top_path = top_score["path"]

    print(
        f"Top candidate: {top_path}"
    )

    dependencies = (
        graph.get_dependencies(
            top_path,
            max_depth=3
        )
    )

    if dependencies:

        for dependency, distance in sorted(
            dependencies.items(),
            key=lambda item: item[1]
        ):

            print(
                f"  -> {dependency} "
                f"[distance={distance}]"
            )

    else:

        print(
            "  No dependencies found."
        )


# ============================================================
# EVIDENCE SUMMARY
# ============================================================

_print_section("EVIDENCE SUMMARY")

combined_evidence = {
    "direct": direct_evidence,
    "structural": all_structural_results
}

summary = evidence_service.summarize(
    combined_evidence
)

print(
    f"Direct evidence records: "
    f"{summary['direct_evidence_count']}"
)

print(
    f"Files with direct evidence: "
    f"{summary['direct_file_count']}"
)

print(
    f"Structural evidence records: "
    f"{summary['structural_evidence_count']}"
)

print(
    f"Structural candidate files: "
    f"{summary['structural_file_count']}"
)


# ============================================================
# END
# ============================================================

_print_section("DONE")