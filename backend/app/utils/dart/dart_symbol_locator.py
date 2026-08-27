import re

from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer


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

    Conservative by design. A symbol declared in two files is
    ambiguous from a bare name, so it is dropped rather than guessed
    at — the same rule DartStructureAnalyzer applies to implements /
    extends. An unresolved symbol costs a navigation shortcut; a
    wrongly resolved one sends a developer to the wrong code.
    """

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
        # the paren to follow the name directly. Common names like
        # `build` will be declared in many files and are dropped by
        # the ambiguity rule rather than guessed at.
        (
            "function",
            re.compile(
                r"^\s*(?:@\w+\s+)*"
                r"(?:static\s+|final\s+|const\s+|late\s+)*"
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

        A symbol with more than one entry is ambiguous; resolve()
        drops those.
        """

        index = {}

        for file in files:

            path = self.structure._normalize_path(
                file.get("path", "")
            )

            if not path.endswith(".dart"):
                continue

            # Masked so a declaration inside a comment or string
            # literal never becomes a location.
            code = self.structure._mask_comments_and_strings(
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

            declarations = index.get(symbol)

            # Unknown, or declared in more than one place and
            # therefore not resolvable from the name alone.
            if not declarations or len(declarations) != 1:
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
