import threading
import uuid
from datetime import datetime, timezone

from app.errors import AnalysisNotFound

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

    def create(self, owner, repo, issue_number):
        analysis_id = uuid.uuid4().hex

        record = {
            "id": analysis_id,
            "status": QUEUED,
            "stage": None,
            "error": None,
            "repository": {"owner": owner, "repo": repo},
            "issue_number": issue_number,
            "issue": None,
            "signals": [],
            "relevant_files": [],
            "diagnosis": None,
            "diagnosis_error": None,
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
