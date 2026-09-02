"""
Dart implementation of CodeIntelligence.

Deliberately thin. Every capability here already exists and is
unit-tested elsewhere in the Dart pack; this class only presents it
through the language-agnostic protocol. It adds no analysis of its
own, so wrapping cannot change observable Dart behaviour — the parity
tests exist to keep it that way.

The one exception is `enclosing_span`, which no existing component can
answer. It is stubbed to None here and implemented in a later step; a
None span is already a supported case in the builder, so the adapter
is usable before that lands.
"""

from app.code_intelligence.types import Location, Reference, Span
from app.services.repository_search_service import RepositorySearchService
from app.utils.dart.dart_span_locator import DartSpanLocator
from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer
from app.utils.dart.dart_symbol_locator import DartSymbolLocator
from app.utils.dart.dart_usage_analyzer import DartUsageAnalyzer


class DartIndex:
    """
    Everything the adapter precomputes for one repository snapshot.

    Held as one object so the core can treat it as opaque and pass it
    back without knowing what is inside.
    """

    __slots__ = (
        "symbols",
        "usages",
        "usages_by_symbol",
        "declarations_by_path",
        "contents",
    )

    def __init__(self, symbols, usages, contents):
        self.symbols = symbols
        self.usages = usages
        self.contents = contents

        # Symbol -> the places that use it. The usage analyzer keys by
        # the CONSUMING file, which answers "what does this file use".
        # Context building asks the opposite question, so it is
        # inverted once here rather than scanned per lookup.
        self.usages_by_symbol = {}

        for usage in usages:
            self.usages_by_symbol.setdefault(
                usage["identifier"],
                [],
            ).append(usage)

        # Path -> declarations, in line order.
        self.declarations_by_path = {}

        for symbol, entries in symbols.items():
            for entry in entries:
                self.declarations_by_path.setdefault(
                    entry["path"],
                    [],
                ).append(
                    Location(
                        symbol=symbol,
                        path=entry["path"],
                        line=entry["line"],
                        kind=entry["kind"],
                    )
                )

        for declarations in self.declarations_by_path.values():
            declarations.sort(key=lambda item: (item.line, item.symbol))


class DartCodeIntelligence:
    """Adapter over the existing Dart analyzers."""

    extensions = (".dart",)

    name = "dart"

    has_intelligence = True

    def __init__(
        self,
        structure_analyzer=None,
        symbol_locator=None,
        usage_analyzer=None,
        search_service=None,
        span_locator=None,
    ):
        self.structure = structure_analyzer or DartStructureAnalyzer()

        self.symbols = symbol_locator or DartSymbolLocator(
            structure_analyzer=self.structure,
        )

        self.usage = usage_analyzer or DartUsageAnalyzer(
            structure_analyzer=self.structure,
        )

        self.search = search_service or RepositorySearchService()

        # Injectable so a caller can disable spans entirely by
        # passing a locator that always declines; the builder already
        # treats None as "fall back to a fixed window".
        self.span_locator = span_locator or DartSpanLocator(
            structure_analyzer=self.structure,
        )

    # =========================================================
    # INDEXING
    # =========================================================

    def build_index(self, files):
        dart_files = [
            file
            for file in files
            if self.structure.normalize_path(
                file.get("path", "")
            ).endswith(".dart")
        ]

        return DartIndex(
            symbols=self.symbols.build_index(dart_files),
            usages=self.usage.analyze_repository(dart_files),
            contents={
                self.structure.normalize_path(file.get("path", "")):
                    file.get("content", "")
                for file in dart_files
            },
        )

    def analyze_structure(self, files):
        return self.structure.analyze_repository(files)

    # =========================================================
    # SYMBOLS
    # =========================================================

    def declaration_of(self, symbol, index):
        resolved = self.symbols.resolve(
            [symbol],
            index=index.symbols,
        )

        if not resolved:
            return None

        declaration = resolved[0]

        return Location(
            symbol=declaration["symbol"],
            path=declaration["path"],
            line=declaration["line"],
            kind=declaration["kind"],
        )

    def declarations_in(self, path, index):
        return list(
            index.declarations_by_path.get(
                self.structure.normalize_path(path),
                (),
            )
        )

    def references_to(self, symbol, index):
        return [
            Reference(
                path=usage["path"],
                symbol=usage["identifier"],
                line=usage["line"],
                kind=usage["kind"],
            )
            for usage in index.usages_by_symbol.get(symbol, ())
        ]

    # =========================================================
    # SLICING
    # =========================================================

    def enclosing_span(self, path, line, index):
        if self.span_locator is None:
            return None

        normalized = self.structure.normalize_path(path)

        content = index.contents.get(normalized)

        if content is None:
            return None

        return self.span_locator.enclosing_span(
            normalized,
            line,
            content,
        )

    def header_end_line(self, path, content, index):
        last = None

        for number, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if (
                stripped.startswith("import ")
                or stripped.startswith("export ")
                or stripped.startswith("part ")
                or stripped.startswith("library ")
            ):
                last = number

        return last

    # =========================================================
    # CONVENTIONS
    # =========================================================

    def is_test_file(self, path):
        # is_candidate_file answers the inverse: whether a file is
        # PRODUCTION code. Reused rather than restated so the whole
        # pipeline keeps one definition of a test file.
        return not self.search.is_candidate_file({"path": path})
