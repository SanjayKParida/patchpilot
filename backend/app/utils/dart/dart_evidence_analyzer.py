import re

from app.utils.dart.dart_usage_analyzer import DartUsageAnalyzer
from app.utils.text_normalizer import TextNormalizer


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
        behavior_flow
            >
        property / method access / consumes / annotation
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

    # `consumes` sits between property access and a bare identifier.
    #
    # It is stronger than `identifier` because the reference has been
    # RESOLVED: the token names a type actually declared elsewhere in
    # this repository and imported here, so it cannot be an unrelated
    # word that happens to look similar.
    #
    # It sits level with property access, because both describe a
    # file actively USING a resolved thing, and below the declaration
    # types because using a thing is weaker evidence of owning a
    # defect than defining it. A screen that reacts to CarsLoading is
    # relevant to a loading bug; the file declaring it usually more so.
    #
    # The value is not finely tuned. Anything from 0.7 upward — even
    # 1.0, level with a class declaration — produces an identical
    # ranking, because confidence saturates. 0.7 is the smallest
    # value that achieves the full effect.
    #
    # `behavior_flow` is a different observation from `consumes`, not
    # a louder one. Consuming CarsLoading says the file names a type
    # that matches the signal. Reacting to CarsLoading AND its
    # siblings (CarsLoaded, CarsError) says the file implements the
    # UI for that behaviour's whole state machine. Distinct evidence
    # types stack, so this can move a file after `consumes` itself
    # has saturated. It sits above consumes because the observation
    # is stronger, and below a function/class declaration because
    # the file still does not own the behaviour.
    EVIDENCE_STRENGTHS = {
        "class": 1.0,
        "function": 0.9,
        "behavior_flow": 0.8,
        "property_access": 0.7,
        "annotation": 0.7,
        "consumes": 0.7,
        "identifier": 0.2,
    }

    # A lifecycle has more than one member. Testing only CarsLoading
    # is generic type consumption, already covered by `consumes`.
    BEHAVIOR_FLOW_MIN_MEMBERS = 2

    # Which kinds of cross-file type usage count as evidence.
    #
    # Only state reaction, for now. Broadening this to every resolved
    # reference was measured and rejected: it promoted the dependency
    # injection container from #8 to #3, because assembling an
    # application means referencing more types than anything else
    # does. See CONTEXT.md.
    CONSUMPTION_KINDS = ("state_test",)

    def __init__(self, normalizer=None, usage_analyzer=None):
        # The same matcher the search service uses. Both channels
        # must agree on what counts as mentioning a concept.
        self.normalizer = normalizer or TextNormalizer()

        # Resolves cross-file type references. Only needed by
        # analyze_repository, which is the entry point that can see
        # the whole repository.
        self.usage_analyzer = (
            usage_analyzer or DartUsageAnalyzer()
        )

    # ---------------------------------------------------------
    # Repository-wide entry point
    # ---------------------------------------------------------

    def analyze_repository(self, files, signals):
        """
        Analyze every file, including cross-file consumption
        and behavioral-flow evidence.

        analyze_file() sees one file and therefore cannot tell a
        reference to a repository type from any other identifier.
        Resolving that, and deciding whether a file reacts to a
        behaviour's whole lifecycle, needs the whole file set.
        """

        usages = self.usage_analyzer.analyze_repository(files)
        families = self.usage_analyzer.type_families(files)

        consumption = {}

        for usage in usages:

            if usage["kind"] not in self.CONSUMPTION_KINDS:
                continue

            consumption.setdefault(
                usage["path"],
                {},
            )[usage["identifier"]] = usage["declared_in"]

        evidence = []

        for file in files:

            path = file.get("path")
            normalized = self.usage_analyzer.structure._normalize_path(
                path or ""
            )

            evidence.extend(
                self.analyze_file(
                    file,
                    signals,
                    consumed_symbols=consumption.get(
                        path,
                        consumption.get(normalized, {}),
                    ),
                )
            )

        evidence.extend(
            self._behavior_flow_evidence(
                files,
                signals,
                usages,
                families,
            )
        )

        return evidence

    def _behavior_flow_evidence(
        self,
        files,
        signals,
        usages,
        families,
    ):
        """
        Evidence that a file reacts to a behaviour's lifecycle.

        `consumes` credits a file for state-testing a type whose name
        matches a signal (CarsLoading → "loading"). That misses the
        rest of the same machine: CarsLoaded and CarsError do not
        contain the word "loading", yet a screen that branches on
        all three is the UI for the reported symptom.

        This is Dart-specific detection (same-file subclass families
        plus `state is X` tests) emitting a generic evidence record.
        Ranking never sees the family; it only sees type, concept,
        and strength.
        """

        behavior_terms = []
        seen_terms = set()

        for signal in signals:

            if signal.get("type") != "behavior":
                continue

            term = signal.get("term", "")

            if not isinstance(term, str):
                continue

            term = term.strip().lower()

            if not term or term in seen_terms:
                continue

            concepts = self.normalizer.concepts(term)

            if not concepts:
                continue

            seen_terms.add(term)
            behavior_terms.append((term, concepts))

        if not behavior_terms or not families:
            return []

        family_of = {}

        for declared_in, grouped in families.items():
            for base, members in grouped.items():
                for member in members:
                    family_of[(declared_in, member)] = (
                        declared_in,
                        base,
                    )

        normalize = self.usage_analyzer.structure._normalize_path

        file_by_path = {
            normalize(file.get("path", "")): file
            for file in files
            if file.get("path")
        }

        reactions = {}

        for usage in usages:

            if usage["kind"] not in self.CONSUMPTION_KINDS:
                continue

            family_key = family_of.get(
                (usage["declared_in"], usage["identifier"])
            )

            if family_key is None:
                continue

            reactions.setdefault(
                (usage["path"], family_key),
                {},
            )[usage["identifier"]] = usage["line"]

        evidence = []

        for (consumer_path, family_key), tested in reactions.items():

            if len(tested) < self.BEHAVIOR_FLOW_MIN_MEMBERS:
                continue

            file = file_by_path.get(consumer_path)

            if file is None:
                continue

            _, base = family_key

            for term, concepts in behavior_terms:

                matching = [
                    name
                    for name in tested
                    if self._matches_term(
                        set(self.normalizer.concepts(name)),
                        concepts,
                    )
                ]

                if not matching:
                    continue

                evidence.append({
                    "file": file,
                    "evidence_type": "behavior_flow",
                    "concept": term,
                    "strength": self.EVIDENCE_STRENGTHS[
                        "behavior_flow"
                    ],
                    "line": min(tested.values()),
                    "identifier": base,
                    "members": sorted(tested),
                })

        return evidence

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def analyze_file(self, file, signals, consumed_symbols=None):
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

        consumed_symbols = consumed_symbols or {}

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

                # -------------------------------------------------
                # A resolved reference to a type declared elsewhere
                # in this repository is upgraded from a bare
                # identifier to consumption evidence.
                #
                # It replaces the identifier record rather than
                # adding to it. One occurrence is one observation,
                # and emitting both would count it twice.
                # -------------------------------------------------

                declared_in = consumed_symbols.get(identifier)

                if declared_in:
                    evidence_type = "consumes"
                else:
                    evidence_type = "identifier"

                self._match_identifier(
                    evidence=evidence,
                    file=file,
                    identifier=identifier,
                    signal_terms=signal_terms,
                    evidence_type=evidence_type,
                    strength=self.EVIDENCE_STRENGTHS[
                        evidence_type
                    ],
                    line_number=line_number,
                    declared_in=declared_in
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
        """
        Reduce signals to (label, concepts) pairs.

        The label is the term as the ranking layer knows it, because
        rank() filters evidence by `concept`. The concepts are what
        identifiers are actually matched against.
        """

        terms = []
        seen = set()

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

            if not term or term in seen:
                continue

            concepts = self.normalizer.concepts(term)

            if not concepts:
                continue

            seen.add(term)

            terms.append(
                (term, concepts)
            )

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
        line_number,
        declared_in=None
    ):

        identifier_concepts = set(
            self.normalizer.concepts(identifier)
        )

        if not identifier_concepts:
            return

        for term, term_concepts in signal_terms:

            if not self._matches_term(
                identifier_concepts,
                term_concepts
            ):
                continue

            record = {
                "file": file,
                "evidence_type": evidence_type,
                "concept": term,
                "strength": strength,
                "line": line_number,
                "identifier": identifier
            }

            # The owner half of the owner -> consumer edge, kept for
            # diagnostics. Ranking does not read it.
            if declared_in:
                record["declared_in"] = declared_in

            evidence.append(record)

    # ---------------------------------------------------------
    # Signal matching
    # ---------------------------------------------------------

    def _matches_term(
        self,
        identifier_concepts,
        term_concepts
    ):
        """
        Does an identifier mention every concept in a signal?

        Both sides have already been tokenized and singularized by
        TextNormalizer, so this compares whole words:

            car  vs  FirebaseCarDataSource   [firebase car data source]  yes
            car  vs  getCars                 [get car]                   yes
            car  vs  MoreCard                [more card]                 no

        The previous implementation matched substrings. That let
        "car" match the payment-card UI, and the resulting false
        evidence contaminated the ranking for the whole domain.
        """

        return all(
            concept in identifier_concepts
            for concept in term_concepts
        )

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