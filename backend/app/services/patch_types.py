"""
Structured patch proposal types.

PatchGenerator emits these; PatchValidator applies them
against a full pre-fix snapshot. The representation is language-
agnostic text hunks, not a parsed AST or unified diff string.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional

STATUS_OK = "ok"
STATUS_INSUFFICIENT_CONTEXT = "insufficient_context"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_INVALID = "invalid"
STATUS_EMPTY = "empty"

VALID_STATUSES = frozenset({
    STATUS_OK,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_AMBIGUOUS,
    STATUS_INVALID,
    STATUS_EMPTY,
})


@dataclass(frozen=True)
class PatchHunk:
    """
    One contiguous replace edit in file coordinates.

    `old_text` must match the context-derived span for
    `[start_line, end_line]` after the same normalization
    ContextBuilder uses when extracting slice content.
    """

    start_line: int
    end_line: int
    old_text: str
    new_text: str


@dataclass(frozen=True)
class PatchFile:
    """All hunks touching one path."""

    path: str
    language: str
    hunks: tuple


@dataclass
class PatchProposal:
    """
    The artifact a patch validator consumes.

    `to_json()` is the determinism contract for tests and
    saved baselines — same validated inputs, same bytes.
    """

    status: str
    summary: str
    reasoning: str
    files: List[PatchFile] = field(default_factory=list)
    confidence: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "confidence": self.confidence,
            "errors": list(self.errors),
            "files": [
                {
                    "hunks": [asdict(hunk) for hunk in file.hunks],
                    "language": file.language,
                    "path": file.path,
                }
                for file in self.files
            ],
            "reasoning": self.reasoning,
            "status": self.status,
            "summary": self.summary,
            "warnings": list(self.warnings),
        }

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
