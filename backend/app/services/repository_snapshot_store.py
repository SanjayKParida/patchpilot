"""
In-memory cache of pinned repository snapshots.

Keyed by exact (owner, repo, commit_sha). Concurrent callers for the
same key share one GitHub download. Entries are copied on read so a
job cannot mutate a cached tree.
"""

import threading
from collections import OrderedDict


class RepositorySnapshotStore:
    MAX_ENTRIES = 16

    def __init__(self, max_entries=MAX_ENTRIES):
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._entries = OrderedDict()
        self._inflight = {}
        self._progress = {}
        self._active = {}

    @staticmethod
    def key(owner, repo, commit_sha):
        return (owner, repo, commit_sha)

    def inspect(self, owner, repo, commit_sha):
        """
        Non-blocking status for one SHA.

        Returns (status, files_or_none, progress) where progress is
        {downloaded, total, percent}. File lists are copies.
        """

        key = self.key(owner, repo, commit_sha)

        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                files = self._copy(self._entries[key])
                total = len(files)
                return "ready", files, self._progress_dict(total, total)

            if key in self._inflight:
                return "running", None, dict(
                    self._progress.get(key) or self._progress_dict(0, 0)
                )

            return "missing", None, self._progress_dict(0, 0)

    def active_sha(self, owner, repo):
        with self._lock:
            return self._active.get((owner, repo))

    def set_progress(self, owner, repo, commit_sha, downloaded, total):
        key = self.key(owner, repo, commit_sha)
        with self._lock:
            if key not in self._inflight:
                return
            self._progress[key] = self._progress_dict(downloaded, total)

    def get_or_fetch(self, owner, repo, commit_sha, loader, wait=True):
        """
        Return a cached snapshot, wait for an in-flight download, or
        run `loader` exactly once for this SHA.

        When `wait` is False and another caller already owns the
        download, returns ("running", None) without starting another.
        """

        key = self.key(owner, repo, commit_sha)

        while True:
            event = None
            started = False

            with self._lock:
                cached = self._entries.get(key)
                if cached is not None:
                    self._entries.move_to_end(key)
                    return "ready", self._copy(cached)

                if key in self._inflight:
                    if not wait:
                        return "running", None
                    event = self._inflight[key]
                else:
                    event = threading.Event()
                    self._inflight[key] = event
                    self._progress[key] = self._progress_dict(0, 0)
                    self._active[(owner, repo)] = commit_sha
                    started = True

            if not started:
                event.wait()
                continue

            try:
                files = loader()
            except Exception:
                with self._lock:
                    self._inflight.pop(key, None)
                    self._progress.pop(key, None)
                    if self._active.get((owner, repo)) == commit_sha:
                        self._active.pop((owner, repo), None)
                event.set()
                raise

            with self._lock:
                self._inflight.pop(key, None)
                self._progress.pop(key, None)
                self._entries[key] = self._copy(files)
                self._entries.move_to_end(key)
                self._active[(owner, repo)] = commit_sha
                self._evict_unlocked()

            event.set()
            return "ready", self._copy(files)

    def _evict_unlocked(self):
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    @staticmethod
    def _progress_dict(downloaded, total):
        downloaded = max(0, int(downloaded or 0))
        total = max(0, int(total or 0))
        percent = 100 if total and downloaded >= total else (
            int((downloaded * 100) / total) if total else 0
        )
        return {
            "downloaded": downloaded,
            "total": total,
            "percent": percent,
        }

    @staticmethod
    def _copy(files):
        return [dict(item) for item in files]
