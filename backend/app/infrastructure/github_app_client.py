"""
GitHub App OAuth and installation access.

Read-only repository traffic still goes through GithubService.
Writes still go through GithubWriteClient. This client only talks to
App/OAuth endpoints and mints installation tokens.
"""

import hashlib
import logging
import time
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx

from app.errors import AuthorizationFailed, UpstreamUnavailable

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"
GITHUB_INSTALL_PREFIX = "https://github.com/apps"
CALLBACK_PATH = "/api/auth/github/callback"
REQUIRED_AUTHORIZE_PARAMS = (
    "client_id",
    "redirect_uri",
    "state",
    "code_challenge",
    "code_challenge_method",
)


def sanitize_oauth_authorize_url(url):
    """
    Describe an authorize URL without secrets.

    Returns hostname, path, parameter names, and whether required
    fields are present. Never includes client_id, state, PKCE
    verifier/challenge, codes, tokens, or other query values.
    """

    parsed = urlparse(url or "")
    query = parse_qs(parsed.query, keep_blank_values=True)
    names = sorted(query)
    required_present = {
        name: bool((query.get(name) or [""])[0])
        for name in REQUIRED_AUTHORIZE_PARAMS
    }
    method = (query.get("code_challenge_method") or [""])[0]
    return {
        "hostname": parsed.hostname,
        "path": parsed.path,
        "parameter_names": names,
        "required_present": required_present,
        "unexpected_parameters": sorted(
            set(names) - set(REQUIRED_AUTHORIZE_PARAMS)
        ),
        "code_challenge_method_is_s256": method == "S256",
        "uses_github_authorize_path": (
            parsed.hostname == "github.com"
            and parsed.path == "/login/oauth/authorize"
        ),
        "redirect_uri_ends_with_callback_path": (
            (query.get("redirect_uri") or [""])[0].endswith(CALLBACK_PATH)
        ),
    }


class GithubAppClient:
    TIMEOUT_SECONDS = 30.0

    def __init__(self, settings, client=None):
        self.settings = settings
        self._client = client
        self._installation_tokens = {}

    def authorization_url(self, *, state, code_challenge):
        params = {
            "client_id": self.settings.github_app_client_id,
            "redirect_uri": self.settings.github_app_redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{GITHUB_AUTHORIZE}?{urlencode(params, quote_via=quote)}"

    def installation_url(self, *, state):
        slug = self.settings.github_app_slug
        if not slug:
            return self.authorization_url(state=state, code_challenge="")
        params = {"state": state}
        return (
            f"{GITHUB_INSTALL_PREFIX}/{slug}/installations/new"
            f"?{urlencode(params)}"
        )

    def exchange_code(self, code, code_verifier):
        payload = self._form(
            GITHUB_TOKEN,
            {
                "client_id": self.settings.github_app_client_id,
                "client_secret": self.settings.github_app_client_secret,
                "code": code,
                "redirect_uri": self.settings.github_app_redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        error = payload.get("error")
        if error:
            raise AuthorizationFailed(
                payload.get("error_description")
                or f"GitHub authorization failed ({error})"
            )
        token = payload.get("access_token")
        if not token:
            raise AuthorizationFailed("GitHub did not return an access token")
        return payload

    def get_authenticated_user(self, access_token):
        return self._json("GET", f"{GITHUB_API}/user", token=access_token)

    def list_installations(self, access_token):
        payload = self._json(
            "GET",
            f"{GITHUB_API}/user/installations?per_page=100",
            token=access_token,
        )
        return payload.get("installations") or []

    def list_installation_repositories(self, access_token, installation_id):
        payload = self._json(
            "GET",
            (
                f"{GITHUB_API}/user/installations/{installation_id}"
                "/repositories?per_page=100"
            ),
            token=access_token,
        )
        return payload.get("repositories") or []

    def create_installation_token(self, installation_id):
        cached = self._installation_tokens.get(installation_id)
        now = time.time()
        if cached and cached["expires_at"] - 60 > now:
            return cached["token"]

        jwt_token = self._app_jwt()
        payload = self._json(
            "POST",
            f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
            token=jwt_token,
        )
        token = payload.get("token")
        if not token:
            raise UpstreamUnavailable(
                "GitHub did not return an installation access token"
            )
        expires = payload.get("expires_at")
        expires_at = now + 3600
        if expires:
            try:
                from datetime import datetime

                expires_at = datetime.fromisoformat(
                    expires.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                expires_at = now + 3600

        self._installation_tokens[installation_id] = {
            "token": token,
            "expires_at": expires_at,
        }
        return token

    def _app_jwt(self):
        if not self.settings.can_mint_installation_tokens:
            raise UpstreamUnavailable(
                "GitHub App private key is not configured"
            )

        import jwt

        now = int(time.time())
        return jwt.encode(
            {
                "iat": now - 60,
                "exp": now + 540,
                "iss": self.settings.github_app_id,
            },
            self.settings.github_app_private_key,
            algorithm="RS256",
        )

    def _form(self, url, data):
        try:
            response = self._request(
                "POST",
                url,
                data=data,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as e:
            raise UpstreamUnavailable(f"Could not reach GitHub: {e}") from e

        if response.status_code >= 400:
            raise AuthorizationFailed(
                f"GitHub returned {response.status_code} exchanging the code"
            )
        return response.json()

    def _json(self, method, url, token):
        try:
            response = self._request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
        except httpx.HTTPError as e:
            raise UpstreamUnavailable(f"Could not reach GitHub: {e}") from e

        if response.status_code >= 400:
            logger.warning(
                "GitHub App %s for %s: %s",
                response.status_code,
                url,
                response.text[:500],
            )
            raise UpstreamUnavailable(
                f"GitHub returned {response.status_code} for {url}"
            )
        return response.json()

    def _request(self, method, url, **kwargs):
        headers = kwargs.pop("headers", {})
        if self._client is not None:
            return self._client.request(
                method,
                url,
                timeout=self.TIMEOUT_SECONDS,
                headers=headers,
                **kwargs,
            )
        return httpx.request(
            method,
            url,
            timeout=self.TIMEOUT_SECONDS,
            headers=headers,
            **kwargs,
        )


def pkce_pair():
    import base64
    import secrets

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
