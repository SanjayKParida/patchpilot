import json
import logging
import threading
import uuid
from datetime import datetime, timezone

from redis.exceptions import RedisError

from app.config import get_settings
from app.errors import AnalysisNotFound, AnalysisStoreUnavailable

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"

RECORD_PREFIX = "analysis:"
ORDER_KEY = "analysis:order"
ISSUE_PREFIX = "analysis:issue:"
ANON_USER = "_"


def connect_redis(url=None):
    """
    Open a Redis client from REDIS_URL.

    Raises AnalysisStoreUnavailable instead of returning a client
    that cannot actually persist.
    """

    import redis

    if url is not None:
        resolved = url.strip()
    else:
        resolved = (get_settings().redis_url or "").strip()
    if not resolved:
        raise AnalysisStoreUnavailable("REDIS_URL is not set")

    try:
        client = redis.from_url(resolved, decode_responses=True)
        client.ping()
        return client
    except RedisError as exc:
        raise AnalysisStoreUnavailable("Could not connect to Redis") from exc


class AnalysisStore:
    """
    Registry of analysis jobs, persisted in Redis.

    An analysis downloads a repository and calls a language model, so
    it is far too slow to answer inside a request. The API creates a
    job, returns immediately, and the client polls.
    """

    MAX_ENTRIES = 200

    def __init__(self, redis_client=None, *, redis_url=None):
        self._lock = threading.Lock()
        self._redis = (
            redis_client if redis_client is not None else connect_redis(redis_url)
        )

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
            self._save(record)
            self._index_new(record)
            self._evict()

        return json.loads(json.dumps(record))

    def find_reusable(
        self,
        owner,
        repo,
        issue_number,
        *,
        commit_sha=None,
        ref=None,
        user_id=None,
    ):
        """
        Return the latest live job for this issue, if any.

        A completed diagnosis is reused instead of cloning the repo
        and calling the model again. Queued and running jobs are
        reused so a second open does not start a parallel run. Failed
        jobs are skipped so Retry still creates a new analysis.
        """

        pinned_sha = (commit_sha or "").strip() or None
        pinned_ref = (ref or "").strip() or None
        issue_key = self._issue_key(owner, repo, issue_number, user_id)

        with self._lock:
            ids = self._list_range(issue_key)
            matches = []
            for analysis_id in ids:
                record = self._load(analysis_id)
                if record is None:
                    continue
                if record.get("status") == FAILED:
                    continue
                if not self._pin_matches(
                    record,
                    commit_sha=pinned_sha,
                    ref=pinned_ref,
                ):
                    continue
                matches.append(record)

        for status in (COMPLETED, RUNNING, QUEUED):
            for record in matches:
                if record.get("status") == status:
                    return record
        return None

    @staticmethod
    def _pin_matches(record, *, commit_sha, ref):
        record_sha = record.get("commit_sha")
        record_ref = record.get("ref")
        if commit_sha:
            return commit_sha in (record_sha, record_ref)
        if ref:
            return ref in (record_sha, record_ref)
        return True

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

        def mutate(record):
            existing = record.get("patch_proposal")
            if existing is not None:
                return "cached", dict(existing)

            if record.get("patch_generating"):
                return "running", None

            record["patch_generating"] = True
            record["patch_error"] = None
            return "started", None

        return self._mutate(analysis_id, mutate)

    def finish_patch_generation(self, analysis_id, proposal=None, error=None):
        """
        Store the proposal or error and clear the in-flight flag.

        A successful proposal is never replaced by a later empty
        finish (client disconnect, cancelled request). A failed
        attempt that produced no proposal stays retryable.
        """

        def mutate(record):
            if proposal is not None:
                record["patch_proposal"] = dict(proposal)
                record["patch_error"] = None
            elif error is not None and record.get("patch_proposal") is None:
                record["patch_error"] = error

            record["patch_generating"] = False
            return (
                record.get("patch_proposal") is not None,
                record.get("patch_error") is not None,
            )

        has_proposal, has_error = self._mutate(analysis_id, mutate)
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

        def mutate(record):
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

        return self._mutate(analysis_id, mutate)

    def set_delivery(self, analysis_id, delivery):
        """Replace the stored delivery record without touching approval."""

        if hasattr(delivery, "to_dict"):
            payload = delivery.to_dict()
        else:
            payload = dict(delivery)

        self._update(analysis_id, patch_delivery=payload)

    def adopt_anonymous(self, analysis_id, user_id):
        """
        Assign an unowned analysis to user_id.

        Missing IDs return None. An analysis already owned by this
        user, or by anyone else, is left unchanged. The record is not
        copied; only user_id (and the existing issue index) move.
        """

        token = (analysis_id or "").strip()
        owner_id = (user_id or "").strip()
        if not token or not owner_id:
            return None

        with self._lock:
            record = self._load(token)
            if record is None:
                return None

            current = record.get("user_id") or None
            if current:
                return json.loads(json.dumps(record))

            repository = record.get("repository") or {}
            old_key = self._issue_key(
                repository.get("owner"),
                repository.get("repo"),
                record.get("issue_number"),
                None,
            )
            record["user_id"] = owner_id
            new_key = self._issue_key(
                repository.get("owner"),
                repository.get("repo"),
                record.get("issue_number"),
                owner_id,
            )
            self._save(record)
            if old_key != new_key:
                def reindex():
                    self._redis.lrem(old_key, 0, token)
                    self._redis.lpush(new_key, token)

                self._redis_call(reindex)
            return json.loads(json.dumps(record))

    def invalidate(self, analysis_id):
        """Remove a job and its lookup indexes."""

        with self._lock:
            record = self._load(analysis_id)
            if record is None:
                return
            self._drop(record)

    # =========================================================
    # READS
    # =========================================================

    def get(self, analysis_id):
        with self._lock:
            record = self._load(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            return record

    # =========================================================
    # INTERNALS
    # =========================================================

    def _update(self, analysis_id, **fields):
        def mutate(record):
            record.update(fields)

        self._mutate(analysis_id, mutate)

    def _mutate(self, analysis_id, mutator):
        with self._lock:
            record = self._load(analysis_id)

            if record is None:
                raise AnalysisNotFound(
                    f"No analysis with id {analysis_id}"
                )

            result = mutator(record)
            self._save(record)
            return result

    def _save(self, record):
        try:
            payload = json.dumps(record, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise AnalysisStoreUnavailable(
                "Analysis could not be serialized"
            ) from exc
        self._redis_call(
            lambda: self._redis.set(self._record_key(record["id"]), payload)
        )

    def _load(self, analysis_id):
        raw = self._redis_call(
            lambda: self._redis.get(self._record_key(analysis_id))
        )
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AnalysisStoreUnavailable(
                "Stored analysis is not valid JSON"
            ) from exc

    def _index_new(self, record):
        analysis_id = record["id"]
        issue_key = self._issue_key(
            record["repository"]["owner"],
            record["repository"]["repo"],
            record["issue_number"],
            record.get("user_id"),
        )

        def write():
            self._redis.rpush(ORDER_KEY, analysis_id)
            self._redis.lpush(issue_key, analysis_id)

        self._redis_call(write)

    def _drop(self, record):
        analysis_id = record["id"]
        issue_key = self._issue_key(
            record["repository"]["owner"],
            record["repository"]["repo"],
            record["issue_number"],
            record.get("user_id"),
        )

        def write():
            self._redis.delete(self._record_key(analysis_id))
            self._redis.lrem(ORDER_KEY, 0, analysis_id)
            self._redis.lrem(issue_key, 0, analysis_id)

        self._redis_call(write)

    def _evict(self):
        while self._len_order() > self.MAX_ENTRIES:
            oldest_ids = self._redis_call(
                lambda: self._redis.lrange(ORDER_KEY, 0, 0)
            )
            if not oldest_ids:
                return
            oldest = oldest_ids[0]
            record = self._load(oldest)
            if record is None:
                self._redis_call(lambda: self._redis.lpop(ORDER_KEY))
                continue
            self._drop(record)

    def _len_order(self):
        return int(self._redis_call(lambda: self._redis.llen(ORDER_KEY) or 0))

    def _list_range(self, key):
        values = self._redis_call(lambda: self._redis.lrange(key, 0, -1))
        return list(values or [])

    def _redis_call(self, fn):
        try:
            return fn()
        except RedisError as exc:
            raise AnalysisStoreUnavailable(
                "Could not reach the analysis store"
            ) from exc

    @staticmethod
    def _record_key(analysis_id):
        return f"{RECORD_PREFIX}{analysis_id}"

    @staticmethod
    def _issue_key(owner, repo, issue_number, user_id):
        user = user_id if user_id else ANON_USER
        return (
            f"{ISSUE_PREFIX}{user}:"
            f"{(owner or '').lower()}:"
            f"{(repo or '').lower()}:"
            f"{issue_number}"
        )

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
