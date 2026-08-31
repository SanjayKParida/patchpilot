"""In-memory GitHub write API. Default pytest never touches the network."""

import hashlib

from app.errors import GitRefConflict, GithubPermissionDenied, UpstreamUnavailable


class FakeGithub:
    """Read-only GitHub surface used by delivery (commit + default branch)."""

    def __init__(self, default_branch="main", tree_sha="tree-base", commits=None):
        self.default_branch = default_branch
        self.tree_sha = tree_sha
        self.commits = dict(commits or {})
        self.get_repository_calls = []
        self.get_commit_calls = []

    def get_repository(self, owner, repo):
        self.get_repository_calls.append((owner, repo))
        return {"default_branch": self.default_branch, "name": repo}

    def get_commit(self, owner, repo, branch):
        self.get_commit_calls.append((owner, repo, branch))
        sha = self.commits.get(branch, branch)
        return {
            "sha": sha,
            "commit": {"tree": {"sha": self.tree_sha}},
        }


class FakeGithubWriteClient:
    def __init__(self):
        self.calls = []
        self.blobs = {}
        self.trees = []
        self.commits = []
        self.refs = {}
        self.pulls = []
        self.fail_on = None
        self.fail_with = None
        self.fail_once = False
        self._triggered = set()

    @property
    def write_ops(self):
        return [
            name
            for name, _payload in self.calls
            if name in {
                "create_blob",
                "create_tree",
                "create_commit",
                "create_ref",
                "create_pull_request",
            }
        ]

    def create_blob(self, owner, repo, content):
        self._record("create_blob", owner=owner, repo=repo, content=content)
        sha = hashlib.sha1(f"blob {content}".encode()).hexdigest()
        self.blobs[sha] = content
        return sha

    def create_tree(self, owner, repo, base_tree, entries):
        self._record(
            "create_tree",
            owner=owner,
            repo=repo,
            base_tree=base_tree,
            entries=list(entries),
        )
        sha = hashlib.sha1(repr(entries).encode()).hexdigest()
        self.trees.append(
            {"sha": sha, "base_tree": base_tree, "tree": list(entries)}
        )
        return sha

    def create_commit(self, owner, repo, message, tree, parents):
        self._record(
            "create_commit",
            owner=owner,
            repo=repo,
            message=message,
            tree=tree,
            parents=list(parents),
        )
        sha = hashlib.sha1(repr((message, tree, parents)).encode()).hexdigest()
        self.commits.append(
            {
                "sha": sha,
                "message": message,
                "tree": tree,
                "parents": list(parents),
            }
        )
        return sha

    def create_ref(self, owner, repo, ref, sha):
        self._record("create_ref", owner=owner, repo=repo, ref=ref, sha=sha)
        if not ref.startswith("refs/heads/"):
            raise UpstreamUnavailable(f"only refs/heads allowed, not {ref}")
        if ref in self.refs:
            raise GitRefConflict(f"ref exists: {ref}")
        self.refs[ref] = sha

    def get_ref(self, owner, repo, ref):
        self._record("get_ref", owner=owner, repo=repo, ref=ref)
        key = ref
        if not key.startswith("refs/"):
            key = f"refs/{key}" if key.startswith("heads/") else f"refs/heads/{key}"
        return self.refs.get(key)

    def create_pull_request(
        self,
        owner,
        repo,
        *,
        title,
        body,
        head,
        base,
        draft=True,
    ):
        self._record(
            "create_pull_request",
            owner=owner,
            repo=repo,
            title=title,
            body=body,
            head=head,
            base=base,
            draft=draft,
        )
        pull = {
            "number": len(self.pulls) + 1,
            "html_url": f"https://github.com/{owner}/{repo}/pull/{len(self.pulls) + 1}",
            "draft": draft,
            "head": head,
            "base": base,
            "title": title,
            "body": body,
        }
        self.pulls.append(pull)
        return {
            "number": pull["number"],
            "html_url": pull["html_url"],
            "draft": pull["draft"],
        }

    def find_pull_request(self, owner, repo, head_branch):
        self._record(
            "find_pull_request",
            owner=owner,
            repo=repo,
            head_branch=head_branch,
        )
        for pull in self.pulls:
            if pull.get("head") == head_branch:
                return {
                    "number": pull["number"],
                    "html_url": pull["html_url"],
                    "draft": pull.get("draft", True),
                }
        return None

    def permission_denied(self, operation="create_ref"):
        self.fail_on = operation
        self.fail_with = GithubPermissionDenied("token cannot write")

    def unavailable(self, operation="create_commit"):
        self.fail_on = operation
        self.fail_with = UpstreamUnavailable(f"fake {operation} failed")

    def _record(self, operation, **payload):
        self.calls.append((operation, payload))
        if self.fail_on != operation:
            return
        if self.fail_once and operation in self._triggered:
            return
        self._triggered.add(operation)
        raise self.fail_with or UpstreamUnavailable(f"fake {operation} failed")
