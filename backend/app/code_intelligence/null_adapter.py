"""
Fallback adapter for files no registered language claims.

It satisfies the CodeIntelligence protocol with empty answers so the
core can still emit file-level slices from ranked paths. Guessing a
span or a relationship here would send a patch generator at invented
structure; declining is the contract.
"""

from typing import Any, List, Optional, Sequence


class NullCodeIntelligence:
    """File-level fallback. No symbols, no edges, no spans."""

    extensions = ()

    name = "unknown"

    def build_index(self, files: Sequence[dict]) -> Any:
        return {
            "files": [file.get("path") for file in files],
        }

    def analyze_structure(self, files: Sequence[dict]) -> List[dict]:
        return []

    def declaration_of(self, symbol: str, index: Any) -> Optional[object]:
        return None

    def declarations_in(self, path: str, index: Any) -> List:
        return []

    def references_to(self, symbol: str, index: Any) -> List:
        return []

    def enclosing_span(self, path: str, line: int, index: Any):
        return None

    def header_end_line(self, path: str, content: str, index: Any):
        return None

    def is_test_file(self, path: str) -> bool:
        return False
