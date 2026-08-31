"""
Full-file patch application.

Matches and replaces hunks against a complete pre-fix file map.
Pure: no subprocess, no temp directories, no mutation of the
caller's original mapping.
"""

from pathlib import PurePosixPath

from app.services.patch_context import hunk_ranges_overlap, normalize_text
from app.services.patch_types import PatchHunk, PatchProposal, STATUS_OK
from app.services.patch_validation_types import FileApplyResult


class ApplyError(Exception):
    """A hunk could not be applied to the snapshot."""


def files_to_map(files):
    """
    Accept dict[path, content] or a list of {path, content} entries.
    """

    if files is None:
        return {}

    if isinstance(files, dict):
        return dict(files)

    mapping = {}

    for item in files:
        if isinstance(item, dict):
            path = item.get("path")
            content = item.get("content") or ""
        else:
            path = item.path
            content = item.content or ""

        if path:
            mapping[path] = content

    return mapping


def proposal_files(proposal):
    """Yield (path, language, hunks) from a PatchProposal or dict."""

    if isinstance(proposal, PatchProposal):
        for item in proposal.files:
            yield item.path, item.language, list(item.hunks)
        return

    proposal = proposal or {}

    for item in proposal.get("files") or []:
        path = item.get("path") or ""
        language = item.get("language") or ""
        hunks = []

        for hunk in item.get("hunks") or []:
            hunks.append(
                PatchHunk(
                    start_line=hunk["start_line"],
                    end_line=hunk["end_line"],
                    old_text=hunk.get("old_text") or "",
                    new_text=hunk.get("new_text") or "",
                )
            )

        yield path, language, hunks


def proposal_status(proposal):
    if isinstance(proposal, PatchProposal):
        return proposal.status

    return (proposal or {}).get("status")


def is_safe_relative_path(path, allowed_prefixes=()):
    """
    Reject empty, absolute, NUL, and parent-directory paths.

    Paths are treated as POSIX-style repository paths.
    """

    if not path or not isinstance(path, str):
        return False

    if "\x00" in path:
        return False

    if path.startswith("/") or path.startswith("\\"):
        return False

    # Windows drive / UNC
    if len(path) >= 2 and path[1] == ":":
        return False

    candidate = path.replace("\\", "/")

    if candidate.startswith("/") or candidate.startswith("//"):
        return False

    parts = PurePosixPath(candidate).parts

    if not parts or parts[0] == "..":
        return False

    if any(part == ".." or part == "" for part in parts):
        return False

    if allowed_prefixes:
        if not any(
            candidate == prefix.rstrip("/")
            or candidate.startswith(prefix.rstrip("/") + "/")
            for prefix in allowed_prefixes
        ):
            return False

    return True


def expected_old_text_from_content(content, start_line, end_line):
    """
    Reconstruct the span at 1-based inclusive file coordinates.

    Returns None when the range is outside the file.
    """

    if end_line < start_line:
        return None

    lines = (content or "").splitlines()

    if start_line < 1 or end_line > len(lines):
        return None

    return "\n".join(lines[start_line - 1:end_line])


def apply_hunks_to_content(content, hunks):
    """
    Apply replace hunks in reverse start_line order.

    Trailing newline: if the original ended with \\n, the result does
    too; otherwise it does not. Line splitting uses splitlines(), the
    same rule as ContextBuilder / PatchGenerator.
    """

    original = content or ""
    keep_trailing_newline = original.endswith("\n")
    lines = original.splitlines()

    ordered = sorted(
        hunks,
        key=lambda hunk: hunk.start_line,
        reverse=True,
    )

    for hunk in ordered:
        if hunk.end_line < hunk.start_line:
            raise ApplyError(
                f"invalid hunk range {hunk.start_line}-{hunk.end_line}"
            )

        if hunk.start_line < 1 or hunk.end_line > len(lines):
            raise ApplyError(
                f"hunk {hunk.start_line}-{hunk.end_line} is outside "
                f"the file ({len(lines)} lines)"
            )

        expected = "\n".join(lines[hunk.start_line - 1:hunk.end_line])
        actual = normalize_text(hunk.old_text)

        if actual != expected:
            raise ApplyError(
                f"old_text mismatch at lines "
                f"{hunk.start_line}-{hunk.end_line}"
            )

        replacement = normalize_text(hunk.new_text)
        new_lines = replacement.splitlines() if replacement else []
        lines[hunk.start_line - 1:hunk.end_line] = new_lines

    result = "\n".join(lines)

    if keep_trailing_newline and (result or original == "\n"):
        result += "\n"

    return result


