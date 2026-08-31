"""
GitHub write API for delivery.

Read-only analysis traffic stays on GithubService (GET only).
This client is the only place that POSTs refs, commits, and PRs.
"""

import logging

import httpx

from app.errors import (
    GitRefConflict,
    GithubPermissionDenied,
    RepositoryNotFound,
    UpstreamUnavailable,
)

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"


class GithubWriteClient:
    TIMEOUT_SECONDS = 30.0

    def __init__(self, github_token: str, client=None):
        self.github_token = github_token
        self._client = client

    def create_blob(self, owner: str, repo: str, content: str) -> str:
        payload = self._send(
            "POST",
            f"{API_ROOT}/repos/{owner}/{repo}/git/blobs",
            json={"content": content, "encoding": "utf-8"},
        )
        return payload["sha"]

    def create_tree(self, owner: str, repo: str, base_tree: str, entries):
        payload = self._send(
            "POST",
            f"{API_ROOT}/repos/{owner}/{repo}/git/trees",
            json={
                "base_tree": base_tree,
                "tree": list(entries),
            },
        )
        return payload["sha"]

    def create_commit(
        self,
        owner: str,
        repo: str,
        message: str,
        tree: str,
        parents,
    ) -> str:
        payload = self._send(
            "POST",
            f"{API_ROOT}/repos/{owner}/{repo}/git/commits",
            json={
                "message": message,
                "tree": tree,
                "parents": list(parents),
            },
        )
        return payload["sha"]

    def create_ref(self, owner: str, repo: str, ref: str, sha: str):
        if not ref.startswith("refs/heads/"):
            raise UpstreamUnavailable(
                f"Refusals: only refs/heads/* may be created, not {ref!r}"
            )

        self._send(
            "POST",
            f"{API_ROOT}/repos/{owner}/{repo}/git/refs",
            json={"ref": ref, "sha": sha},
        )

    def get_ref(self, owner: str, repo: str, ref: str):
        """
        SHA of `ref`, or None if it does not exist.

        `ref` is `refs/heads/...` or `heads/...`.
        """

        qualified = ref
        if qualified.startswith("refs/"):
            qualified = qualified[len("refs/"):]

        payload = self._send(
            "GET",
            f"{API_ROOT}/repos/{owner}/{repo}/git/ref/{qualified}",
            missing_ok=True,
        )

        if payload is None:
            return None

        obj = payload.get("object") or {}
        return obj.get("sha")

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = True,
    ):
        payload = self._send(
            "POST",
            f"{API_ROOT}/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
            },
        )
        return {
            "number": payload.get("number"),
            "html_url": payload.get("html_url"),
            "draft": payload.get("draft", draft),
        }

    def find_pull_request(self, owner: str, repo: str, head_branch: str):
        payload = self._send(
            "GET",
            (
                f"{API_ROOT}/repos/{owner}/{repo}/pulls"
                f"?head={owner}:{head_branch}&state=all"
            ),
        )

        if not payload:
            return None

        item = payload[0]
        return {
            "number": item.get("number"),
            "html_url": item.get("html_url"),
            "draft": item.get("draft", True),
        }

    def _send(self, method: str, url: str, json=None, *, missing_ok=False):
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            if self._client is not None:
                response = self._client.request(
                    method,
                    url,
                    json=json,
                    headers=headers,
                    timeout=self.TIMEOUT_SECONDS,
                )
            else:
                response = httpx.request(
                    method,
                    url,
                    json=json,
                    headers=headers,
                    timeout=self.TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as e:
            raise UpstreamUnavailable(
                f"Could not reach GitHub: {e}"
            ) from e

        status = response.status_code

        if status == 404:
            if missing_ok:
                return None
            raise RepositoryNotFound(
                f"GitHub returned 404 for {url}"
            )

        if status in (401, 403):
            logger.warning(
                "GitHub %s for %s: %s",
                status,
                url,
                response.text[:500],
            )
            raise GithubPermissionDenied(
                "The GitHub token cannot create branches, commits, "
                "or pull requests for this repository. Grant Contents "
                "and Pull requests write access (classic `repo`, or "
                "`public_repo` for public repositories)."
            )

        if status == 422:
            body = response.text[:500]
            logger.warning("GitHub 422 for %s: %s", url, body)
            if "already exists" in body.lower():
                raise GitRefConflict(
                    f"GitHub ref already exists for {url}"
                )
            raise UpstreamUnavailable(
                f"GitHub returned 422 for {url}"
            )

        if status >= 400:
            logger.warning(
                "GitHub %s for %s: %s",
                status,
                url,
                response.text[:500],
            )
            raise UpstreamUnavailable(
                f"GitHub returned {status} for {url}"
            )

        if status == 204 or not response.content:
            return None

        return response.json()
