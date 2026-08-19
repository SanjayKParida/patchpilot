import os
from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.issue_signal_service import IssueSignalService
from app.services.repository_search_service import RepositorySearchService
from app.services.repository_ranking_service import RepositoryRankingService


# -----------------------------------------
# Setup
# -----------------------------------------

load_dotenv()

token = os.getenv("GITHUB_TOKEN")

github = GithubService(token)

owner = "SanjayKParida"
repo = "car-rental-app"


# -----------------------------------------
# Services
# -----------------------------------------

search = RepositorySearchService()
ranking = RepositoryRankingService()
signal_service = IssueSignalService()


# -----------------------------------------
# Authentication
# -----------------------------------------

user = github.authenticate()

print("Authenticated as:", user["login"])


# -----------------------------------------
# Get repository source files
# -----------------------------------------

files = github.get_repository_source_files(
    owner,
    repo
)

print(f"Total files: {len(files)}")


# -----------------------------------------
# Get GitHub issue
# -----------------------------------------

issues = github.get_issues(
    owner,
    repo
)

issue = issues[0]

print("\n========== ISSUE ==========")
print("TITLE:", issue["title"])
print("BODY:", issue["body"])


# -----------------------------------------
# Extract signals
# -----------------------------------------

signals = signal_service.extract_signals(
    issue["title"],
    issue["body"]
)

print("\n========== SIGNALS ==========")

for signal in signals:
    print(
        signal["term"],
        "(",
        signal["type"],
        ")"
    )


# -----------------------------------------
# DEBUG: Loading search
# -----------------------------------------

print("\n========== LOADING SEARCH ==========")

loading_results = search.search_content(
    files,
    "loading"
)

print("\n========== CAR BLOC RAW CONTENT ==========")

for file in files:
    if file["path"] == "lib/presentation/bloc/car_bloc.dart":
        print(file["content"])

for result in loading_results:
    print(
        result["file"]["path"],
        "->",
        f"line {result['line']}:",
        result["text"],
        "->",
        result["match_type"]
    )


# -----------------------------------------
# Rank each signal
# -----------------------------------------

rankings = []


for signal in signals:

    term = signal["term"]

    print(
        f"\n========== SIGNAL: "
        f"{term} ({signal['type']}) =========="
    )


    # -------------------------------------
    # Path search
    # -------------------------------------

    path_results = search.search(
        files,
        term
    )


    print("\nPath matches:")

    if path_results:
        for file in path_results:
            print(file["path"])
    else:
        print("None")


    # -------------------------------------
    # Content search
    # -------------------------------------

    content_results = search.search_content(
        files,
        term
    )


    print("\nContent matches:")

    if content_results:
        for result in content_results:
            print(
                result["file"]["path"],
                "->",
                f"line {result['line']}:",
                result["text"],
                "->",
                result["match_type"]
            )
    else:
        print("None")


    # -------------------------------------
    # Rank this signal
    # -------------------------------------

    scores = ranking.rank(
        signal,
        path_results,
        content_results
    )

    rankings.append(scores)


# -----------------------------------------
# Aggregate all signal rankings
# -----------------------------------------

final_scores = ranking.aggregate(
    rankings
)


# -----------------------------------------
# Sort by total score
# -----------------------------------------

sorted_scores = sorted(
    final_scores.items(),
    key=lambda item: item[1]["total_score"],
    reverse=True
)


# -----------------------------------------
# Final ranked files
# -----------------------------------------

print("\n========== RANKED FILES ==========")

for rank, (sha, score) in enumerate(
    sorted_scores,
    start=1
):
    print(
        rank,
        score["path"],
        "->",
        "total:",
        round(score["total_score"], 2),
        "path:",
        round(score["path_score"], 2),
        "content:",
        round(score["content_score"], 2)
    )