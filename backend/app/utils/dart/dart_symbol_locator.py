import re

from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer


# Words the function pattern used to accept as a "return type".
# `const Foo()` is a constructor (or a constructor call);
# `return Foo()` is a call. Neither is a declaration, and treating
# them as one is how a class and its constructor become two symbols,
# and how a test that constructs Foo makes the real Foo look
# ambiguous.
_NOT_A_RETURN_TYPE = (
    "return", "throw", "if", "for", "while", "do", "switch",
    "await", "yield", "assert", "case", "else", "catch",
    "new", "const", "final", "var", "late", "static",
    "factory", "typedef", "enum", "class", "mixin",
    "extension", "with", "is", "as", "on", "in",
)

_NOT_A_RETURN_TYPE_RE = "|".join(
    sorted(_NOT_A_RETURN_TYPE, key=len, reverse=True)
)


class DartSymbolLocator:
    """
    Resolves a Dart symbol name to where it is declared.

    This exists to keep locations out of the language model. A model
    can reliably NAME a symbol it was shown; it cannot reliably count
    lines, and will state a wrong line number with full confidence.
    So the model says "CarsLoading" and this says where CarsLoading
    actually is.

    That split is the same one the rest of the pipeline uses:
    deterministic code answers "where", the model answers "why".

    Conservative by design. A symbol declared in two *product* files
    is ambiguous from a bare name, so it is dropped rather than
    guessed at — the same rule DartStructureAnalyzer applies to
    implements / extends. An unresolved symbol costs a navigation
    shortcut; a wrongly resolved one sends a developer to the wrong
    code.

    Two collisions are not genuine ambiguity and are collapsed
    before that rule runs:

        1. A type and a constructor in the same file. The type is
           the declaration; the constructor is the same symbol.
        2. A product declaration and a test-file match. The product
           site is the one a developer would jump to.
    """

    TYPE_KINDS = frozenset({
        "class",
        "mixin",
        "enum",
        "typedef",
        "extension",
    })

    # Ordered: the first pattern that matches a line wins, so
    # `mixin class Foo` reports the more specific kind.
    DECLARATION_PATTERNS = (
        (
            "enum",
            re.compile(r"\benum\s+(?P<name>[A-Za-z_]\w*)\b"),
        ),
        (
            "typedef",
            re.compile(r"\btypedef\s+(?P<name>[A-Za-z_]\w*)\b"),
        ),
        (
            "extension",
            re.compile(r"\bextension\s+(?P<name>[A-Za-z_]\w*)\b"),
        ),
        (
            "mixin",
            re.compile(
                r"\bmixin\s+(?!class\b)(?P<name>[A-Za-z_]\w*)\b"
            ),
        ),
        (
            "class",
            re.compile(
                r"\b(?:abstract\s+|base\s+|final\s+|sealed\s+"
                r"|interface\s+)*"
                r"(?:mixin\s+)?class\s+(?P<name>[A-Za-z_]\w*)\b"
            ),
        ),
        # Method and function DECLARATIONS: a return type, then the
        # name, then an open paren.
        #
        # Root causes are often about a method — "getCars never
        # completes" — and that is the most specific location a
        # diagnosis can point at.
        #
        # Must not match a CALL. `dataSource.getCars()` is excluded by
        # requiring no leading dot, and `getCars.call()` by requiring
        # the paren to follow the name directly.
        #
        # Must not match a constructor or a constructor call.
        # `const Foo()` and `return Foo()` used to match because
        # `const` / `return` were accepted as the return type; they
        # are refused below. Common names like `build` will be
        # declared in many files and are dropped by the ambiguity
        # rule rather than guessed at.
        (
            "function",
            re.compile(
                r"^\s*(?:@\w+\s+)*"
                r"(?:static\s+|final\s+|const\s+|late\s+|factory\s+)*"
                rf"(?!(?:{_NOT_A_RETURN_TYPE_RE})\b)"
                r"(?:[A-Za-z_][\w<>,?\[\]\.]*\s+)"
                r"(?<![.\w])(?P<name>[A-Za-z_]\w*)\s*\("
            ),
        ),
    )

    def __init__(self, structure_analyzer=None):
        self.structure = (
            structure_analyzer or DartStructureAnalyzer()
        )

    # =========================================================
    # PUBLIC API
    # =========================================================

    def build_index(self, files):
        """
        Map every declared symbol to where it is declared.

        Returns
        -------
        dict
            {"CarsLoading": [{"path": ..., "line": 5, "kind": "class"}]}

        A symbol with more than one *product* entry after
        disambiguation is ambiguous; resolve() drops those.
        """

        index = {}

        for file in files:

            path = self.structure.normalize_path(
                file.get("path", "")
            )

            if not path.endswith(".dart"):
                continue

            # Masked so a declaration inside a comment or string
            # literal never becomes a location.
            code = self.structure.mask_source(
                file.get("content", "")
            )

            for line_number, line in enumerate(
                code.splitlines(),
                start=1,
            ):

                for kind, pattern in self.DECLARATION_PATTERNS:

                    match = pattern.search(line)

                    if not match:
                        continue

                    index.setdefault(
                        match.group("name"),
                        [],
                    ).append({
                        "path": path,
                        "line": line_number,
                        "kind": kind,
                    })

                    break

        return index

    def resolve(self, symbols, files=None, index=None):
        """
        Resolve symbol names to declaration sites.

        Unknown and ambiguous symbols are omitted, duplicates are
        collapsed, and input order is preserved so the most important
        symbol the model named stays first.

        Returns
        -------
        list
            [{"symbol", "path", "line", "kind"}]
        """

        if index is None:
            index = self.build_index(files or [])

        resolved = []
        seen = set()

        for symbol in symbols or []:

            if not isinstance(symbol, str):
                continue

            symbol = symbol.strip()

            if not symbol or symbol in seen:
                continue

            declarations = self._disambiguate(
                index.get(symbol) or []
            )

            # Unknown, or declared in more than one product place
            # and therefore not resolvable from the name alone.
            if len(declarations) != 1:
                continue

            seen.add(symbol)

            declaration = declarations[0]

            resolved.append({
                "symbol": symbol,
                "path": declaration["path"],
                "line": declaration["line"],
                "kind": declaration["kind"],
            })

        return resolved

    # =========================================================
    # DISAMBIGUATION
    # =========================================================

    def _disambiguate(self, declarations):
        """
        Collapse collisions that are not genuine ambiguity.

        A class and its constructor in the same file are one symbol.
        A product declaration beating a test-file match is the site
        a developer would open. Two product declarations of the same
        name are still ambiguous and stay untouched so resolve()
        drops them.
        """

        if not declarations:
            return []

        collapsed = self._prefer_type_in_same_file(declarations)
        return self._prefer_product_over_test(collapsed)

    def _prefer_type_in_same_file(self, declarations):
        by_path = {}

        for entry in declarations:
            by_path.setdefault(entry["path"], []).append(entry)

        collapsed = []

        for entries in by_path.values():
            types = [
                entry
                for entry in entries
                if entry["kind"] in self.TYPE_KINDS
            ]

            if types:
                collapsed.extend(types)
            else:
                collapsed.extend(entries)

        return collapsed

    def _prefer_product_over_test(self, declarations):
        product = [
            entry
            for entry in declarations
            if self._is_product_path(entry["path"])
        ]

        if product:
            return product

        return declarations

    @staticmethod
    def _is_product_path(path):
        """
        Same convention RepositorySearchService uses for Dart:
        anything under a test directory, or a `*_test.dart` file,
        is not product code.
        """

        normalized = path.replace("\\", "/").lower()

        if not normalized:
            return False

        prefixed = f"/{normalized}"

        if "/test/" in prefixed or "/tests/" in prefixed:
            return False

        if normalized.endswith("_test.dart"):
            return False

        return True
