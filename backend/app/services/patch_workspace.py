"""
Isolated workspace for patch application.

Writes a snapshot file map into a temporary directory. Never mutates
the caller's mapping. Cleanup is always attempted by the caller via
`cleanup()`.
"""

import os
import shutil
import tempfile
from pathlib import Path


class WorkspaceError(Exception):
    """The snapshot could not be materialized safely."""


def _resolved_under(root, relative):
    """
    Resolve relative against root and require it stays inside root.
    """

    candidate = (root / relative).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(
            f"path escapes workspace: {relative}"
        ) from exc

    return candidate


def materialize(file_map, root=None):
    """
    Write `file_map` into a new directory.

    Returns the absolute workspace root. Files are written as regular
    files from snapshot content — no symlink following.
    """

    if root is None:
        root = Path(tempfile.mkdtemp(prefix="patchpilot-validate-"))
    else:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)

    root = root.resolve()

    for path, content in sorted((file_map or {}).items()):
        relative = Path(path.replace("\\", "/"))

        if relative.is_absolute():
            raise WorkspaceError(f"absolute path in snapshot: {path}")

        destination = _resolved_under(root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content or "", encoding="utf-8")

    return root


def write_files(root, file_map):
    """Overwrite paths in an existing workspace from a file map."""

    root = Path(root).resolve()

    for path, content in (file_map or {}).items():
        relative = Path(path.replace("\\", "/"))
        destination = _resolved_under(root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content or "", encoding="utf-8")


def cleanup(root):
    """
    Remove a workspace directory.

    Returns True on success. Missing roots count as cleaned.
    """

    if root is None:
        return True

    path = Path(root)

    if not path.exists():
        return True

    shutil.rmtree(path, ignore_errors=False)
    return not path.exists()
