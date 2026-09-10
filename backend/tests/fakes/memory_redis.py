"""In-memory Redis stand-in for tests. No network."""

import time


class MemoryRedis:
    def __init__(self, clock=None):
        self._kv = {}
        self._lists = {}
        self._now = clock or time.time

    def ping(self):
        return True

    def get(self, key):
        return self._value(key)

    def set(self, key, value, ex=None, **_kwargs):
        expires_at = None
        if ex is not None:
            expires_at = self._now() + float(ex)
        self._kv[key] = (value, expires_at)
        return True

    def getdel(self, key):
        value = self._value(key)
        if key in self._kv:
            del self._kv[key]
        return value

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self._kv:
                del self._kv[key]
                removed += 1
            if key in self._lists:
                del self._lists[key]
                removed += 1
        return removed

    def lpush(self, key, *values):
        lst = self._lists.setdefault(key, [])
        for value in reversed(values):
            lst.insert(0, value)
        return len(lst)

    def rpush(self, key, *values):
        lst = self._lists.setdefault(key, [])
        lst.extend(values)
        return len(lst)

    def lpop(self, key):
        lst = self._lists.get(key)
        if not lst:
            return None
        return lst.pop(0)

    def llen(self, key):
        return len(self._lists.get(key, []))

    def lrange(self, key, start, end):
        lst = self._lists.get(key, [])
        if not lst:
            return []
        if end == -1:
            return list(lst[start:])
        return list(lst[start : end + 1])

    def lrem(self, key, count, value):
        lst = self._lists.get(key)
        if not lst:
            return 0

        removed = 0
        if count == 0:
            kept = [item for item in lst if item != value]
            removed = len(lst) - len(kept)
            self._lists[key] = kept
            return removed

        if count > 0:
            kept = []
            for item in lst:
                if item == value and removed < count:
                    removed += 1
                    continue
                kept.append(item)
            self._lists[key] = kept
            return removed

        kept = []
        remaining = -count
        for item in reversed(lst):
            if item == value and remaining > 0:
                remaining -= 1
                removed += 1
                continue
            kept.append(item)
        kept.reverse()
        self._lists[key] = kept
        return removed

    def _value(self, key):
        item = self._kv.get(key)
        if item is None:
            return None
        if not isinstance(item, tuple):
            return item
        value, expires_at = item
        if expires_at is not None and self._now() >= expires_at:
            del self._kv[key]
            return None
        return value
