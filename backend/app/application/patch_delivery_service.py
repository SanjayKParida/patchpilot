"""
Turn an approved, validated stored proposal into a draft GitHub PR.

Does not generate, validate, retrieve, or accept a client patch payload.
All inputs come from AnalysisStore.
"""

from datetime import datetime, timezone

from app.domain.patch_delivery import (
    STAGE_APPLY,
    STAGE_COMMIT,
    STAGE_PRECONDITIONS,
    STAGE_PULL_REQUEST,
    STAGE_PUSH,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    PatchApproval,
    PatchDelivery,
    delivery_branch_name,
    first_line,
    is_safe_branch_name,
)
from app.errors import (
    GitRefConflict,
    GithubPermissionDenied,
    IssueNotFound,
    PatchApprovalNotFound,
    PatchDeliveryInProgress,
    PatchDeliveryNotFound,
    PatchDeliveryRejected,
    PatchNotApproved,
    PatchNotValidated,
    RepositoryNotFound,
    UpstreamUnavailable,
)
from app.services.patch_apply import (
    apply_proposal_to_map,
    files_to_map,
    is_safe_relative_path,
    proposal_files,
)
from app.services.patch_types import STATUS_OK


class PatchDeliveryService:
    FILE_MODE = "100644"
    MAX_BRANCH_SUFFIX = 3

    def __init__(self, store, github, writer, access=None):
        self.store = store
        self.github = github
        self.writer = writer
        self.access = access

    def approve(self, analysis_id, actor=None):
        record = self.store.get(analysis_id)
        if self.access is not None:
            self.access.assert_can_read_analysis(record, actor)
        self._assert_approval_preconditions(record)

        commit_sha = record["commit_sha"]

        if record.get("patch_approved"):
            if record.get("patch_approved_commit_sha") != commit_sha:
                raise PatchDeliveryRejected(
                    "This approval is bound to a different commit than "
                    "the analysis. Approval was not changed."
                )
            return self._approval_from(record)

        approved_at = _now()
        self.store.set_approval(
            analysis_id,
            approved_at=approved_at,
            commit_sha=commit_sha,
        )
        record = self.store.get(analysis_id)
        return self._approval_from(record)

    def get_approval(self, analysis_id):
        record = self.store.get(analysis_id)
        self._require_completed(record)

        if not record.get("patch_approved"):
            raise PatchApprovalNotFound(
                "This patch has not been approved"
            )

        return self._approval_from(record)

    def get_delivery(self, analysis_id):
        record = self.store.get(analysis_id)
        self._require_completed(record)

        payload = record.get("patch_delivery")
        if payload is None:
            raise PatchDeliveryNotFound(
                "No patch delivery has been attempted"
            )

        return PatchDelivery.from_dict(payload)

    def deliver(self, analysis_id, actor=None):
        record = self.store.get(analysis_id)
        if self.access is not None:
            self.access.assert_can_deliver(record, actor)
        self._assert_delivery_preconditions(record)

        kind, _current = self.store.begin_delivery(analysis_id)

        if kind == "succeeded":
            return PatchDelivery.from_dict(
                self.store.get(analysis_id)["patch_delivery"]
            )

        if kind == "running":
            raise PatchDeliveryInProgress(
                "A delivery attempt is already running for this analysis"
            )

        record = self.store.get(analysis_id)

        try:
            return self._deliver(record)
        except PatchDeliveryRejected as e:
            self._mark_failed(analysis_id, STAGE_PRECONDITIONS, str(e))
            raise
        except (GithubPermissionDenied, RepositoryNotFound, UpstreamUnavailable):
            raise

    def _deliver(self, record):
        analysis_id = record["id"]
        owner, repo = self._repository(record)
        base_sha = record["commit_sha"]
        previous = PatchDelivery.from_dict(record.get("patch_delivery"))
        previous.base_commit_sha = base_sha
        previous.status = STATUS_FAILED

        patched, apply_errors = self._apply(record)

        if apply_errors:
            previous.stage = STAGE_APPLY
            previous.errors = apply_errors
            self.store.set_delivery(analysis_id, previous)
            return previous

        try:
            default_branch = self.github.get_repository(owner, repo)[
                "default_branch"
            ]
        except (RepositoryNotFound, UpstreamUnavailable, GithubPermissionDenied) as e:
            previous.stage = STAGE_PUSH
            previous.errors = [str(e)]
            self.store.set_delivery(analysis_id, previous)
            raise

        branch = previous.branch or delivery_branch_name(
            record["issue_number"],
            base_sha,
            analysis_id,
        )

        if not is_safe_branch_name(branch, default_branch=default_branch):
            previous.stage = STAGE_PUSH
            previous.errors = [f"unsafe branch name: {branch}"]
            self.store.set_delivery(analysis_id, previous)
            raise PatchDeliveryRejected(
                f"Refusing to create branch {branch!r}"
            )

        if previous.commit_sha:
            return self._resume(
                record,
                previous,
                owner=owner,
                repo=repo,
                branch=branch,
                default_branch=default_branch,
                base_sha=base_sha,
            )

        return self._commit_and_open(
            record,
            previous,
            patched=patched,
            owner=owner,
            repo=repo,
            branch=branch,
            default_branch=default_branch,
            base_sha=base_sha,
        )

    def _commit_and_open(
        self,
        record,
        previous,
        *,
        patched,
        owner,
        repo,
        branch,
        default_branch,
        base_sha,
    ):
        analysis_id = record["id"]
        previous.stage = STAGE_COMMIT
        previous.branch = branch
        self.store.set_delivery(analysis_id, previous)

        try:
            commit = self.github.get_commit(owner, repo, base_sha)
            remote_sha = commit.get("sha") if isinstance(commit, dict) else None
            if remote_sha and remote_sha != base_sha:
                raise PatchDeliveryRejected(
                    "GitHub returned a different commit than the analysis "
                    f"was pinned to ({base_sha}). Delivery was not started."
                )
            tree_sha = commit["commit"]["tree"]["sha"]
        except (PatchDeliveryRejected, RepositoryNotFound, UpstreamUnavailable) as e:
            previous.errors = [str(e)]
            self.store.set_delivery(analysis_id, previous)
            raise

        proposal = record["patch_proposal"]
        entries = []

        try:
            for path, _language, _hunks in proposal_files(proposal):
                blob_sha = self.writer.create_blob(
                    owner,
                    repo,
                    patched[path],
                )
                entries.append({
                    "path": path,
                    "mode": self.FILE_MODE,
                    "type": "blob",
                    "sha": blob_sha,
                })

            new_tree = self.writer.create_tree(
                owner,
                repo,
                tree_sha,
                entries,
            )
            message = self._commit_message(record)
            new_commit = self.writer.create_commit(
                owner,
                repo,
                message,
                new_tree,
                [base_sha],
            )
        except (GithubPermissionDenied, RepositoryNotFound, UpstreamUnavailable) as e:
            previous.errors = [str(e)]
            self.store.set_delivery(analysis_id, previous)
            raise

        previous.commit_sha = new_commit
        previous.stage = STAGE_PUSH
        self.store.set_delivery(analysis_id, previous)

        branch = self._create_or_reuse_branch(
            previous,
            owner=owner,
            repo=repo,
            branch=branch,
            commit_sha=new_commit,
            default_branch=default_branch,
            issue_number=record["issue_number"],
            analysis_id=analysis_id,
            base_sha=base_sha,
        )
        previous.branch = branch
        self.store.set_delivery(analysis_id, previous)

        return self._open_or_find_pr(
            record,
            previous,
            owner=owner,
            repo=repo,
            branch=branch,
            default_branch=default_branch,
            base_sha=base_sha,
        )

    def _resume(
        self,
        record,
        previous,
        *,
        owner,
        repo,
        branch,
        default_branch,
        base_sha,
    ):
        analysis_id = record["id"]
        commit_sha = previous.commit_sha
        previous.stage = STAGE_PUSH
        previous.branch = branch
        self.store.set_delivery(analysis_id, previous)

        branch = self._create_or_reuse_branch(
            previous,
            owner=owner,
            repo=repo,
            branch=branch,
            commit_sha=commit_sha,
            default_branch=default_branch,
            issue_number=record["issue_number"],
            analysis_id=analysis_id,
            base_sha=base_sha,
        )
        previous.branch = branch
        self.store.set_delivery(analysis_id, previous)

        return self._open_or_find_pr(
            record,
            previous,
            owner=owner,
            repo=repo,
            branch=branch,
            default_branch=default_branch,
            base_sha=base_sha,
        )

    def _create_or_reuse_branch(
        self,
        previous,
        *,
        owner,
        repo,
        branch,
        commit_sha,
        default_branch,
        issue_number,
        analysis_id,
        base_sha,
    ):
        candidates = [branch]
        for suffix in range(2, self.MAX_BRANCH_SUFFIX + 1):
            candidates.append(
                delivery_branch_name(
                    issue_number,
                    base_sha,
                    analysis_id,
                    suffix=suffix,
                )
            )

        last_error = None

        for candidate in candidates:
            if not is_safe_branch_name(
                candidate,
                default_branch=default_branch,
            ):
                last_error = f"unsafe branch name: {candidate}"
                continue

            ref = f"refs/heads/{candidate}"
            existing = self.writer.get_ref(owner, repo, ref)

            if existing == commit_sha:
                return candidate

            if existing is not None:
                last_error = (
                    f"branch {candidate} already points at {existing}, "
                    "not this delivery commit"
                )
                continue

            try:
                self.writer.create_ref(owner, repo, ref, commit_sha)
                return candidate
            except GitRefConflict:
                conflict = self.writer.get_ref(owner, repo, ref)
                if conflict == commit_sha:
                    return candidate
                last_error = (
                    f"branch {candidate} already exists at {conflict}"
                )
                continue
            except (GithubPermissionDenied, RepositoryNotFound, UpstreamUnavailable) as e:
                previous.errors = [str(e)]
                self.store.set_delivery(analysis_id, previous)
                raise

        previous.errors = [last_error or "could not create a unique branch"]
        self.store.set_delivery(analysis_id, previous)
        raise UpstreamUnavailable(previous.errors[0])

    def _open_or_find_pr(
        self,
        record,
        previous,
        *,
        owner,
        repo,
        branch,
        default_branch,
        base_sha,
    ):
        analysis_id = record["id"]
        previous.stage = STAGE_PULL_REQUEST
        previous.branch = branch
        self.store.set_delivery(analysis_id, previous)

        existing = self.writer.find_pull_request(owner, repo, branch)
        if existing and existing.get("number") and existing.get("html_url"):
            return self._succeed(analysis_id, previous, existing, branch, base_sha)

        try:
            created = self.writer.create_pull_request(
                owner,
                repo,
                title=self._pr_title(record),
                body=self._pr_body(record, base_sha),
                head=branch,
                base=default_branch,
                draft=True,
            )
        except (GithubPermissionDenied, RepositoryNotFound, UpstreamUnavailable) as e:
            previous.errors = [str(e)]
            self.store.set_delivery(analysis_id, previous)
            raise

        if not created.get("number") or not created.get("html_url"):
            previous.errors = ["GitHub did not return a pull request URL"]
            self.store.set_delivery(analysis_id, previous)
            raise UpstreamUnavailable(previous.errors[0])

        return self._succeed(analysis_id, previous, created, branch, base_sha)

    def _succeed(self, analysis_id, previous, pull, branch, base_sha):
        previous.status = STATUS_SUCCEEDED
        previous.stage = STAGE_PULL_REQUEST
        previous.branch = branch
        previous.base_commit_sha = base_sha
        previous.pr_number = pull["number"]
        previous.pr_url = pull["html_url"]
        previous.draft = bool(pull.get("draft", True))
        previous.errors = []
        self.store.set_delivery(analysis_id, previous)
        return previous

    def _apply(self, record):
        snapshot = record.get("snapshot")
        if not snapshot:
            return {}, ["No pinned repository snapshot is stored"]

        patched, _files, errors = apply_proposal_to_map(
            record["patch_proposal"],
            files_to_map(snapshot),
        )
        return patched, errors

    def _assert_delivery_preconditions(self, record):
        self._assert_approval_preconditions(record)

        if not record.get("patch_approved"):
            raise PatchNotApproved(
                "The patch has not been approved"
            )

        commit_sha = record.get("commit_sha")
        if record.get("patch_approved_commit_sha") != commit_sha:
            raise PatchDeliveryRejected(
                "The approval is bound to a different commit than "
                "the analysis. Delivery was not started."
            )

        snapshot_commit = record.get("snapshot_commit")
        if snapshot_commit and snapshot_commit != commit_sha:
            raise PatchDeliveryRejected(
                "The stored repository snapshot does not match the "
                "analysis commit. Delivery was not started."
            )

        if not record.get("snapshot"):
            raise PatchDeliveryRejected(
                "No pinned repository snapshot is stored. "
                "Delivery was not started."
            )

    def _assert_approval_preconditions(self, record):
        self._require_completed(record)

        commit_sha = (record.get("commit_sha") or "").strip()
        if not commit_sha:
            raise PatchDeliveryRejected(
                "This analysis has no resolved commit SHA"
            )

        snapshot_commit = record.get("snapshot_commit")
        if snapshot_commit and snapshot_commit != commit_sha:
            raise PatchDeliveryRejected(
                "The stored repository snapshot does not match the "
                "analysis commit. Approval was not recorded."
            )

        proposal = record.get("patch_proposal")
        if not proposal:
            raise PatchDeliveryRejected(
                "No patch proposal is available for this analysis"
            )

        if proposal.get("status") != STATUS_OK:
            raise PatchDeliveryRejected(
                "The stored proposal is not a valid ok patch"
            )

        entries = list(proposal_files(proposal))
        if not entries:
            raise PatchDeliveryRejected(
                "The stored proposal has no files"
            )

        for path, _language, hunks in entries:
            if not is_safe_relative_path(path):
                raise PatchDeliveryRejected(
                    f"unsafe path: {path}"
                )
            if not hunks:
                raise PatchDeliveryRejected(
                    f"no hunks for {path}"
                )

        validation = record.get("patch_validation")
        if not validation:
            raise PatchNotValidated(
                "The patch has not been validated"
            )

        if (
            validation.get("status") != "passed"
            or validation.get("validation_passed") is not True
            or validation.get("runnable") is not True
        ):
            raise PatchNotValidated(
                "The patch has not passed runnable validation"
            )

    def _require_completed(self, record):
        if record.get("status") != "completed":
            raise IssueNotFound(
                "This analysis has not completed yet"
            )

    def _repository(self, record):
        repository = record.get("repository") or {}
        owner = repository.get("owner")
        repo = repository.get("repo")
        if not owner or not repo:
            raise PatchDeliveryRejected(
                "This analysis has no stored repository identity"
            )
        return owner, repo

    def _approval_from(self, record):
        return PatchApproval(
            approved=True,
            approved_at=record["patch_approved_at"],
            commit_sha=record["patch_approved_commit_sha"],
            analysis_id=record["id"],
        )

    def _mark_failed(self, analysis_id, stage, message):
        current = PatchDelivery.from_dict(
            self.store.get(analysis_id).get("patch_delivery")
        )
        if current.status == STATUS_SUCCEEDED:
            return
        current.status = STATUS_FAILED
        current.stage = stage
        if message and message not in current.errors:
            current.errors.append(message)
        self.store.set_delivery(analysis_id, current)

    def _commit_message(self, record):
        proposal = record.get("patch_proposal") or {}
        summary = first_line(proposal.get("summary"), limit=72) or "PatchPilot patch"
        return (
            f"{summary}\n\n"
            f"PatchPilot analysis {record['id']}\n"
            f"Pinned commit {record['commit_sha']}\n"
        )

    def _pr_title(self, record):
        issue = record.get("issue") or {}
        number = record["issue_number"]
        title = first_line(issue.get("title"), limit=56)
        if title:
            return first_line(f"Fix #{number}: {title}", limit=72)
        return f"Fix #{number}"

    def _pr_body(self, record, base_sha):
        proposal = record.get("patch_proposal") or {}
        number = record["issue_number"]
        summary = (proposal.get("summary") or "").strip()
        reasoning = (proposal.get("reasoning") or "").strip()
        parts = [
            f"PatchPilot draft for issue #{number}.",
            "",
            f"Analyzed commit: `{base_sha}`",
            "",
        ]
        if summary:
            parts.extend([summary, ""])
        if reasoning:
            parts.extend([reasoning, ""])
        parts.append(
            "This pull request was opened as a draft. "
            "It does not merge automatically."
        )
        return "\n".join(parts)


def _now():
    return datetime.now(timezone.utc).isoformat()
