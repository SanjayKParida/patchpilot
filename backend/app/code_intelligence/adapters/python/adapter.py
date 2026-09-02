"""
Python implementation of CodeIntelligence.

Structural answers come from the standard-library AST. The adapter
is a thin protocol face over that analysis so ContextBuilder never
needs to know about Python.
"""

from app.code_intelligence.adapters.python.structure import (
    PythonStructure,
    is_python_path,
    is_test_path,
    normalize_path,
)
from app.code_intelligence.types import Location, Reference


class PythonIndex:
    """
    Precomputed Python snapshot. Opaque to the core; passed back
    into every later protocol call.
    """

    __slots__ = (
        "symbols",
        "usages",
        "usages_by_symbol",
        "declarations_by_path",
        "spans_by_path",
        "header_end_by_path",
        "contents",
        "relationships",
    )

    def __init__(
        self,
        symbols,
        usages,
        declarations_by_path,
        spans_by_path,
        header_end_by_path,
        contents,
        relationships,
    ):
        self.symbols = symbols
        self.usages = usages
        self.declarations_by_path = declarations_by_path
        self.spans_by_path = spans_by_path
        self.header_end_by_path = header_end_by_path
        self.contents = contents
        self.relationships = relationships
        self.usages_by_symbol = {}
        for usage in usages:
            self.usages_by_symbol.setdefault(
                usage["identifier"],
                [],
            ).append(usage)


class PythonCodeIntelligence:
    """Adapter over the standard-library Python AST."""

    extensions = (".py",)

    name = "python"

    has_intelligence = True

    def __init__(self, structure=None):
        self.structure = structure or PythonStructure()

    def build_index(self, files):
        py_files = [
            file
            for file in files
            if is_python_path(file.get("path") or "")
        ]
        analysis = self.structure.analyze(py_files)
        return PythonIndex(
            symbols=analysis["symbols"],
            usages=analysis["usages"],
            declarations_by_path=analysis["declarations_by_path"],
            spans_by_path=analysis["spans_by_path"],
            header_end_by_path=analysis["header_end_by_path"],
            contents=analysis["contents"],
            relationships=analysis["relationships"],
        )

    def analyze_structure(self, files):
        analysis = self.structure.analyze(files)
        return list(analysis["relationships"])

    def declaration_of(self, symbol, index):
        resolved = self.structure.resolve(symbol, index.symbols)
        if resolved is None:
            return None
        return Location(
            symbol=resolved["symbol"],
            path=resolved["path"],
            line=resolved["line"],
            kind=resolved["kind"],
        )

    def declarations_in(self, path, index):
        return list(
            index.declarations_by_path.get(normalize_path(path), ())
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

    def enclosing_span(self, path, line, index):
        return self.structure.enclosing_span(
            path,
            line,
            index.spans_by_path,
        )

    def header_end_line(self, path, content, index):
        normalized = normalize_path(path)
        if normalized in index.header_end_by_path:
            return index.header_end_by_path[normalized]
        analysis = self.structure.analyze([{"path": path, "content": content}])
        return analysis["header_end_by_path"].get(normalized)

    def is_test_file(self, path):
        return is_test_path(path)
