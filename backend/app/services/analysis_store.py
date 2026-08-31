import logging
import threading
import uuid
from datetime import datetime, timezone

from app.errors import AnalysisNotFound

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"


class AnalysisStore:
    """
    In-memory registry of analysis jobs.

    An analysis downloads a repository and calls a language model, so
    it is far too slow to answer inside a request. The API creates a
    job, returns immediately, and the client polls.

    Deliberately in-memory: analyses are cheap to re-run and nothing
    here is worth a database yet. The consequence is that jobs do not
    survive a restart and do not work across multiple worker
    processes. Run the API with a single worker, or move this behind
    a shared store before scaling out.
    """

    MAX_ENTRIES = 200

    def __init__(self):
        self._lock = threading.Lock()
        self._analyses = {}
        self._order = []

    # =========================================================
    # WRITES
    # =========================================================

    def create(
        self,
        owner,
        repo,
        issue_number,
        ref=None,
        commit_sha=None,
        user_id=None,
        github_repo_id=None,
    ):
        analysis_id = uuid.uuid4().hex

        record = {
            "id": analysis_id,
            "status": QUEUED,
            "stage": None,
            "error": None,
            "repository": {"owner": owner, "repo": repo},
            "user_id": user_id,
            "github_repo_id": github_repo_id,
            "issue_number": issue_number,
            "ref": ref,
            "commit_sha": commit_sha,
            "issue": None,
            "signals": [],
            "relevant_files": [],
            "diagnosis": None,
            "diagnosis_error": None,
            "context_package": None,
            "context_error": None,
            "patch_proposal": None,
            "patch_error": None,
            "patch_generating": False,
            "patch_validation": None,
            "patch_validation_error": None,
            "snapshot": None,
            "snapshot_commit": None,
            "patch_approved": False,
            "patch_approved_at": None,
            "patch_approved_commit_sha": None,
            "patch_delivery": None,
            "created_at": self._now(),
            "completed_at": None,
        }

        with self._lock:
            self._analyses[analysis_id] = record
            self._order.append(analysis_id)
            self._evict()

        return record

    def mark_running(self, analysis_id, stage):
        self._update(
            analysis_id,
            status=RUNNING,
            stage=stage,
        )

    def mark_completed(self, analysis_id, result):
        self._update(
            analysis_id,
            status=COMPLETED,
            stage=None,
            completed_at=self._now(),
            **result,
        )

    def mark_failed(self, analysis_id, message):
        self._update(
            analysis_id,
            status=FAILED,
            stage=None,
            error=message,
            completed_at=self._now(),
        )

    def update(self, analysis_id, **fields):
        """
        Merge fields into an existing job record.

        Used for on-demand artifacts (patch proposals) that are not
        produced by the analysis runner itself.
        """

        self._update(analysis_id, **fields)

    def set_patch(self, analysis_id, proposal=None, error=None):
        """
        Record a patch attempt without touching diagnosis or context.

        `proposal` is a serialised PatchProposal dict, or None when
        generation failed before producing one.
        """

        self._update(
            analysis_id,
            patch_proposal=proposal,
            patch_error=error,
            patch_generating=False,
        )

    def begin_patch_generation(self, analysis_id):
        """
        Atomically start (or reuse) a patch generation attempt.

        Returns (kind, proposal_or_none):
        - cached: a proposal is already stored; do not generate
        - running: another request owns generation
        - started: this caller must generate
        """

        with self._lock:
            record = self._analyses.get(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            existing = record.get("patch_proposal")
            if existing is not None:
                return "cached", dict(existing)

            if record.get("patch_generating"):
                return "running", None

            record["patch_generating"] = True
            record["patch_error"] = None
            return "started", None

    def finish_patch_generation(self, analysis_id, proposal=None, error=None):
        """
        Store the proposal or error and clear the in-flight flag.

        A successful proposal is never replaced by a later empty
        finish (client disconnect, cancelled request). A failed
        attempt that produced no proposal stays retryable.
        """

        with self._lock:
            record = self._analyses.get(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            if proposal is not None:
                record["patch_proposal"] = dict(proposal)
                record["patch_error"] = None
            elif (
                error is not None
                and record.get("patch_proposal") is None
            ):
                record["patch_error"] = error

            record["patch_generating"] = False
            has_proposal = record.get("patch_proposal") is not None
            has_error = record.get("patch_error") is not None

        logger.info(
            "patch_cache_write analysis_id=%s has_proposal=%s has_error=%s",
            analysis_id,
            has_proposal,
            has_error,
        )

    def set_approval(self, analysis_id, *, approved_at, commit_sha):
        """
        Record explicit approval bound to the analysis commit.

        Idempotent when the same SHA is already stored.
        """

        self._update(
            analysis_id,
            patch_approved=True,
            patch_approved_at=approved_at,
            patch_approved_commit_sha=commit_sha,
        )

    def begin_delivery(self, analysis_id):
        """
        Atomically start (or resume) a delivery attempt.

        Returns (kind, delivery_dict):
        - succeeded: already has a PR; caller must not write
        - running: another attempt is in flight
        - started: this caller owns the attempt
        """

        with self._lock:
            record = self._analyses.get(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            current = dict(record.get("patch_delivery") or {})
            status = current.get("status")

            if status == "succeeded":
                return "succeeded", current

            if status == "running":
                return "running", current

            delivery = {
                "status": "running",
                "stage": "preconditions",
                "branch": current.get("branch"),
                "commit_sha": current.get("commit_sha"),
                "base_commit_sha": record.get("commit_sha"),
                "pr_number": current.get("pr_number"),
                "pr_url": current.get("pr_url"),
                "draft": True,
                "errors": [],
                "warnings": list(current.get("warnings") or []),
            }
            record["patch_delivery"] = delivery
            return "started", dict(delivery)

    def set_delivery(self, analysis_id, delivery):
        """Replace the stored delivery record without touching approval."""

        if hasattr(delivery, "to_dict"):
            payload = delivery.to_dict()
        else:
            payload = dict(delivery)

        self._update(analysis_id, patch_delivery=payload)

    # =========================================================
    # READS
    # =========================================================

    def get(self, analysis_id):
        with self._lock:
            record = self._analyses.get(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            return dict(record)

    # =========================================================
    # INTERNALS
    # =========================================================

    def _update(self, analysis_id, **fields):
        with self._lock:
            record = self._analyses.get(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            record.update(fields)

    def _evict(self):
        while len(self._order) > self.MAX_ENTRIES:
            self._analyses.pop(self._order.pop(0), None)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