def check_proposal_structure(proposal, file_map, allowed_prefixes=()):
    """
    Structural checks before any apply.

    Returns (errors, file_results) — empty errors means the proposal
    may be applied against the snapshot.
    """

    errors = []
    file_results = []

    status = proposal_status(proposal)

    if status != STATUS_OK:
        errors.append(
            f"proposal status is {status or 'missing'}, not ok"
        )
        return errors, file_results

    entries = list(proposal_files(proposal))

    if not entries:
        errors.append("proposal has no files")
        return errors, file_results

    seen_paths = []

    for path, _language, hunks in entries:
        if not is_safe_relative_path(path, allowed_prefixes):
            errors.append(f"unsafe path: {path}")
            file_results.append(
                FileApplyResult(
                    path=path or "",
                    applied=False,
                    error=f"unsafe path: {path}",
                )
            )
            continue

        if not hunks:
            errors.append(f"no hunks for {path}")
            file_results.append(
                FileApplyResult(
                    path=path,
                    applied=False,
                    error=f"no hunks for {path}",
                )
            )
            continue

        range_error = None

        for hunk in hunks:
            if hunk.end_line < hunk.start_line:
                range_error = (
                    f"invalid hunk range for {path}: "
                    f"{hunk.start_line}-{hunk.end_line}"
                )
                break

        if range_error:
            errors.append(range_error)
            file_results.append(
                FileApplyResult(
                    path=path,
                    applied=False,
                    error=range_error,
                )
            )
            continue

        overlap = False

        for index, hunk in enumerate(hunks):
            for other in hunks[:index]:
                if hunk_ranges_overlap(hunk, other):
                    overlap = True
                    message = (
                        f"overlapping hunks in {path}: "
                        f"{hunk.start_line}-{hunk.end_line}"
                    )
                    errors.append(message)
                    file_results.append(
                        FileApplyResult(
                            path=path,
                            applied=False,
                            error=message,
                        )
                    )
                    break
            if overlap:
                break

        if overlap:
            continue

        seen_paths.append((path, hunks))

    if errors:
        return errors, file_results

    for path, hunks in seen_paths:
        if path not in file_map:
            message = f"path not in snapshot: {path}"
            errors.append(message)
            file_results.append(
                FileApplyResult(
                    path=path,
                    applied=False,
                    error=message,
                )
            )

    return errors, file_results


def apply_proposal_to_map(proposal, file_map, allowed_prefixes=()):
    """
    Return (patched_map, file_results, errors).

    `file_map` is not mutated. On any apply failure, patched_map is
    empty and no partial result is returned.
    """

    patched = dict(file_map)
    file_results = []
    errors = []

    structure_errors, structure_files = check_proposal_structure(
        proposal,
        file_map,
        allowed_prefixes=allowed_prefixes,
    )

    if structure_errors:
        return {}, structure_files, structure_errors

    for path, _language, hunks in proposal_files(proposal):
        content = file_map[path]

        for hunk in hunks:
            expected = expected_old_text_from_content(
                content,
                hunk.start_line,
                hunk.end_line,
            )
            actual = normalize_text(hunk.old_text)

            if expected is None:
                message = (
                    f"lines {hunk.start_line}-{hunk.end_line} in "
                    f"{path} are outside the file"
                )
                errors.append(message)
                file_results.append(
                    FileApplyResult(
                        path=path,
                        applied=False,
                        error=message,
                    )
                )
                return {}, file_results, errors

            if actual != expected:
                message = (
                    f"old_text mismatch for {path}:"
                    f"{hunk.start_line}-{hunk.end_line}"
                )
                errors.append(message)
                file_results.append(
                    FileApplyResult(
                        path=path,
                        applied=False,
                        error=message,
                    )
                )
                return {}, file_results, errors

        try:
            patched[path] = apply_hunks_to_content(content, hunks)
        except ApplyError as exc:
            message = f"{path}: {exc}"
            errors.append(message)
            file_results.append(
                FileApplyResult(
                    path=path,
                    applied=False,
                    error=message,
                )
            )
            return {}, file_results, errors

        file_results.append(
            FileApplyResult(
                path=path,
                applied=True,
                hunks_applied=len(hunks),
            )
        )

    return patched, file_results, errors
