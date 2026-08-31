"""
Which repositories a PatchPilot session may read or write.

When a GitHub App is not configured, local evaluation keeps using
GITHUB_TOKEN. Once the App is configured, that token is isolated to
the demo repository for reads and is never used as a write fallback
for arbitrary visitors or user repositories.
"""

from app.errors import (
    GithubPermissionDenied,
    NotAuthenticated,
    NotAuthorized,
    AnalysisNotFound,
)
from app.infrastructure.github_write_client import GithubWriteClient
from app.services.github_service import GithubService


class RepositoryAccess:
    def __init__(self, store, settings, github_app=None):
        self.store = store
        self.settings = settings
        self.github_app = github_app

    @property
    def app_configured(self):
        return self.settings.github_app_configured

    def is_demo(self, owner, repo):
        return self.settings.is_demo_repo(owner, repo)

    def demo_repository(self):
        return {
            "owner": self.settings.demo_owner,
            "repo": self.settings.demo_repo,
            "full_name": self.settings.demo_full_name,
            "description": self.settings.demo_description,
            "private": False,
            "demo": True,
            "can_read": True,
            "can_write": False,
        }

    def assert_can_analyze(self, owner, repo, session):
        if self.is_demo(owner, repo):
            return

        if not self.app_configured:
            return

        if session is None:
            raise NotAuthenticated(
                "Connect GitHub to analyze your repositories"
            )

        granted = self.store.find_repository(session.user_id, owner, repo)
        if granted is None or not granted.can_read:
            raise NotAuthorized(
                f"{owner}/{repo} is not authorized for this PatchPilot account"
            )

    def assert_can_read_analysis(self, record, session):
        owner, repo = _repo(record)
        user_id = record.get("user_id")

        if user_id:
            if session is None or session.user_id != user_id:
                raise AnalysisNotFound(f"No analysis with id {record.get('id')}")
            return

        if self.is_demo(owner, repo):
            return

        if not self.app_configured:
            return

        raise AnalysisNotFound(f"No analysis with id {record.get('id')}")

    def assert_can_deliver(self, record, session):
        self.assert_can_read_analysis(record, session)
        owner, repo = _repo(record)

        stored_owner = (record.get("repository") or {}).get("owner")
        stored_repo = (record.get("repository") or {}).get("repo")
        if stored_owner != owner or stored_repo != repo:
            raise NotAuthorized(
                "Delivery target does not match the stored analysis repository"
            )

        if not self.app_configured:
            return

        if self.is_demo(owner, repo):
            if session is None:
                raise GithubPermissionDenied(
                    "Creating a draft PR for the demo repository requires "
                    "a GitHub account that can write to it. Analysis, "
                    "diagnosis, and patch review do not."
                )
            granted = self.store.find_repository(session.user_id, owner, repo)
            if granted is None or not granted.can_write:
                raise GithubPermissionDenied(
                    "This GitHub account cannot create branches or pull "
                    f"requests on {owner}/{repo}"
                )
            return

        if session is None:
            raise NotAuthenticated("Connect GitHub to open a draft pull request")

        granted = self.store.find_repository(session.user_id, owner, repo)
        if granted is None:
            raise NotAuthorized(
                f"{owner}/{repo} is not authorized for this PatchPilot account"
            )
        if not granted.can_write:
            raise GithubPermissionDenied(
                "This GitHub account cannot create branches or pull "
                f"requests on {owner}/{repo}"
            )

    def github_token_for(self, owner, repo, session, *, write=False):
        """
        Token for GithubService / GithubWriteClient.

        Never returns a GitHub credential to an HTTP client. Demo
        writes never fall back to GITHUB_TOKEN for anonymous visitors.
        """

        if write:
            return self._write_token(owner, repo, session)
        return self._read_token(owner, repo, session)

    def github_service_for(self, owner, repo, session, *, write=False):
        return GithubService(
            self.github_token_for(owner, repo, session, write=write)
        )

    def github_writer_for(self, owner, repo, session):
        return GithubWriteClient(
            self.github_token_for(owner, repo, session, write=True)
        )

    def _read_token(self, owner, repo, session):
        if self.is_demo(owner, repo):
            if self.settings.github_token:
                return self.settings.github_token
            if session is not None:
                return self._user_or_installation_token(session, owner, repo)
            raise NotAuthorized(
                "The demo repository is not configured for anonymous reads"
            )

        if not self.app_configured:
            if not self.settings.github_token:
                raise NotAuthorized("GITHUB_TOKEN is not configured")
            return self.settings.github_token

        if session is None:
            raise NotAuthenticated(
                "Connect GitHub to analyze your repositories"
            )
        return self._user_or_installation_token(session, owner, repo)

    def _write_token(self, owner, repo, session):
        if self.is_demo(owner, repo):
            if not self.app_configured:
                if not self.settings.github_token:
                    raise GithubPermissionDenied(
                        "GITHUB_TOKEN is not configured"
                    )
                return self.settings.github_token
            if session is None:
                raise GithubPermissionDenied(
                    "Creating a draft PR for the demo repository requires "
                    "a GitHub account that can write to it"
                )
            granted = self.store.find_repository(session.user_id, owner, repo)
            if granted is None or not granted.can_write:
                raise GithubPermissionDenied(
                    "This GitHub account cannot create branches or pull "
                    f"requests on {owner}/{repo}"
                )
            return self._user_or_installation_token(session, owner, repo)

        if not self.app_configured:
            if not self.settings.github_token:
                raise GithubPermissionDenied("GITHUB_TOKEN is not configured")
            return self.settings.github_token

        if session is None:
            raise NotAuthenticated("Connect GitHub to open a draft pull request")
        granted = self.store.find_repository(session.user_id, owner, repo)
        if granted is None or not granted.can_write:
            raise GithubPermissionDenied(
                "This GitHub account cannot create branches or pull "
                f"requests on {owner}/{repo}"
            )
        return self._user_or_installation_token(session, owner, repo)

    def _user_or_installation_token(self, session, owner, repo):
        user = self.store.get_user(session.user_id)
        if user is None:
            raise NotAuthenticated("Connect GitHub to continue")

        granted = self.store.find_repository(session.user_id, owner, repo)
        if (
            granted
            and granted.installation_id
            and self.github_app is not None
            and self.settings.can_mint_installation_tokens
        ):
            return self.github_app.create_installation_token(
                granted.installation_id
            )

        if user.github_access_token:
            return user.github_access_token

        raise GithubPermissionDenied(
            "No GitHub credentials are stored for this account"
        )


def _repo(record):
    repository = record.get("repository") or {}
    return repository.get("owner") or "", repository.get("repo") or ""
