"""Short-lived Redis OAuth resume records are single-use."""

import json

import pytest
from redis.exceptions import RedisError

from app.errors import AnalysisStoreUnavailable
from app.services.oauth_resume_store import RESUME_TTL_SECONDS, OAuthResumeStore
from tests.fakes.memory_redis import MemoryRedis


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _store(clock=None):
    redis = MemoryRedis(clock=clock)
    return OAuthResumeStore(redis_client=redis), redis


def test_create_resume_state():
    store, redis = _store()
    created = store.create(
        analysis_id="analysis-abc",
        repair_path="/r/owner/repo/issues/1/diagnosis",
        stage="diagnosis",
    )

    assert created["id"]
    assert created["id"] != "analysis-abc"
    assert created["analysis_id"] == "analysis-abc"
    assert created["repair_path"] == "/r/owner/repo/issues/1/diagnosis"
    assert created["stage"] == "diagnosis"

    raw = redis.get(f"oauth:resume:{created['id']}")
    assert json.loads(raw) == created


def test_consume_is_single_use():
    store, _redis = _store()
    created = store.create(
        analysis_id="a1",
        repair_path="/r/o/r/issues/3/patch",
        stage="patch",
    )

    first = store.consume(created["id"])
    assert first["id"] == created["id"]
    assert first["analysis_id"] == "a1"
    assert first["repair_path"] == "/r/o/r/issues/3/patch"
    assert first["stage"] == "patch"

    assert store.consume(created["id"]) is None


def test_consume_missing_returns_none():
    store, _redis = _store()
    assert store.consume("missing") is None
    assert store.consume("") is None
    assert store.consume(None) is None


def test_expired_resume_cannot_be_consumed():
    clock = FakeClock()
    store, _redis = _store(clock=clock)
    created = store.create(
        analysis_id="a1",
        repair_path="/r/o/r/issues/1/diagnosis",
        stage="diagnosis",
        ttl_seconds=RESUME_TTL_SECONDS,
    )

    clock.advance(RESUME_TTL_SECONDS)
    assert store.consume(created["id"]) is None


class BoomRedis:
    def getdel(self, key):
        raise RedisError("down")

    def set(self, key, value, ex=None, **kwargs):
        raise RedisError("down")


def test_redis_errors_are_not_swallowed():
    store = OAuthResumeStore(redis_client=BoomRedis())
    with pytest.raises(AnalysisStoreUnavailable):
        store.create(
            analysis_id="a1",
            repair_path="/r/o/r/issues/1/diagnosis",
            stage="diagnosis",
        )
