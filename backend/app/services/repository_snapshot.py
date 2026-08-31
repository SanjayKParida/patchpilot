"""
Prepare a pinned repository snapshot and derive ranking source files.

Downloads go through GithubService.get_repository_tracked_files.
Language-filtered source files are sliced from that snapshot so
ranking keeps the same extension set without a second GitHub walk.
"""

import logging
import time

from app.errors import SnapshotPreparationInProgress

logger = logging.getLogger(__name__)

# Same extensions GithubService.get_repository_source_files uses.
SOURCE_FILE_EXTENSIONS = (".dart", ".py", ".js", ".ts", ".java", ".kt")


def source_files_from_tracked(tracked):
    """Language-filtered files ranking already expects."""

    return [
        file
        for file in tracked
        if str(file.get("path") or "").endswith(SOURCE_FILE_EXTENSIONS)
    ]


def prepare_repository_snapshot(
    github,
    store,
    owner,
    repo,
    ref=None,
    wait=True,
):
    """
    Resolve `ref` to a SHA and return the tracked snapshot for it.

    Invalid explicit refs fail in resolve_commit; HEAD is never
    substituted. Concurrent callers for the same SHA share one
    download. When `wait` is False and a download is already running,
    raises SnapshotPreparationInProgress.
    """

    started = time.monotonic()
    commit_sha = github.resolve_commit(owner, repo, ref)
    logger.info(
        "snapshot_prepare_start owner=%s repo=%s sha=%s",
        owner,
        repo,
        commit_sha,
    )

    def load():
        logger.info(
            "snapshot_github_download owner=%s repo=%s sha=%s",
            owner,
            repo,
            commit_sha,
        )

        def on_progress(downloaded, total):
            store.set_progress(owner, repo, commit_sha, downloaded, total)

        return github.get_repository_tracked_files(
            owner,
            repo,
            ref=commit_sha,
            on_progress=on_progress,
        )

    status, files = store.get_or_fetch(
        owner,
        repo,
        commit_sha,
        load,
        wait=wait,
    )

    if status == "running":
        logger.info(
            "snapshot_prepare_end owner=%s repo=%s sha=%s status=running "
            "elapsed_ms=%s",
            owner,
            repo,
            commit_sha,
            int((time.monotonic() - started) * 1000),
        )
        raise SnapshotPreparationInProgress(
            "Repository snapshot preparation is already running "
            f"for {owner}/{repo} at this commit"
        )

    logger.info(
        "snapshot_prepare_end owner=%s repo=%s sha=%s status=%s "
        "file_count=%s elapsed_ms=%s",
        owner,
        repo,
        commit_sha,
        status,
        len(files or []),
        int((time.monotonic() - started) * 1000),
    )
    return commit_sha, files, status
