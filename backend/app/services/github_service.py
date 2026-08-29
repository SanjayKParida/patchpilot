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

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
        page: int = 1,
        since: str | None = None,
    ):
        """
        Issues for a repository.

        Defaults match GitHub's own: open issues only, newest first.
        Candidate discovery needs `state="closed"`, since an issue with
        a fix is by definition closed.
        """
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/issues"
            f"?state={state}&per_page={per_page}&page={page}"
        )

        if since:
            url += f"&since={since}"

        return self._request(url)

    def get_issue_timeline(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        per_page: int = 100,
    ):
        """
        Timeline events for an issue.

        This is where GitHub records what actually closed an issue:
        `closed` events carry a `commit_id`, and `referenced` events
        link commits that mention it. Commit messages alone are a
        weaker signal — the timeline is the repository's own account
        of the link.
        """
        return self._request(
            f"https://api.github.com/repos/{owner}/{repo}"
            f"/issues/{issue_number}/timeline?per_page={per_page}"
        )
    
    def get_repository_files(self, owner: str, repo: str):
        return self._request(f"https://api.github.com/repos/{owner}/{repo}/contents")

    def get_issue(self, owner: str, repo: str, issue_number: int):
        return self._request(f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}")

    def get_commit(self, owner: str, repo: str, branch: str):
        return self._request(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
        )   

    def compare_commits(
        self,
        owner: str,
        repo: str,
        base: str,
        head: str,
    ):
        """
        Diff between two commits.

        `files` in the response is the changed-file list, each entry
        carrying `filename`, `status`, and `previous_filename` for
        renames.
        """
        return self._request(
            f"https://api.github.com/repos/{owner}/{repo}"
            f"/compare/{base}...{head}"
        )

    def get_repository_source_files(
        self,
        owner: str,
        repo: str,
        ref: str | None = None,
    ):
        """
        Source files for a repository at `ref`.

        `ref` may be a commit SHA, branch or tag. Omit it for the
        default branch, which is the behaviour every existing caller
        relies on.
        """
        files = self.get_repository_tree(owner, repo, ref=ref)

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

    def get_repository_tree(
        self,
        owner: str,
        repo: str,
        ref: str | None = None,
    ):
            """
            File tree for a repository at `ref` (default branch when
            omitted).

            The tree is resolved from the commit `ref` points at, so
            a caller asking for an old commit gets that commit's
            files -- not the current ones.
            """
            files = []

            if ref is None:
                repository = self.get_repository(owner, repo)
                ref = repository["default_branch"]

            commit = self.get_commit(owner, repo, ref)

            tree_sha = commit["commit"]["tree"]["sha"]

            tree = self._request(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1"
            )

            for item in tree["tree"]:
                if item["type"] == "blob":
                    files.append(item)

            return files

