"""
Context-anchored validation for patch hunks.

Rebuilds the line map PatchGenerator is allowed to edit from
ContextPackage slices only. No repository access, no language
parsers — the same splitlines/join normalization ContextBuilder
uses when materializing slice content.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from app.services.patch_types import PatchFile, PatchHunk


@dataclass
class HunkValidation:
    """Outcome of validating one hunk against context slices."""

    hunk: PatchHunk
    path: str
    language: str
    accepted: bool
    error: Optional[str] = None


@dataclass
class AnchoredValidation:
    """Aggregated result of validating a batch of hunks."""

    files: List[PatchFile] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def normalize_text(text):
    """
    Match ContextBuilder slice extraction.

    Empty input stays empty; otherwise splitlines() joined by \\n.
    """

    if text is None:
        return ""

    if text == "":
        return ""

    return "\n".join(text.splitlines())


def build_line_map(slices):
    """
    Map path -> {1-based line number -> line text}.

    When slices overlap, the first slice encountered in input order
    wins for a given line. Callers should pass slices in stable order.
    """

    by_path = {}

    for item in slices:
        path = _slice_path(item)
        content = _slice_content(item)
        start = _slice_start(item)
        end = _slice_end(item)

        if end < start:
            continue

        bucket = by_path.setdefault(path, {})

        for offset, line in enumerate(content.splitlines()):
            bucket[start + offset] = line

    return by_path


def covered_lines(slices, path):
    """1-based line numbers shown for one path."""

    covered = set()

    for item in slices:
        if _slice_path(item) != path:
            continue

        start = _slice_start(item)
        end = _slice_end(item)

        if end < start:
            continue

        covered.update(range(start, end + 1))

    return covered


def lines_fully_covered(path, start_line, end_line, slices):
    """Whether every line in the inclusive range appears in context."""

    if end_line < start_line:
        return False

    covered = covered_lines(slices, path)
    needed = set(range(start_line, end_line + 1))
    return needed.issubset(covered)


def expected_old_text(path, start_line, end_line, slices):
    """
    Reconstruct the text ContextBuilder would show for a range.

    Returns None when any line in the range is missing from slices.
    """

    if end_line < start_line:
        return None

    if not lines_fully_covered(path, start_line, end_line, slices):
        return None

    line_map = build_line_map(slices)
    bucket = line_map.get(path, {})
    lines = [bucket[line] for line in range(start_line, end_line + 1)]
    return "\n".join(lines)


def hunk_ranges_overlap(left, right):
    """Whether two inclusive line ranges touch or overlap."""

    return (
        left.start_line <= right.end_line
        and right.start_line <= left.end_line
    )


def validate_hunk(path, hunk, slices):
    """
    Validate one hunk against context slices.

    v1 accepts replace hunks only: start_line <= end_line, old_text
    must exactly match the context-derived span.
    """

    language = _language_for_path(slices, path)

    if path not in {_slice_path(item) for item in slices}:
        return HunkValidation(
            hunk=hunk,
            path=path,
            language=language,
            accepted=False,
            error=f"path not in context: {path}",
        )

    if hunk.end_line < hunk.start_line:
        return HunkValidation(
            hunk=hunk,
            path=path,
            language=language,
            accepted=False,
            error=(
                f"invalid hunk range for {path}: "
                f"{hunk.start_line}-{hunk.end_line}"
            ),
        )

    expected = expected_old_text(
        path,
        hunk.start_line,
        hunk.end_line,
        slices,
    )

    if expected is None:
        return HunkValidation(
            hunk=hunk,
            path=path,
            language=language,
            accepted=False,
            error=(
                f"lines {hunk.start_line}-{hunk.end_line} in {path} "
                f"are not fully covered by context slices"
            ),
        )

    actual = normalize_text(hunk.old_text)

    if actual != expected:
        return HunkValidation(
            hunk=hunk,
            path=path,
            language=language,
            accepted=False,
            error=(
                f"old_text mismatch for {path}:"
                f"{hunk.start_line}-{hunk.end_line}"
            ),
        )

    return HunkValidation(
        hunk=hunk,
        path=path,
        language=language,
        accepted=True,
    )


def validate_hunks(hunks_by_path, slices):
    """
    Validate hunks grouped by path.

    `hunks_by_path` is an ordered mapping path -> list of PatchHunk.
    Accepted hunks are sorted by start_line; overlaps within a file
    are rejected.
    """

    result = AnchoredValidation()
    accepted_by_path = {}
    path_order = []

    for path, hunks in hunks_by_path.items():
        accepted = []

        for hunk in hunks:
            outcome = validate_hunk(path, hunk, slices)

            if not outcome.accepted:
                result.errors.append(outcome.error)
                continue

            if any(
                hunk_ranges_overlap(existing, hunk)
                for existing in accepted
            ):
                result.errors.append(
                    f"overlapping hunks in {path}: "
                    f"{hunk.start_line}-{hunk.end_line}"
                )
                continue

            accepted.append(hunk)

        if accepted:
            accepted.sort(key=lambda item: item.start_line)
            accepted_by_path[path] = (
                path,
                _language_for_path(slices, path),
                tuple(accepted),
            )
            path_order.append(path)

    for path in path_order:
        file_path, language, hunks = accepted_by_path[path]
        result.files.append(
            PatchFile(
                path=file_path,
                language=language,
                hunks=hunks,
            )
        )

    return result


def _language_for_path(slices, path):
    for item in slices:
        if _slice_path(item) == path:
            return _slice_language(item)
    return ""


def _slice_path(item):
    return item["path"] if isinstance(item, dict) else item.path


def _slice_content(item):
    return item["content"] if isinstance(item, dict) else item.content


def _slice_start(item):
    return item["start_line"] if isinstance(item, dict) else item.start_line


def _slice_end(item):
    return item["end_line"] if isinstance(item, dict) else item.end_line


def _slice_language(item):
    if isinstance(item, dict):
        return item.get("language") or ""
    return item.language or ""
