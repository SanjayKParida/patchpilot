"""
GitHub App login, session, and authorized-repository listing.

Does not fetch repository source or open pull requests.
"""

from urllib.parse import urlparse

from app.domain.auth import (
    AuthorizedRepository,
    permissions_allow_read,
    permissions_allow_write,
)
from app.errors import (
    AuthorizationFailed,
    InvalidOAuthState,
    NotAuthenticated,
)
from app.infrastructure.github_app_client import pkce_pair


class AuthService:
    def __init__(self, store, github_app, settings):
        self.store = store
        self.github_app = github_app
        self.settings = settings

    def current_user(self, session_id):
        session = self.store.get_valid_session(session_id)
        if session is None:
            return None
        return self.store.get_user(session.user_id)

    def start_login(self, return_to, user_id=None):
        if not self.settings.github_app_configured:
            raise AuthorizationFailed(
                "GitHub App is not configured. Set GITHUB_APP_CLIENT_ID."
            )

        verifier, challenge = pkce_pair()
        record = self.store.put_oauth_state(
            code_verifier=verifier,
            return_to=self._safe_return_to(return_to),
            user_id=user_id,
        )
        return {
            "authorization_url": self.github_app.authorization_url(
                state=record.state,
                code_challenge=challenge,
            ),
            "installation_url": self.github_app.installation_url(
                state=record.state,
            ),
            "state": record.state,
        }

    def complete_login(self, *, code, state, installation_id=None):
        record = self.store.consume_oauth_state(state)
        if record is None:
            raise InvalidOAuthState(
                "This GitHub authorization is invalid or has expired"
            )

        tokens = self.github_app.exchange_code(code, record.code_verifier)
        access_token = tokens["access_token"]
        profile = self.github_app.get_authenticated_user(access_token)
        github_id = profile.get("id")
        login = profile.get("login")
        if not github_id or not login:
            raise AuthorizationFailed("GitHub did not return a user identity")

        user = self.store.upsert_github_user(
            github_id=int(github_id),
            github_login=login,
            avatar_url=profile.get("avatar_url") or "",
            name=profile.get("name") or "",
            github_access_token=access_token,
            github_refresh_token=tokens.get("refresh_token") or "",
        )
        self.refresh_repositories(user)
        session = self.store.create_session(user.id)
        return session, user, record.return_to

    def start_install(self, return_to, session_id):
        session = self.store.require_session(session_id)
        if not self.settings.github_app_configured:
            raise AuthorizationFailed(
                "GitHub App is not configured. Set GITHUB_APP_CLIENT_ID."
            )

        record = self.store.put_oauth_state(
            code_verifier="",
            return_to=self._safe_return_to(return_to),
            user_id=session.user_id,
        )
        return {
            "installation_url": self.github_app.installation_url(
                state=record.state,
            ),
            "state": record.state,
        }

    def complete_installation_return(self, *, session_id, state=None):
        session = self.store.require_session(session_id)
        user = self.store.get_user(session.user_id)
        if user is None:
            raise NotAuthenticated("Connect GitHub to continue")

        return_to = self.settings.frontend_origin
        if state:
            record = self.store.consume_oauth_state(state)
            if record is not None:
                if record.user_id and record.user_id != session.user_id:
                    raise InvalidOAuthState(
                        "This GitHub authorization is invalid or has expired"
                    )
                return_to = record.return_to or return_to

        self.refresh_repositories(user)
        return session, user, return_to

    def logout(self, session_id):
        self.store.delete_session(session_id)

    def authorized_repositories(self, session_id):
        session = self.store.require_session(session_id)
        user = self.store.get_user(session.user_id)
        if user is None:
            raise NotAuthenticated("Connect GitHub to continue")
        return self.store.list_repositories(user.id)

    def refresh_authorized_repositories(self, session_id):
        session = self.store.require_session(session_id)
        user = self.store.get_user(session.user_id)
        if user is None:
            raise NotAuthenticated("Connect GitHub to continue")
        return self.refresh_repositories(user)

    def refresh_repositories(self, user):
        installations = self.github_app.list_installations(
            user.github_access_token
        )
        repos = []
        seen = set()

        for installation in installations:
            installation_id = installation.get("id")
            if installation_id is None:
                continue
            for raw in self.github_app.list_installation_repositories(
                user.github_access_token,
                installation_id,
            ):
                mapped = _repository_from_github(raw, installation_id)
                key = (mapped.owner.lower(), mapped.repo.lower())
                if key in seen:
                    continue
                seen.add(key)
                repos.append(mapped)

        self.store.replace_repositories(user.id, repos)
        return repos

    def _safe_return_to(self, return_to):
        candidate = (return_to or "").strip() or self.settings.frontend_origin
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https"):
            return self.settings.frontend_origin
        if not parsed.netloc:
            return self.settings.frontend_origin
        if not _host_allowed(parsed.hostname, self.settings):
            return self.settings.frontend_origin
        return candidate


def _host_allowed(hostname, settings):
    host = (hostname or "").lower()
    if host in ("localhost", "127.0.0.1"):
        return True

    allowed = settings.cors_origins or ""
    for origin in allowed.split(","):
        origin = origin.strip()
        if not origin:
            continue
        parsed = urlparse(origin)
        if (parsed.hostname or "").lower() == host:
            return True
        if origin.lower().rstrip("/") == host:
            return True
    return False


def _repository_from_github(raw, installation_id):
    full_name = raw.get("full_name") or ""
    owner = (raw.get("owner") or {}).get("login") or ""
    name = raw.get("name") or ""
    if "/" in full_name:
        owner, name = full_name.split("/", 1)
    permissions = raw.get("permissions") or {}
    return AuthorizedRepository(
        owner=owner,
        repo=name,
        full_name=full_name or f"{owner}/{name}",
        github_repo_id=raw.get("id"),
        installation_id=int(installation_id) if installation_id else None,
        private=bool(raw.get("private")),
        description=raw.get("description") or "",
        html_url=raw.get("html_url"),
        default_branch=raw.get("default_branch"),
        can_read=permissions_allow_read(permissions),
        can_write=permissions_allow_write(permissions),
    )
