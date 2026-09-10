"""
PatchPilot identity and GitHub authorization types.

No HTTP, no GitHub client. Tokens stay on the server-side records
and are stripped before anything is serialised to a client.
"""

from dataclasses import dataclass


@dataclass
class PatchPilotUser:
    id: str
    github_id: int
    github_login: str
    avatar_url: str = ""
    name: str = ""
    github_access_token: str = ""
    github_refresh_token: str = ""

    def public_dict(self):
        return {
            "id": self.id,
            "github_id": self.github_id,
            "github_login": self.github_login,
            "avatar_url": self.avatar_url,
            "name": self.name,
        }


@dataclass
class Session:
    id: str
    user_id: str
    created_at: str
    expires_at: str


@dataclass
class AuthorizedRepository:
    owner: str
    repo: str
    full_name: str
    github_repo_id: int | None = None
    installation_id: int | None = None
    private: bool = False
    description: str = ""
    html_url: str | None = None
    default_branch: str | None = None
    can_read: bool = True
    can_write: bool = False

    @property
    def access(self):
        if self.can_write:
            return "write"
        if self.can_read:
            return "read"
        return "none"

    def public_dict(self):
        return {
            "owner": self.owner,
            "repo": self.repo,
            "full_name": self.full_name,
            "github_repo_id": self.github_repo_id,
            "private": self.private,
            "description": self.description or None,
            "html_url": self.html_url,
            "default_branch": self.default_branch,
            "can_read": self.can_read,
            "can_write": self.can_write,
            "access": self.access,
        }


@dataclass
class OAuthState:
    state: str
    code_verifier: str
    return_to: str
    expires_at: str
    user_id: str | None = None
    resume_id: str | None = None


def permissions_allow_write(permissions):
    permissions = permissions or {}
    return bool(
        permissions.get("push")
        or permissions.get("admin")
        or permissions.get("maintain")
        or permissions.get("contents") in ("write", "admin")
        or permissions.get("pull_requests") in ("write", "admin")
    )


def permissions_allow_read(permissions):
    permissions = permissions or {}
    if permissions_allow_write(permissions):
        return True
    return bool(
        permissions.get("pull")
        or permissions.get("triage")
        or permissions.get("contents") in ("read", "write", "admin")
        or not permissions
    )
