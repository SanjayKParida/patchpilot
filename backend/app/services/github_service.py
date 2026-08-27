import base64
import logging

import httpx

from app.errors import RepositoryNotFound, UpstreamUnavailable

logger = logging.getLogger(__name__)


class GithubService:

    TIMEOUT_SECONDS = 30.0

    def __init__(self, github_token: str):
        self.github_token = github_token

    def _request(self, url: str):
        try:
            response = httpx.get(
                url,
                timeout=self.TIMEOUT_SECONDS,
                headers={
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code

            # GitHub's body explains WHY (bad credentials, rate limit,
            # SAML enforcement). It is logged rather than returned:
            # these messages reach an HTTP client, and the upstream
            # body is for the operator, not the caller.
            logger.warning(
                "GitHub %s for %s: %s",
                status,
                url,
                e.response.text[:500],
            )

            if status == 404:
                raise RepositoryNotFound(
                    f"GitHub returned 404 for {url}"
                ) from e

            raise UpstreamUnavailable(
                f"GitHub returned {status} for {url}"
            ) from e

        except httpx.HTTPError as e:
            raise UpstreamUnavailable(
                f"Could not reach GitHub: {e}"
            ) from e

    def authenticate(self):
        return self._request("https://api.github.com/user")

    def get_repository(self, owner: str, repo: str):
        return self._request(f"https://api.github.com/repos/{owner}/{repo}")

    def get_issues(self, owner: str, repo: str):
        return self._request(f"https://api.github.com/repos/{owner}/{repo}/issues")
    
    def get_repository_files(self, owner: str, repo: str):
        return self._request(f"https://api.github.com/repos/{owner}/{repo}/contents")

    def get_issue(self, owner: str, repo: str, issue_number: int):
        return self._request(f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}")

    def get_commit(self, owner: str, repo: str, branch: str):
        return self._request(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
        )   

    def get_repository_source_files(self, owner: str, repo: str):
        files = self.get_repository_tree(owner, repo)

        source_files = []

        for file in files:
            if not file["path"].endswith(
                (".dart", ".py", ".js", ".ts", ".java", ".kt")
            ):
                continue

            content = self.get_blob(
                owner,
                repo,
                file["sha"]
            )

            source_files.append({
                **file,
                "content": content
            })

        return source_files

    def get_blob(self, owner: str, repo: str, sha: str):
        blob = self._request(
            f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{sha}"
        )     
        return base64.b64decode(blob['content']).decode('utf-8')

    def get_repository_tree(self, owner: str, repo: str):
            files = []

            repository = self.get_repository(owner, repo)
            default_branch = repository["default_branch"]

            commit = self.get_commit(owner, repo, default_branch)

            tree_sha = commit["commit"]["tree"]["sha"]

            tree = self._request(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1"
            )

            for item in tree["tree"]:
                if item["type"] == "blob":
                    files.append(item)

            return files

