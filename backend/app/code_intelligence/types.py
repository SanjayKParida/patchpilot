"""
Plain records exchanged across the language boundary.

Every value a language adapter returns is one of these. Nothing
language-specific crosses the seam: an adapter may know about Dart
mixins or Python decorators internally, but what it hands back is a
path, a line and a string `kind` the core never interprets.

Frozen because the ContextBuilder deduplicates by value and must be
able to put these in sets.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True)
class Location:
    """Where a symbol is declared."""

    symbol: str
    path: str
    line: int

    # The adapter's own vocabulary — "class", "function", "def",
    # "interface". The core passes it through to the output and never
    # branches on it.
    kind: str


@dataclass(frozen=True)
class Span:
    """
    An inclusive, 1-based range of lines forming one whole declaration.

    `start_line` and `end_line` are inclusive so that
    `end_line - start_line + 1` is the line count, which is what the
    budget arithmetic needs.
    """

    path: str
    start_line: int
    end_line: int
    kind: str
    symbol: Optional[str] = None

    @property
    def line_count(self):
        return self.end_line - self.start_line + 1

    def overlaps(self, other, gap=0):
        """
        Whether two spans in the same file touch, or sit within `gap`
        lines of each other.

        Used when merging slices: two fragments a few lines apart read
        worse than one contiguous block.
        """

        if self.path != other.path:
            return False

        return (
            self.start_line - gap <= other.end_line
            and other.start_line - gap <= self.end_line
        )


@dataclass(frozen=True)
class Reference:
    """One place a symbol declared elsewhere is used."""

    path: str
    symbol: str
    line: int

    # How the symbol was used. The Dart adapter reports "state_test",
    # "type_argument" or "reference"; other languages will report
    # their own. The core may order by kind but never assigns meaning
    # to a particular value.
    kind: str


# Tiers, in priority order. Fill order and eviction order are the
# same list read forwards and backwards, so truncation always drops
# the least important context first.
TIER_DEFECT = 0
TIER_SUPPORTING = 1
TIER_DEPENDENCY = 2
TIER_CALLER = 3
TIER_CONTRACT = 4
TIER_TEST = 5
TIER_SECONDARY = 6

TIER_NAMES = {
    TIER_DEFECT: "defect",
    TIER_SUPPORTING: "supporting",
    TIER_DEPENDENCY: "dependency",
    TIER_CALLER: "caller",
    TIER_CONTRACT: "contract",
    TIER_TEST: "test",
    TIER_SECONDARY: "secondary",
}


@dataclass(frozen=True)
class ContextCandidate:
    """
    A piece of code the builder intends to include, before slicing.

    Separating candidate selection from slicing keeps the two failure
    modes apart: "we looked at the wrong code" and "we cut the right
    code badly".

    `reason` is not decoration. When a generated patch is wrong, the
    first question is why the model was shown that code, and this is
    the only field that answers it.
    """

    path: str
    tier: int
    reason: str
    symbol: Optional[str] = None
    line: Optional[int] = None

    @property
    def tier_name(self):
        return TIER_NAMES.get(self.tier, "unknown")

    @property
    def key(self):
        """
        Identity for deduplication.

        Symbol-anchored candidates are distinct within a file — a
        defect and a supporting declaration can share a file — so the
        symbol participates. File-level candidates collapse to the
        path.
        """

        return (self.path, self.symbol)


@dataclass(frozen=True)
class ContextSlice:
    """
    One contiguous range of a file actually shown to a patch generator.

    `truncated` is True when the range is a fallback window rather than
    a resolved declaration, not when a budget cut the defect site —
    that path records a warning and leaves the slice intact.
    """

    path: str
    start_line: int
    end_line: int
    tier: int
    reason: str
    symbols: Tuple[str, ...]
    content: str
    truncated: bool
    language: str = ""
    adapter: str = ""

    @property
    def line_count(self):
        if self.end_line < self.start_line:
            return 0
        return self.end_line - self.start_line + 1

    @property
    def tier_name(self):
        return TIER_NAMES.get(self.tier, "unknown")


@dataclass(frozen=True)
class FileRollup:
    path: str
    total_lines: int
    included_lines: int
    complete: bool


@dataclass(frozen=True)
class OmittedEntry:
    path: str
    reason: str


@dataclass(frozen=True)
class BudgetUsage:
    max_files: int
    files_used: int
    max_lines_total: int
    lines_used: int
    estimated_tokens: int
    over_budget: bool


@dataclass
class ContextPackage:
    """
    The artifact a patch generator consumes.

    `to_json()` is the determinism contract: the same inputs must
    produce the same bytes. Key order is sorted so a later field
    insertion cannot silently reshuffle snapshots.
    """

    slices: List[ContextSlice]
    files: List[FileRollup]
    omitted: List[OmittedEntry]
    warnings: List[str]
    budget: BudgetUsage
    language: str
    adapter: str
    issue: Any = None
    diagnosis: Any = None
    root_cause: Optional[dict] = None

    def to_dict(self):
        return {
            "adapter": self.adapter,
            "budget": asdict(self.budget),
            "diagnosis": self.diagnosis,
            "files": [asdict(item) for item in self.files],
            "issue": self.issue,
            "language": self.language,
            "omitted": [asdict(item) for item in self.omitted],
            "root_cause": self.root_cause,
            "slices": [asdict(item) for item in self.slices],
            "warnings": list(self.warnings),
        }

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
