import re

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_github_service
from app.errors import InvalidRepositoryUrl
from app.schemas import Issue, Repository

repositories_router = APIRouter(tags=["repositories"])

# Accepts what a developer actually pastes: a browser URL, a clone
# URL, or a bare owner/repo.
REPOSITORY_PATTERN = re.compile(
    r"^(?:https?://(?:www\.)?github\.com/|git@github\.com:)?"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)"
    r"(?:\.git)?/?$"
)


def parse_repository_url(url):
    candidate = (url or "").strip()

    if not candidate:
        raise InvalidRepositoryUrl(
            "Enter a GitHub repository URL"
        )

    match = REPOSITORY_PATTERN.match(candidate)

    if not match:
        raise InvalidRepositoryUrl(
            "Expected a GitHub repository URL such as "
            "https://github.com/owner/repo"
        )

    return match.group("owner"), match.group("repo")


@repositories_router.get("", response_model=Repository)
def resolve_repository(
    url: str = Query(
        ...,
        description="GitHub URL or owner/repo",
    ),
    github=Depends(get_github_service),
):
    """Validate a pasted repository reference and return its metadata."""

    owner, repo = parse_repository_url(url)

    data = github.get_repository(owner, repo)

    return Repository(
        owner=data["owner"]["login"],
        repo=data["name"],
        full_name=data["full_name"],
        description=data.get("description"),
        default_branch=data.get("default_branch"),
        private=data.get("private", False),
        html_url=data.get("html_url"),
    )


@repositories_router.get(
    "/{owner}/{repo}/issues",
    response_model=list[Issue],
)
def list_issues(
    owner: str,
    repo: str,
    search: str | None = Query(
        None,
        description="Filter by issue number, title or body",
    ),
    github=Depends(get_github_service),
):
    issues = github.get_issues(owner, repo)

    results = []

    for issue in issues:

        # The issues endpoint also returns pull requests. They are not
        # what the user is choosing between.
        if "pull_request" in issue:
            continue

        results.append(
            Issue(
                number=issue["number"],
                title=issue.get("title") or "",
                body=issue.get("body") or "",
                state=issue.get("state") or "open",
                html_url=issue.get("html_url"),
                comments=issue.get("comments", 0),
                updated_at=issue.get("updated_at"),
            )
        )

    return _filter(results, search)


def _filter(issues, search):
    term = (search or "").strip().lower()

    if not term:
        return issues

    return [
        issue
        for issue in issues
        if term in issue.title.lower()
        or term in issue.body.lower()
        or term in f"#{issue.number}"
    ]
