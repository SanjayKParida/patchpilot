"""AnalysisStore persists jobs in Redis and reuses completed diagnoses."""

import pytest
from redis.exceptions import RedisError

from app.errors import AnalysisNotFound, AnalysisStoreUnavailable
from app.services.analysis_store import AnalysisStore
from tests.fakes.memory_redis import MemoryRedis


def _store():
    return AnalysisStore(redis_client=MemoryRedis())


class BoomRedis:
    def get(self, key):
        raise RedisError("down")

    def set(self, key, value):
        raise RedisError("down")

    def delete(self, *keys):
        raise RedisError("down")

    def rpush(self, key, *values):
        raise RedisError("down")

    def lpush(self, key, *values):
        raise RedisError("down")

    def lrange(self, key, start, end):
        raise RedisError("down")

    def llen(self, key):
        raise RedisError("down")

    def lrem(self, key, count, value):
        raise RedisError("down")

    def lpop(self, key):
        raise RedisError("down")


def test_save_and_get_round_trip():
    store = _store()
    created = store.create("Owner", "Repo", 3, user_id="u1")

    fetched = store.get(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["status"] == "queued"
    assert fetched["repository"] == {"owner": "Owner", "repo": "Repo"}
    assert fetched["issue_number"] == 3
    assert fetched["user_id"] == "u1"


def test_completed_analysis_is_persisted():
    store = _store()
    created = store.create("o", "r", 3)
    store.mark_completed(
        created["id"],
        {
            "diagnosis": {"root_cause": "filter inverted"},
            "commit_sha": "abc",
        },
    )

    fetched = store.get(created["id"])
    assert fetched["status"] == "completed"
    assert fetched["diagnosis"]["root_cause"] == "filter inverted"
    assert fetched["commit_sha"] == "abc"
    assert fetched["completed_at"]


def test_reusable_lookup_returns_completed_job():
    store = _store()
    first = store.create("o", "r", 3, user_id="u1")
    store.mark_completed(first["id"], {"diagnosis": {"root_cause": "x"}})
    store.create("o", "r", 3, user_id="u1")

    reused = store.find_reusable("o", "r", 3, user_id="u1")
    assert reused["id"] == first["id"]
    assert reused["status"] == "completed"


def test_user_isolation():
    store = _store()
    alice = store.create("o", "r", 3, user_id="alice")
    store.mark_completed(alice["id"], {"diagnosis": {"root_cause": "alice"}})
    bob = store.create("o", "r", 3, user_id="bob")
    store.mark_completed(bob["id"], {"diagnosis": {"root_cause": "bob"}})

    assert store.find_reusable("o", "r", 3, user_id="alice")["id"] == alice["id"]
    assert store.find_reusable("o", "r", 3, user_id="bob")["id"] == bob["id"]
    assert store.find_reusable("o", "r", 3) is None


def test_failed_analysis_is_not_reused():
    store = _store()
    failed = store.create("o", "r", 3)
    store.mark_failed(failed["id"], "boom")

    assert store.find_reusable("o", "r", 3) is None
    assert store.get(failed["id"])["status"] == "failed"


def test_queued_job_is_reused_when_nothing_completed():
    store = _store()
    created = store.create("o", "r", 3)
    reused = store.find_reusable("o", "r", 3)
    assert reused["id"] == created["id"]
    assert reused["status"] == "queued"


def test_pin_mismatch_is_not_reused():
    store = _store()
    created = store.create("o", "r", 3, commit_sha="aaa")
    store.mark_completed(created["id"], {"commit_sha": "aaa"})

    assert store.find_reusable("o", "r", 3, commit_sha="bbb") is None
    assert store.find_reusable("o", "r", 3, commit_sha="aaa")["id"] == created["id"]


def test_invalidate_removes_record_and_lookup():
    store = _store()
    created = store.create("o", "r", 3)
    store.mark_completed(created["id"], {"diagnosis": {"root_cause": "x"}})

    store.invalidate(created["id"])

    with pytest.raises(AnalysisNotFound):
        store.get(created["id"])
    assert store.find_reusable("o", "r", 3) is None


def test_invalidate_missing_id_is_a_no_op():
    store = _store()
    store.invalidate("missing")


def test_missing_analysis_raises():
    store = _store()
    with pytest.raises(AnalysisNotFound):
        store.get("missing")


def test_creating_another_job_keeps_the_completed_one():
    store = _store()
    first = store.create("o", "r", 3)
    store.mark_completed(first["id"], {"diagnosis": {"root_cause": "x"}})
    second = store.create("o", "r", 3)

    assert second["id"] != first["id"]
    assert store.find_reusable("o", "r", 3)["id"] == first["id"]


def test_redis_errors_are_not_swallowed():
    store = AnalysisStore(redis_client=BoomRedis())
    with pytest.raises(AnalysisStoreUnavailable):
        store.create("o", "r", 3)


def test_eviction_drops_oldest():
    store = _store()
    store.MAX_ENTRIES = 2
    first = store.create("o", "r", 1)
    second = store.create("o", "r", 2)
    third = store.create("o", "r", 3)

    with pytest.raises(AnalysisNotFound):
        store.get(first["id"])
    assert store.get(second["id"])["issue_number"] == 2
    assert store.get(third["id"])["issue_number"] == 3
    assert store.find_reusable("o", "r", 1) is None


def test_adopt_anonymous_assigns_owner_and_keeps_payload():
    store = _store()
    created = store.create("o", "r", 3)
    store.mark_completed(
        created["id"],
        {
            "diagnosis": {"root_cause": "filter inverted"},
            "patch_proposal": {"status": "ok", "files": []},
            "patch_validation": {"status": "passed"},
            "patch_approved": True,
            "patch_delivery": {"status": "succeeded", "pr_number": 12},
        },
    )
    before = store.get(created["id"])

    adopted = store.adopt_anonymous(created["id"], "user-xyz")

    assert adopted["id"] == created["id"]
    assert adopted["user_id"] == "user-xyz"
    fetched = store.get(created["id"])
    assert fetched["user_id"] == "user-xyz"
    assert fetched["diagnosis"] == before["diagnosis"]
    assert fetched["patch_proposal"] == before["patch_proposal"]
    assert fetched["patch_validation"] == before["patch_validation"]
    assert fetched["patch_approved"] is True
    assert fetched["patch_delivery"] == before["patch_delivery"]
    assert store.find_reusable("o", "r", 3, user_id="user-xyz")["id"] == created["id"]
    assert store.find_reusable("o", "r", 3) is None


def test_adopt_anonymous_leaves_owned_and_foreign_records():
    store = _store()
    mine = store.create("o", "r", 3, user_id="alice")
    theirs = store.create("o", "r", 4, user_id="bob")

    same = store.adopt_anonymous(mine["id"], "alice")
    foreign = store.adopt_anonymous(theirs["id"], "alice")

    assert same["user_id"] == "alice"
    assert foreign["user_id"] == "bob"
    assert store.get(mine["id"])["user_id"] == "alice"
    assert store.get(theirs["id"])["user_id"] == "bob"


def test_adopt_anonymous_missing_returns_none():
    store = _store()
    assert store.adopt_anonymous("missing", "user-xyz") is None
    assert store.adopt_anonymous("", "user-xyz") is None
    assert store.adopt_anonymous("id", "") is None
