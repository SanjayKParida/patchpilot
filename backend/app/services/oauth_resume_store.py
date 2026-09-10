"""
Short-lived OAuth resume records.

Stores the repair location the user left to authorize GitHub so the
callback can send them back. Single-use: consume reads and deletes.
"""

import json
import secrets
import threading

from redis.exceptions import RedisError

from app.errors import AnalysisStoreUnavailable
from app.services.analysis_store import connect_redis

RESUME_PREFIX = "oauth:resume:"
RESUME_TTL_SECONDS = 15 * 60


class OAuthResumeStore:
    def __init__(self, redis_client=None, *, redis_url=None):
        self._lock = threading.Lock()
        self._redis = redis_client
        self._redis_url = redis_url

    def create(
        self,
        *,
        analysis_id=None,
        repair_path=None,
        stage=None,
        ttl_seconds=RESUME_TTL_SECONDS,
    ):
        resume_id = secrets.token_urlsafe(32)
        payload = {
            "id": resume_id,
            "analysis_id": analysis_id or None,
            "repair_path": repair_path or None,
            "stage": stage or None,
        }
        try:
            body = json.dumps(payload, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise AnalysisStoreUnavailable(
                "OAuth resume could not be serialized"
            ) from exc

        with self._lock:
            self._redis_call(
                lambda: self._client().set(
                    self._key(resume_id),
                    body,
                    ex=int(ttl_seconds),
                )
            )
        return payload

    def consume(self, resume_id):
        """Read and delete. Missing or expired IDs return None."""

        token = (resume_id or "").strip()
        if not token:
            return None

        with self._lock:
            raw = self._redis_call(lambda: self._getdel(self._key(token)))

        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AnalysisStoreUnavailable(
                "Stored OAuth resume is not valid JSON"
            ) from exc

    def _client(self):
        if self._redis is None:
            self._redis = connect_redis(self._redis_url)
        return self._redis

    def _getdel(self, key):
        client = self._client()
        getdel = getattr(client, "getdel", None)
        if callable(getdel):
            return getdel(key)

        pipe = client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        raw, _deleted = pipe.execute()
        return raw

    def _redis_call(self, fn):
        try:
            return fn()
        except RedisError as exc:
            raise AnalysisStoreUnavailable(
                "Could not reach the OAuth resume store"
            ) from exc

    @staticmethod
    def _key(resume_id):
        return f"{RESUME_PREFIX}{resume_id}"
