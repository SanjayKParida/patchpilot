"""
Context-anchored validation for patch hunks.

Rebuilds the line map PatchGenerator is allowed to edit from
ContextPackage slices only. No repository access, no language
parsers — the same splitlines/join normalization ContextBuilder
uses when materializing slice content.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional

from app.services.patch_types import PatchFile, PatchHunk

# Whole-file copies that already contain the one-character fix still
# need to bind to the snapshot span. "wrong" vs a real line stays
# well below this.
_NEAR_MATCH_RATIO = 0.97
_SPAN_LINE_SLACK = 2


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


def align_hunk(hunk, expected, line_map):
    """
    Bind a model hunk to the context span it actually edits.

    Models copy slice CONTENT into old_text and often take
    start_line/end_line from the slice LINES header. Copied old_text
    then includes markdown fences or a trailing blank line. This
    rewrites old_text to the authoritative slice span when the copy
    can be aligned; it does not invent a match from line numbers
    alone.
    """

    if expected is None or hunk is None:
        return None

    if normalize_text(hunk.old_text) == expected:
        return hunk

    candidates = _old_text_candidates(hunk.old_text)
    expected_n = _line_count(expected)

    for candidate, strip_fence, strip_edge in candidates:
        if not candidate:
            continue

        if candidate == expected:
            return _rewrite_hunk(
                hunk,
                hunk.start_line,
                hunk.end_line,
                expected,
                strip_fence,
                strip_edge,
            )

        located = _unique_span(line_map, candidate)
        if located is None:
            continue

        start, end, span_text = located
        if _new_text_fits_span(
            hunk.new_text,
            _line_count(candidate),
            slack=0,
        ):
            return _rewrite_hunk(
                hunk,
                start,
                end,
                span_text,
                strip_fence,
                strip_edge,
            )

    for candidate, strip_fence, strip_edge in candidates:
        if not candidate:
            continue

        if _near_match(candidate, expected) and _new_text_fits_span(
            hunk.new_text,
            expected_n,
        ):
            return _rewrite_hunk(
                hunk,
                hunk.start_line,
                hunk.end_line,
                expected,
                strip_fence,
                strip_edge,
            )

    return None


def validate_hunk(path, hunk, slices):
    """
    Validate one hunk against context slices.

    v1 accepts replace hunks only: start_line <= end_line, old_text
    must match the context-derived span after copy-artifact recovery.
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

    line_map = build_line_map(slices).get(path, {})
    aligned = align_hunk(hunk, expected, line_map)

    if aligned is None:
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
        hunk=aligned,
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

            recovered = outcome.hunk

            if any(
                hunk_ranges_overlap(existing, recovered)
                for existing in accepted
            ):
                result.errors.append(
                    f"overlapping hunks in {path}: "
                    f"{recovered.start_line}-{recovered.end_line}"
                )
                continue

            accepted.append(recovered)

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


def _old_text_candidates(text):
    """Distinct (text, stripped_fence, strip_edge) copies of old_text."""

    seen = set()
    out = []

    for strip_fence, strip_edge in (
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ):
        candidate = _transform_copied_text(text, strip_fence, strip_edge)
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append((candidate, strip_fence, strip_edge))

    return out


def _transform_copied_text(text, strip_fence, strip_edge):
    value = normalize_text(text)

    if strip_fence:
        value = _strip_markdown_fence(value)

    if strip_edge:
        value = _strip_edge_blank_lines(value)

    return value


def _strip_markdown_fence(text):
    lines = _lines(text)

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines)


def _strip_edge_blank_lines(text):
    lines = _lines(text)

    while lines and lines[0] == "":
        lines.pop(0)

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def _unique_span(line_map, needle_text):
    if not needle_text or not line_map:
        return None

    needle = needle_text.split("\n")
    matches = []

    for run in _contiguous_runs(line_map):
        texts = [line for _number, line in run]
        numbers = [number for number, _line in run]
        width = len(needle)

        if width > len(texts):
            continue

        for index in range(0, len(texts) - width + 1):
            if texts[index:index + width] != needle:
                continue

            start = numbers[index]
            end = numbers[index + width - 1]
            span_text = "\n".join(texts[index:index + width])
            matches.append((start, end, span_text))

    if len(matches) != 1:
        return None

    return matches[0]


def _contiguous_runs(line_map):
    runs = []
    run = []
    previous = None

    for number in sorted(line_map):
        if previous is not None and number != previous + 1:
            runs.append(run)
            run = []

        run.append((number, line_map[number]))
        previous = number

    if run:
        runs.append(run)

    return runs


def _near_match(actual, expected):
    if not actual or not expected:
        return False

    if abs(_line_count(actual) - _line_count(expected)) > _SPAN_LINE_SLACK:
        return False

    return SequenceMatcher(None, actual, expected).ratio() >= _NEAR_MATCH_RATIO


def _new_text_fits_span(new_text, span_lines, slack=_SPAN_LINE_SLACK):
    """
    Recovered replacements must stay a same-span edit.

    Trusting a 1-32 range while new_text is a single line would
    replace the whole file. Unique-span retargeting uses the
    matched old_text line count, not the claimed header.
    """

    new_n = _line_count(_strip_edge_blank_lines(_strip_markdown_fence(new_text)))
    return abs(new_n - span_lines) <= slack


def _rewrite_hunk(hunk, start_line, end_line, old_text, strip_fence, strip_edge):
    new_text = _transform_copied_text(
        hunk.new_text,
        strip_fence,
        strip_edge,
    )

    if (
        hunk.start_line == start_line
        and hunk.end_line == end_line
        and hunk.old_text == old_text
        and hunk.new_text == new_text
    ):
        return hunk

    return PatchHunk(
        start_line=start_line,
        end_line=end_line,
        old_text=old_text,
        new_text=new_text,
    )


def _lines(text):
    if not text:
        return []
    return normalize_text(text).split("\n")


def _line_count(text):
    if not text:
        return 0
    return len(_lines(text))


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
