import re

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    get_auth_service,
    get_github_service,
    get_optional_session,
    get_repository_access,
    get_repository_snapshot_store,
)
from app.errors import InvalidRepositoryUrl, NotAuthenticated
from app.schemas import Issue, Repository, RepositorySnapshot
from app.services.repository_snapshot import prepare_repository_snapshot

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


@repositories_router.get("/demo", response_model=Repository)
def get_demo_repository(access=Depends(get_repository_access)):
    """Public demo repository. Available without GitHub login."""

    demo = access.demo_repository()
    return Repository(
        owner=demo["owner"],
        repo=demo["repo"],
        full_name=demo["full_name"],
        description=demo["description"],
        private=False,
        demo=True,
        can_read=True,
        can_write=False,
    )


@repositories_router.get("/authorized", response_model=list[Repository])
def list_authorized_repositories(
    session=Depends(get_optional_session),
    auth=Depends(get_auth_service),
):
    """Repositories the current GitHub App installation can access."""

    if session is None:
        raise NotAuthenticated("Connect GitHub to see your repositories")

    return _authorized_payload(auth.authorized_repositories(session.id))


@repositories_router.post("/authorized/refresh", response_model=list[Repository])
def refresh_authorized_repositories(
    session=Depends(get_optional_session),
    auth=Depends(get_auth_service),
):
    """Re-read GitHub App installation grants for the current session."""

    if session is None:
        raise NotAuthenticated("Connect GitHub to see your repositories")

    return _authorized_payload(
        auth.refresh_authorized_repositories(session.id)
    )


def _authorized_payload(items):
    return [
        Repository(
            owner=item.owner,
            repo=item.repo,
            full_name=item.full_name,
            description=item.description or None,
            default_branch=item.default_branch,
            private=item.private,
            html_url=item.html_url,
            demo=False,
            can_read=item.can_read,
            can_write=item.can_write,
            access=item.access,
            github_repo_id=item.github_repo_id,
        )
        for item in items
    ]


@repositories_router.get("", response_model=Repository)
def resolve_repository(
    url: str = Query(
        ...,
        description="GitHub URL or owner/repo",
    ),
    github=Depends(get_github_service),
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
):
    """Validate a pasted repository reference and return its metadata."""

    owner, repo = parse_repository_url(url)
    access.assert_can_analyze(owner, repo, session)

    github_for_repo = github
    if access.app_configured:
        github_for_repo = access.github_service_for(
            owner,
            repo,
            session,
            write=False,
        )

    data = github_for_repo.get_repository(owner, repo)

    granted = None
    if session is not None:
        granted = access.store.find_repository(session.user_id, owner, repo)

    return Repository(
        owner=data["owner"]["login"],
        repo=data["name"],
        full_name=data["full_name"],
        description=data.get("description"),
        default_branch=data.get("default_branch"),
        private=data.get("private", False),
        html_url=data.get("html_url"),
        demo=access.is_demo(owner, repo),
        can_read=True if granted is None else granted.can_read,
        can_write=False if granted is None else granted.can_write,
        access=None if granted is None else granted.access,
        github_repo_id=granted.github_repo_id if granted else data.get("id"),
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
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
):
    access.assert_can_analyze(owner, repo, session)

    github_for_repo = _github_for_repo(github, access, owner, repo, session)

    issues = github_for_repo.get_issues(owner, repo)

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


def _github_for_repo(github, access, owner, repo, session):
    if access.app_configured:
        return access.github_service_for(
            owner,
            repo,
            session,
            write=False,
        )
    return github


def _snapshot_payload(commit_sha, status, files=None, progress=None):
    progress = progress or {}
    downloaded = progress.get("downloaded", 0)
    total = progress.get("total", 0)
    percent = progress.get("percent", 100 if status == "ready" else 0)
    file_count = len(files or [])
    if status == "ready" and not total:
        total = file_count
        downloaded = file_count
        percent = 100
    return RepositorySnapshot(
        commit_sha=commit_sha,
        status=status,
        file_count=file_count,
        progress_percent=percent,
        files_downloaded=downloaded,
        files_total=total,
    )


@repositories_router.post(
    "/{owner}/{repo}/snapshot",
    response_model=RepositorySnapshot,
)
def create_repository_snapshot(
    owner: str,
    repo: str,
    ref: str | None = Query(
        None,
        description="Commit SHA or ref. Omit for default-branch HEAD.",
    ),
    github=Depends(get_github_service),
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
    snapshots=Depends(get_repository_snapshot_store),
):
    """
    Download and cache the tracked tree at one commit.

    Returns metadata only. A cached SHA is reused. An in-flight
    download for the same SHA is not started again.
    """

    access.assert_can_analyze(owner, repo, session)
    github_for_repo = _github_for_repo(github, access, owner, repo, session)
    commit_sha, files, _status = prepare_repository_snapshot(
        github_for_repo,
        snapshots,
        owner,
        repo,
        ref=ref,
        wait=False,
    )
    return _snapshot_payload(commit_sha, "ready", files)


@repositories_router.get(
    "/{owner}/{repo}/snapshot",
    response_model=RepositorySnapshot,
)
def get_repository_snapshot(
    owner: str,
    repo: str,
    ref: str | None = Query(
        None,
        description="Commit SHA or ref. Omit for default-branch HEAD.",
    ),
    github=Depends(get_github_service),
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
    snapshots=Depends(get_repository_snapshot_store),
):
    """Status of a cached snapshot. Never returns file contents."""

    access.assert_can_analyze(owner, repo, session)
    github_for_repo = _github_for_repo(github, access, owner, repo, session)
    commit_sha = snapshots.active_sha(owner, repo)
    if not commit_sha:
        commit_sha = github_for_repo.resolve_commit(owner, repo, ref)
    elif ref:
        commit_sha = github_for_repo.resolve_commit(owner, repo, ref)
    status, files, progress = snapshots.inspect(owner, repo, commit_sha)
    return _snapshot_payload(commit_sha, status, files, progress)


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
