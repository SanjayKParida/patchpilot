"""
Runtime configuration.

GitHub App credentials and the demo repository identity live here so
neither is scattered through the product. A missing GitHub App keeps
local evaluation on `GITHUB_TOKEN`; it is not a write fallback once
the App is configured.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

SESSION_COOKIE_NAME = "patchpilot_session"


def _env(name, default=None):
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return value.strip()


def _bool_env(name, default=False):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _private_key(raw):
    if not raw:
        return None
    return raw.replace("\\n", "\n").strip()


@dataclass(frozen=True)
class Settings:
    github_token: str | None
    github_app_id: str | None
    github_app_client_id: str | None
    github_app_client_secret: str | None
    github_app_private_key: str | None
    github_app_slug: str | None
    github_app_redirect_uri: str
    session_secret: str
    session_ttl_seconds: int
    cookie_secure: bool
    cookie_samesite: str
    demo_owner: str
    demo_repo: str
    demo_description: str
    frontend_origin: str
    cors_origins: str | None

    @property
    def github_app_configured(self):
        return bool(self.github_app_client_id)

    @property
    def can_mint_installation_tokens(self):
        return bool(self.github_app_id and self.github_app_private_key)

    @property
    def demo_full_name(self):
        return f"{self.demo_owner}/{self.demo_repo}"

    def is_demo_repo(self, owner, repo):
        return (
            (owner or "").lower() == self.demo_owner.lower()
            and (repo or "").lower() == self.demo_repo.lower()
        )


@lru_cache(maxsize=1)
def get_settings():
    return Settings(
        github_token=_env("GITHUB_TOKEN"),
        github_app_id=_env("GITHUB_APP_ID"),
        github_app_client_id=_env("GITHUB_APP_CLIENT_ID"),
        github_app_client_secret=_env("GITHUB_APP_CLIENT_SECRET"),
        github_app_private_key=_private_key(_env("GITHUB_APP_PRIVATE_KEY")),
        github_app_slug=_env("GITHUB_APP_SLUG"),
        github_app_redirect_uri=_env(
            "GITHUB_APP_REDIRECT_URI",
            "http://localhost:8000/api/auth/github/callback",
        ),
        session_secret=_env("SESSION_SECRET", "dev-session-secret-change-me"),
        session_ttl_seconds=_int_env("SESSION_TTL_SECONDS", 12 * 60 * 60),
        cookie_secure=_bool_env("SESSION_COOKIE_SECURE", False),
        cookie_samesite=_env("SESSION_COOKIE_SAMESITE", "lax"),
        demo_owner=_env("DEMO_OWNER", "SanjayKParida"),
        demo_repo=_env("DEMO_REPO", "patchpilot-diagnosis-demo"),
        demo_description=_env(
            "DEMO_DESCRIPTION",
            "Try PatchPilot on prepared issues",
        ),
        frontend_origin=_env("FRONTEND_ORIGIN", "http://localhost:59738"),
        cors_origins=_env("CORS_ORIGINS"),
    )
