"""
In-memory PatchPilot users, sessions, OAuth state, and repo grants.

Same durability as AnalysisStore: survives a browser refresh, not an
API restart. Tokens never leave this module except to GitHub clients.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.domain.auth import (
    AuthorizedRepository,
    OAuthState,
    PatchPilotUser,
    Session,
)
from app.errors import NotAuthenticated


class AuthStore:
    def __init__(self, session_ttl_seconds=12 * 60 * 60):
        self.session_ttl_seconds = session_ttl_seconds
        self._lock = threading.Lock()
        self._users_by_id = {}
        self._users_by_github_id = {}
        self._sessions = {}
        self._oauth = {}
        self._repos_by_user = {}

    def upsert_github_user(
        self,
        *,
        github_id,
        github_login,
        avatar_url="",
        name="",
        github_access_token="",
        github_refresh_token="",
    ):
        with self._lock:
            existing = self._users_by_github_id.get(github_id)
            if existing is None:
                user = PatchPilotUser(
                    id=uuid.uuid4().hex,
                    github_id=github_id,
                    github_login=github_login,
                    avatar_url=avatar_url or "",
                    name=name or "",
                    github_access_token=github_access_token or "",
                    github_refresh_token=github_refresh_token or "",
                )
                self._users_by_id[user.id] = user
                self._users_by_github_id[github_id] = user
                self._repos_by_user.setdefault(user.id, [])
                return user

            existing.github_login = github_login
            existing.avatar_url = avatar_url or existing.avatar_url
            existing.name = name or existing.name
            if github_access_token:
                existing.github_access_token = github_access_token
            if github_refresh_token:
                existing.github_refresh_token = github_refresh_token
            return existing

    def get_user(self, user_id):
        with self._lock:
            return self._users_by_id.get(user_id)

    def create_session(self, user_id):
        now = _now()
        session = Session(
            id=uuid.uuid4().hex,
            user_id=user_id,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.session_ttl_seconds)).isoformat(),
        )
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get_valid_session(self, session_id):
        if not session_id:
            return None

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if _parse(session.expires_at) <= _now():
                self._sessions.pop(session_id, None)
                return None
            return session

    def require_session(self, session_id):
        session = self.get_valid_session(session_id)
        if session is None:
            raise NotAuthenticated("Connect GitHub to continue")
        return session

    def delete_session(self, session_id):
        with self._lock:
            self._sessions.pop(session_id, None)

    def put_oauth_state(
        self,
        *,
        code_verifier,
        return_to,
        user_id=None,
        ttl_seconds=600,
        resume_id=None,
    ):
        now = _now()
        record = OAuthState(
            state=uuid.uuid4().hex,
            code_verifier=code_verifier,
            return_to=return_to,
            expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
            user_id=user_id,
            resume_id=resume_id,
        )
        with self._lock:
            self._oauth[record.state] = record
        return record

    def consume_oauth_state(self, state):
        if not state:
            return None
        with self._lock:
            record = self._oauth.pop(state, None)
        if record is None:
            return None
        if _parse(record.expires_at) <= _now():
            return None
        return record

    def replace_repositories(self, user_id, repositories):
        with self._lock:
            self._repos_by_user[user_id] = list(repositories)

    def list_repositories(self, user_id):
        with self._lock:
            return list(self._repos_by_user.get(user_id, []))

    def find_repository(self, user_id, owner, repo):
        owner_key = (owner or "").lower()
        repo_key = (repo or "").lower()
        for item in self.list_repositories(user_id):
            if item.owner.lower() == owner_key and item.repo.lower() == repo_key:
                return item
        return None


def _now():
    return datetime.now(timezone.utc)


def _parse(value):
    return datetime.fromisoformat(value)
