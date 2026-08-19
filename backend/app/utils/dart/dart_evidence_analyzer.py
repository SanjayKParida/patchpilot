import re


class DartEvidenceAnalyzer:
    """
    Extracts language-specific evidence from Dart source files.

    This analyzer does NOT decide whether a file is relevant.
    It only identifies evidence that can later be scored by the
    RepositoryRankingService.

    Evidence priority:

        class declaration
            >
        function / method declaration
            >
        property / method access
            >
        annotation
            >
        generic identifier

    The analyzer deliberately avoids trying to fully parse Dart.
    It uses conservative lexical patterns so that generic matches
    do not overwhelm stronger evidence.
    """

    # ---------------------------------------------------------
    # Dart lexical patterns
    # ---------------------------------------------------------

    IDENTIFIER_PATTERN = re.compile(
        r"\b[A-Za-z_][A-Za-z0-9_]*\b"
    )

    CLASS_PATTERN = re.compile(
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)"
    )

    FUNCTION_PATTERN = re.compile(
        r"""
        (?:
            Future
            |
            void
            |
            dynamic
            |
            bool
            |
            int
            |
            double
            |
            String
            |
            [A-Za-z_][A-Za-z0-9_<>,?\[\]]*
        )
        \s+
        ([A-Za-z_][A-Za-z0-9_]*)
        \s*\(
        """,
        re.VERBOSE,
    )

    PROPERTY_ACCESS_PATTERN = re.compile(
        r"\b[A-Za-z_][A-Za-z0-9_]*\."
        r"([A-Za-z_][A-Za-z0-9_]*)"
    )

    ANNOTATION_PATTERN = re.compile(
        r"@\s*([A-Za-z_][A-Za-z0-9_]*)"
    )

    # Dart single-line comments.
    SINGLE_LINE_COMMENT_PATTERN = re.compile(
        r"^\s*//"
    )

    # Dart block-comment markers.
    BLOCK_COMMENT_START_PATTERN = re.compile(
        r"^\s*/\*"
    )

    BLOCK_COMMENT_END_PATTERN = re.compile(
        r"^\s*\*/"
    )

    # ---------------------------------------------------------
    # Evidence strengths
    # ---------------------------------------------------------

    EVIDENCE_STRENGTHS = {
        "class": 1.0,
        "function": 0.9,
        "property_access": 0.7,
        "annotation": 0.7,
        "identifier": 0.2,
    }

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def analyze_file(self, file, signals):
        """
        Analyze one Dart file against the supplied issue signals.

        Parameters
        ----------
        file:
            Repository file dictionary. Expected to contain:

                {
                    "path": "...",
                    "content": "...",
                    ...
                }

        signals:
            List of issue signals:

                [
                    {
                        "term": "firebase",
                        "type": "technology"
                    },
                    ...
                ]

        Returns
        -------
        list
            Evidence dictionaries.

        Example:

            {
                "file": file,
                "evidence_type": "class",
                "concept": "firebase",
                "strength": 1.0,
                "line": 12,
                "identifier": "FirebaseCarDataSource"
            }
        """

        evidence = []

        content = file.get(
            "content",
            ""
        )

        signal_terms = self._normalize_signal_terms(
            signals
        )

        if not signal_terms:
            return evidence

        lines = content.splitlines()

        inside_block_comment = False

        for line_number, line in enumerate(
            lines,
            start=1
        ):

            stripped = line.strip()

            if not stripped:
                continue

            # -------------------------------------------------
            # Block comment handling
            # -------------------------------------------------

            if inside_block_comment:

                if self.BLOCK_COMMENT_END_PATTERN.match(
                    stripped
                ):
                    inside_block_comment = False

                continue

            if self.BLOCK_COMMENT_START_PATTERN.match(
                stripped
            ):

                # If the comment starts and ends on the same line,
                # it does not affect subsequent lines.
                comment_start = line.find("/*")
                comment_end = line.find(
                    "*/",
                    comment_start + 2
                )

                if comment_end == -1:
                    inside_block_comment = True

                continue

            # -------------------------------------------------
            # Single-line comments
            # -------------------------------------------------

            if self.SINGLE_LINE_COMMENT_PATTERN.match(
                stripped
            ):
                continue

            # -------------------------------------------------
            # Remove inline comments before lexical analysis.
            #
            # Example:
            #
            #   FirebaseFirestore.instance; // firebase
            #
            # The comment should not create additional evidence.
            # -------------------------------------------------

            code_line = self._remove_inline_comment(
                line
            )

            if not code_line.strip():
                continue

            # -------------------------------------------------
            # Track identifiers that already received stronger
            # declaration evidence.
            #
            # This prevents:
            #
            #   class CarBloc
            #
            # from becoming both:
            #
            #   class evidence
            #   identifier evidence
            # -------------------------------------------------

            declared_identifiers = set()

            # -------------------------------------------------
            # Class declarations
            # -------------------------------------------------

            class_match = self.CLASS_PATTERN.search(
                code_line
            )

            if class_match:

                class_name = class_match.group(1)

                declared_identifiers.add(
                    class_name
                )

                self._match_identifier(
                    evidence=evidence,
                    file=file,
                    identifier=class_name,
                    signal_terms=signal_terms,
                    evidence_type="class",
                    strength=self.EVIDENCE_STRENGTHS["class"],
                    line_number=line_number
                )

            # -------------------------------------------------
            # Function / method declarations
            # -------------------------------------------------

            function_match = self.FUNCTION_PATTERN.search(
                code_line
            )

            if function_match:

                function_name = function_match.group(1)

                # Avoid accidentally treating Dart keywords as
                # function declarations.
                if not self._is_dart_keyword(
                    function_name
                ):

                    declared_identifiers.add(
                        function_name
                    )

                    self._match_identifier(
                        evidence=evidence,
                        file=file,
                        identifier=function_name,
                        signal_terms=signal_terms,
                        evidence_type="function",
                        strength=self.EVIDENCE_STRENGTHS["function"],
                        line_number=line_number
                    )

            # -------------------------------------------------
            # Property / method access
            # -------------------------------------------------

            property_matches = (
                self.PROPERTY_ACCESS_PATTERN.findall(
                    code_line
                )
            )

            for property_name in property_matches:

                if self._is_dart_keyword(
                    property_name
                ):
                    continue

                self._match_identifier(
                    evidence=evidence,
                    file=file,
                    identifier=property_name,
                    signal_terms=signal_terms,
                    evidence_type="property_access",
                    strength=self.EVIDENCE_STRENGTHS[
                        "property_access"
                    ],
                    line_number=line_number
                )

            # -------------------------------------------------
            # Annotations
            # -------------------------------------------------

            annotation_matches = (
                self.ANNOTATION_PATTERN.findall(
                    code_line
                )
            )

            for annotation_name in annotation_matches:

                self._match_identifier(
                    evidence=evidence,
                    file=file,
                    identifier=annotation_name,
                    signal_terms=signal_terms,
                    evidence_type="annotation",
                    strength=self.EVIDENCE_STRENGTHS[
                        "annotation"
                    ],
                    line_number=line_number
                )

            # -------------------------------------------------
            # Generic identifiers
            #
            # This is deliberately weak evidence.
            #
            # Example:
            #
            #   final car = ...
            #
            # can produce generic "car" evidence.
            #
            # However, declarations that already received
            # stronger evidence are excluded.
            # -------------------------------------------------

            identifiers = (
                self.IDENTIFIER_PATTERN.findall(
                    code_line
                )
            )

            for identifier in identifiers:

                if identifier in declared_identifiers:
                    continue

                if self._is_dart_keyword(
                    identifier
                ):
                    continue

                self._match_identifier(
                    evidence=evidence,
                    file=file,
                    identifier=identifier,
                    signal_terms=signal_terms,
                    evidence_type="identifier",
                    strength=self.EVIDENCE_STRENGTHS[
                        "identifier"
                    ],
                    line_number=line_number
                )

        return self._deduplicate(
            evidence
        )

    # ---------------------------------------------------------
    # Normalize signals
    # ---------------------------------------------------------

    def _normalize_signal_terms(
        self,
        signals
    ):
        terms = []

        for signal in signals:

            term = signal.get(
                "term",
                ""
            )

            if not isinstance(
                term,
                str
            ):
                continue

            term = term.strip().lower()

            if not term:
                continue

            if term not in terms:
                terms.append(term)

        return terms

    # ---------------------------------------------------------
    # Match identifier against signals
    # ---------------------------------------------------------

    def _match_identifier(
        self,
        evidence,
        file,
        identifier,
        signal_terms,
        evidence_type,
        strength,
        line_number
    ):

        identifier_lower = (
            identifier.lower()
        )

        for term in signal_terms:

            if not self._matches_term(
                identifier_lower,
                term
            ):
                continue

            evidence.append({
                "file": file,
                "evidence_type": evidence_type,
                "concept": term,
                "strength": strength,
                "line": line_number,
                "identifier": identifier
            })

    # ---------------------------------------------------------
    # Signal matching
    # ---------------------------------------------------------

    def _matches_term(
        self,
        identifier,
        term
    ):
        """
        Match a signal against an identifier.

        We currently support substring matching because issue
        signals such as:

            firebase
            car
            repository

        need to match identifiers such as:

            FirebaseCarDataSource
            CarRepository
            CarRepositoryImpl

        Exact token matching can be added later once the signal
        extraction layer provides normalized concepts.
        """

        return term in identifier

    # ---------------------------------------------------------
    # Remove inline comments
    # ---------------------------------------------------------

    def _remove_inline_comment(
        self,
        line
    ):
        """
        Remove // comments from a source line.

        This intentionally stays conservative and does not attempt
        to fully parse Dart strings.
        """

        quote_single = False
        quote_double = False
        escaped = False

        index = 0

        while index < len(line):

            character = line[index]

            if escaped:

                escaped = False
                index += 1
                continue

            if character == "\\":
                escaped = True
                index += 1
                continue

            if character == "'" and not quote_double:
                quote_single = not quote_single
                index += 1
                continue

            if character == '"' and not quote_single:
                quote_double = not quote_double
                index += 1
                continue

            if (
                character == "/"
                and index + 1 < len(line)
                and line[index + 1] == "/"
                and not quote_single
                and not quote_double
            ):
                return line[:index]

            index += 1

        return line

    # ---------------------------------------------------------
    # Dart keywords
    # ---------------------------------------------------------

    def _is_dart_keyword(
        self,
        identifier
    ):
        keywords = {
            "abstract",
            "as",
            "assert",
            "async",
            "await",
            "break",
            "case",
            "catch",
            "class",
            "const",
            "continue",
            "covariant",
            "default",
            "deferred",
            "do",
            "dynamic",
            "else",
            "enum",
            "export",
            "extends",
            "extension",
            "external",
            "factory",
            "false",
            "final",
            "finally",
            "for",
            "Function",
            "get",
            "hide",
            "if",
            "implements",
            "import",
            "in",
            "interface",
            "is",
            "late",
            "library",
            "mixin",
            "new",
            "null",
            "on",
            "operator",
            "part",
            "required",
            "rethrow",
            "return",
            "set",
            "show",
            "static",
            "super",
            "switch",
            "sync",
            "this",
            "throw",
            "true",
            "try",
            "typedef",
            "var",
            "void",
            "while",
            "with",
            "yield",
        }

        return identifier in keywords

    # ---------------------------------------------------------
    # Deduplicate evidence
    # ---------------------------------------------------------

    def _deduplicate(
        self,
        evidence
    ):
        """
        Remove exact duplicate evidence.

        Evidence of different types is intentionally NOT merged.

        Example:

            class CarBloc

        and:

            FirebaseFirestore.instance

        should remain distinct evidence.

        However, the exact same evidence generated twice by the
        analyzer is removed.
        """

        seen = set()
        unique = []

        for item in evidence:

            key = (
                item["file"]["path"],
                item["evidence_type"],
                item["concept"],
                item["line"],
                item.get("identifier")
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(item)

        return unique