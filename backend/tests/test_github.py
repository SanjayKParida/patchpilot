import os
from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.repository_search_service import RepositorySearchService
from app.utils.text_normalizer import TextNormalizer


load_dotenv()

token = os.getenv("GITHUB_TOKEN")

github = GithubService(token)
search = RepositorySearchService()
normalizer = TextNormalizer()

owner = "SanjayKParida"
repo = "car-rental-app"


# -----------------------------------------
# Get repository files
# -----------------------------------------

files = github.get_repository_source_files(
    owner,
    repo
)

print(f"Total files: {len(files)}")


# -----------------------------------------
# Test tokenization
# -----------------------------------------

print("\n========== TOKENIZATION ==========")

query = "FirebaseCar"

print(
    query,
    "->",
    normalizer.tokenize(query)
)


# -----------------------------------------
# Test content search
# -----------------------------------------

print("\n========== CONTENT SEARCH ==========")

results = search.search_content(
    files,
    query
)

print(f"Query: {query}")
print(f"Matches: {len(results)}")


for result in results:
    print(
        result["file"]["path"],
        "->",
        f"line {result['line']}:",
        result["text"],
        "->",
        result["match_type"]
    )