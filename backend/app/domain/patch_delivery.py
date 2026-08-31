"""
Delivery and approval types.

No HTTP, GitHub, or subprocess imports. The application layer
orchestrates; infrastructure talks to GitHub.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

STAGE_PRECONDITIONS = "preconditions"
STAGE_APPLY = "apply"
STAGE_COMMIT = "commit"
STAGE_PUSH = "push"
STAGE_PULL_REQUEST = "pull_request"

VALID_DELIVERY_STATUSES = frozenset({
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
})

_BRANCH_SAFE = re.compile(r"^[a-z0-9._/-]+$")
_DEFAULT_BRANCH_BLOCKLIST = frozenset({
    "main",
    "master",
    "trunk",
    "develop",
    "dev",
    "production",
    "prod",
})


@dataclass
class PatchApproval:
    approved: bool
    approved_at: str
    commit_sha: str
    analysis_id: str

    def to_dict(self):
        return {
            "analysis_id": self.analysis_id,
            "approved": self.approved,
            "approved_at": self.approved_at,
            "commit_sha": self.commit_sha,
        }


@dataclass
class PatchDelivery:
    status: str
    stage: str
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    base_commit_sha: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    draft: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def succeeded(self):
        return (
            self.status == STATUS_SUCCEEDED
            and self.pr_number is not None
            and bool(self.pr_url)
        )

    def to_dict(self):
        return {
            "base_commit_sha": self.base_commit_sha,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "draft": self.draft,
            "errors": list(self.errors),
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "stage": self.stage,
            "status": self.status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload):
        payload = payload or {}
        return cls(
            status=payload.get("status") or STATUS_FAILED,
            stage=payload.get("stage") or STAGE_PRECONDITIONS,
            branch=payload.get("branch"),
            commit_sha=payload.get("commit_sha"),
            base_commit_sha=payload.get("base_commit_sha"),
            pr_number=payload.get("pr_number"),
            pr_url=payload.get("pr_url"),
            draft=payload.get("draft", True),
            errors=list(payload.get("errors") or []),
            warnings=list(payload.get("warnings") or []),
        )


def delivery_branch_name(issue_number, commit_sha, analysis_id, suffix=None):
    """
    Deterministic branch for one analysis + pinned commit.

    patchpilot/issue-{n}/{short_sha}-{analysis_prefix}[-{suffix}]
    """

    short_sha = (commit_sha or "")[:12].lower()
    prefix = (analysis_id or "")[:8].lower()
    number = int(issue_number)

    name = f"patchpilot/issue-{number}/{short_sha}-{prefix}"

    if suffix is not None:
        name = f"{name}-{int(suffix)}"

    return name


def is_safe_branch_name(name, default_branch=None):
    """Reject traversal, absolute refs, and the repository default branch."""

    if not name or not isinstance(name, str):
        return False

    if "\x00" in name or ".." in name:
        return False

    if name.startswith("/") or name.startswith("\\"):
        return False

    if name.startswith("refs/"):
        return False

    if not _BRANCH_SAFE.match(name):
        return False

    if name.startswith("-") or name.endswith("/") or "//" in name:
        return False

    leaf = name.rsplit("/", 1)[-1]
    blocked = set(_DEFAULT_BRANCH_BLOCKLIST)

    if default_branch:
        blocked.add(default_branch.lower())

    if name.lower() in blocked or leaf.lower() in blocked:
        return False

    return True


def first_line(text, limit=72):
    """Commit/PR title fragment from untrusted model or issue text."""

    raw = (text or "").replace("\r", "\n").split("\n", 1)[0]
    cleaned = "".join(ch for ch in raw if ch.isprintable()).strip()

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 1].rstrip() + "…"
