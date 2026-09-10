"""
GitHub App login, session, and authorized-repository listing.

Does not fetch repository source or open pull requests.
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.domain.auth import (
    AuthorizedRepository,
    permissions_allow_read,
    permissions_allow_write,
)
from app.errors import (
    AnalysisStoreUnavailable,
    AuthorizationFailed,
    InvalidOAuthState,
    NotAuthenticated,
)
from app.infrastructure.github_app_client import pkce_pair


class AuthService:
    def __init__(self, store, github_app, settings, resume_store=None):
        self.store = store
        self.github_app = github_app
        self.settings = settings
        self.resume_store = resume_store

    def current_user(self, session_id):
        session = self.store.get_valid_session(session_id)
        if session is None:
            return None
        return self.store.get_user(session.user_id)

    def start_login(
        self,
        return_to,
        user_id=None,
        *,
        analysis_id=None,
        stage=None,
        repair_path=None,
    ):
        if not self.settings.github_app_configured:
            raise AuthorizationFailed(
                "GitHub App is not configured. Set GITHUB_APP_CLIENT_ID."
            )

        verifier, challenge = pkce_pair()
        safe_return = self._safe_return_to(return_to)
        resume_id = self._save_resume(
            analysis_id=analysis_id,
            stage=stage,
            repair_path=repair_path,
            return_to=safe_return,
        )
        record = self.store.put_oauth_state(
            code_verifier=verifier,
            return_to=safe_return,
            user_id=user_id,
            resume_id=resume_id,
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
        resume = self._consume_resume(record.resume_id)
        return session, user, self._login_return_to(record, resume)

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

    def _save_resume(self, *, analysis_id, stage, repair_path, return_to):
        if self.resume_store is None:
            return None

        analysis_id = (analysis_id or "").strip() or None
        stage = (stage or "").strip() or None
        path = (repair_path or "").strip() or _path_and_query(return_to)
        if path in ("", "/"):
            path = None

        if not analysis_id and not stage and not path:
            return None

        record = self.resume_store.create(
            analysis_id=analysis_id,
            repair_path=path,
            stage=stage,
        )
        return record["id"]

    def _consume_resume(self, resume_id):
        if not resume_id or self.resume_store is None:
            return None
        try:
            return self.resume_store.consume(resume_id)
        except AnalysisStoreUnavailable:
            return None

    def _login_return_to(self, record, resume):
        current = record.return_to
        parsed = urlparse(current or "")
        if parsed.path in ("", "/"):
            path = (resume or {}).get("repair_path") if resume else None
            if path:
                current = self._safe_return_to(path)

        analysis_id = (resume or {}).get("analysis_id") if resume else None
        if analysis_id:
            current = _with_query(
                current or self.settings.frontend_origin,
                "analysis_id",
                analysis_id,
            )
        return current or self.settings.frontend_origin

    def _safe_return_to(self, return_to):
        candidate = (return_to or "").strip() or self.settings.frontend_origin
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https"):
            if candidate.startswith("/"):
                origin = self.settings.frontend_origin.rstrip("/")
                candidate = f"{origin}{candidate}"
                parsed = urlparse(candidate)
            else:
                return self.settings.frontend_origin
        if not parsed.netloc:
            return self.settings.frontend_origin
        if not _host_allowed(parsed.hostname, self.settings):
            return self.settings.frontend_origin
        cleaned = urlunparse(parsed._replace(fragment=""))
        return _strip_oauth_query(cleaned)


def _with_query(url, key, value):
    parsed = urlparse(url)
    kept = [
        (name, item)
        for name, item in parse_qsl(parsed.query, keep_blank_values=True)
        if name != key
    ]
    kept.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(kept)))


def _path_and_query(url):
    parsed = urlparse(url or "")
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path or "/"


def _strip_oauth_query(url):
    parsed = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in ("connected", "auth_error")
    ]
    return urlunparse(parsed._replace(query=urlencode(kept), fragment=""))


def _host_allowed(hostname, settings):
    host = (hostname or "").lower()
    if host in ("localhost", "127.0.0.1"):
        return True

    frontend_host = urlparse(settings.frontend_origin).hostname
    if host and frontend_host and host == frontend_host.lower():
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
