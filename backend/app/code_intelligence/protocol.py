"""
The only language-aware seam in context building.

ContextBuilderService decides WHAT to include and HOW MUCH. An adapter
answers WHERE things are. If the core ever needs to know a file is
Dart, this boundary has been drawn in the wrong place.

Structural typing on purpose: adapters do not inherit from anything,
so the existing Dart classes need no modification, and a test fake
needs no import from this module.

Conservative resolution is part of the contract, not an implementation
detail. An adapter returns None for a symbol it cannot resolve
UNAMBIGUOUSLY. A missing location costs the builder some context; a
wrong one sends a patch generator at the wrong code.
"""

from typing import Any, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from app.code_intelligence.types import Location, Reference, Span


@runtime_checkable
class CodeIntelligence(Protocol):
    """Language-specific code intelligence for one file type."""

    # File extensions this adapter handles, e.g. (".dart",).
    extensions: Tuple[str, ...]

    # Short identifier recorded in the ContextPackage, e.g. "dart".
    name: str

    def build_index(self, files: Sequence[dict]) -> Any:
        """
        Build whatever this adapter needs to answer the rest.

        The return value is opaque to the core, which only stores it
        and passes it back. Called once per analysis; every other
        method must be cheap given the index.
        """
        ...

    def analyze_structure(self, files: Sequence[dict]) -> List[dict]:
        """
        Relationships between files, as `{source, target, relationship}`.

        These feed RepositoryGraph, which is language-agnostic and
        already knows how to traverse them. Adapters produce edges;
        the core walks them.
        """
        ...

    def declaration_of(
        self,
        symbol: str,
        index: Any,
    ) -> Optional[Location]:
        """
        Where `symbol` is declared, or None.

        None means unknown OR ambiguous. Both are failures to resolve
        and the caller treats them identically.
        """
        ...

    def declarations_in(
        self,
        path: str,
        index: Any,
    ) -> List[Location]:
        """Every symbol declared in one file, in declaration order."""
        ...

    def references_to(
        self,
        symbol: str,
        index: Any,
    ) -> List[Reference]:
        """
        Where `symbol` is used, excluding the file that declares it.

        This is symbol-level caller lookup, finer than the file-level
        graph: it distinguishes a file that reacts to a type from one
        that merely imports the file containing it.
        """
        ...

    def enclosing_span(
        self,
        path: str,
        line: int,
        index: Any,
    ) -> Optional[Span]:
        """
        The extent of the declaration containing `line`.

        None when no span can be determined confidently; the core then
        falls back to a fixed window. A wrong span silently truncates
        the code a patch is reasoned about, so guessing is worse than
        declining.
        """
        ...

    def header_end_line(
        self,
        path: str,
        content: str,
        index: Any,
    ) -> Optional[int]:
        """
        Last 1-based line of the file header (imports and similar).

        None when the file has no distinct header. The core always
        unions this range into the file's slices so a patch generator
        can see, and add, an import.
        """
        ...

    def is_test_file(self, path: str) -> bool:
        """Whether this path is test code by the language's convention."""
        ...


def supports(adapter: CodeIntelligence, path: str) -> bool:
    """Whether an adapter handles this path, by extension."""

    lowered = path.lower()

    return any(
        lowered.endswith(extension)
        for extension in adapter.extensions
    )
