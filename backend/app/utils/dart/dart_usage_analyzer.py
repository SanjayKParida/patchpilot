import re

from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer


class DartUsageAnalyzer:
    """
    Detects which files CONSUME types that other files DECLARE.

    Why this exists
    ---------------

    Ranking rewards a file for owning a concept: declaring the class,
    defining the function. That is the right primary signal, but it
    systematically misses a whole category of relevant file.

        car_state.dart      declares  CarsLoading
        car_list_screen.dart consumes  CarsLoading

    When an issue reports "the loading indicator never goes away", the
    screen reacting to that state is exactly what a developer opens
    first, yet it declares nothing and so scores as a bystander.

    The evidence analyzer on its own cannot tell these apart:

        CarsLoading      a real type declared in this repository
        directions_car   a Material icon name

    Both are bare identifier tokens. Resolving the reference against
    the repository's own declarations is what separates them, and that
    needs cross-file knowledge, which is why it lives here rather than
    in the per-file evidence analyzer.

    What counts as consumption
    --------------------------

    Deliberately narrow for a first implementation. A file B consumes
    symbol S when ALL of the following hold:

        1. S is declared as a type (class / mixin) in a file A of this
           repository, and A is not B.

        2. B has an import that RESOLVES to A. A name matching
           something elsewhere in the repository is not enough — the
           same rule DartStructureAnalyzer already applies to
           implements / extends. Do not guess.

        3. S is unambiguous from B's position: exactly one of B's
           resolved imports declares it.

        4. S appears as an identifier in B's code, outside comments
           and string literals.

    This intentionally does NOT cover calls, field reads, constructor
    invocation or injection as distinct relationships. Those are
    separate hypotheses and should be measured separately.

    Type families
    -------------

    `type_families()` groups classes that share a base declared in
    the same file. That is the Dart-side detection for behavioral
    flow: CarsLoading / CarsLoaded / CarsError are one lifecycle
    because they extend CarState together, not because their names
    look similar. Ranking never sees this structure; the evidence
    analyzer turns a reaction to the family into a generic
    `behavior_flow` record.
    """

    IDENTIFIER_PATTERN = re.compile(
        r"\b[A-Za-z_][A-Za-z0-9_]*\b"
    )

    # ---------------------------------------------------------
    # Usage kinds
    # ---------------------------------------------------------
    #
    # The detector reports HOW a type was used and lets the caller
    # decide which kinds count as relevance evidence. Lumping them
    # together does not work: the file that wires an application
    # together references more types than any other file, and treating
    # every reference alike makes the dependency-injection container
    # look like the most relevant file in the repository.
    #
    #   state_test     `state is CarsLoading`
    #                  The file REACTS to the type — it branches on
    #                  it. This is the relationship a screen has with
    #                  the state that drives it.
    #
    #   type_argument  `BlocBuilder<CarBloc, CarState>`, `getIt<X>()`
    #                  The file is parameterised by the type.
    #
    #   reference      anything else, including construction.
    #                  `CarBloc(getCars: ...)` builds the thing; that
    #                  is assembly, not use.
    # ---------------------------------------------------------

    STATE_TEST_PATTERN = re.compile(
        r"\bis!?\s+([A-Za-z_]\w*)"
    )

    TYPE_ARGUMENT_PATTERN = re.compile(
        r"<([^<>]*)>"
    )

    STATE_TEST = "state_test"
    TYPE_ARGUMENT = "type_argument"
    REFERENCE = "reference"

    def __init__(self, structure_analyzer=None):
        self.structure = (
            structure_analyzer
            or DartStructureAnalyzer()
        )

    # =========================================================
    # PUBLIC API
    # =========================================================

    def analyze_repository(self, files):
        """
        Find every consumption relationship in the repository.

        Returns
        -------
        list

            {
                "path": "lib/presentation/pages/car_list_screen.dart",
                "identifier": "CarsLoading",
                "declared_in": "lib/presentation/bloc/car_state.dart",
                "line": 23
            }

        The pair (declared_in, path) is the owner -> consumer edge.
        """

        dart_files = [
            file
            for file in files
            if self.structure._normalize_path(
                file.get("path", "")
            ).endswith(".dart")
        ]

        file_by_path = self.structure._build_file_index(dart_files)
        symbol_index = self.structure._build_symbol_index(dart_files)

        # symbol -> set of declaring paths
        declared_in = {}

        for symbol, owners in symbol_index.items():
            declared_in[symbol] = {
                self.structure._normalize_path(owner["path"])
                for owner in owners
            }

        usages = []

        for file in dart_files:
            usages.extend(
                self._analyze_file(
                    file,
                    dart_files,
                    file_by_path=file_by_path,
                    declared_in=declared_in,
                )
            )

        return usages

    def type_families(self, files):
        """
        Group classes that share a base declared in the same file.

        A BLoC/Cubit state file typically looks like:

            abstract class CarState {}
            class CarsLoading extends CarState {}
            class CarsLoaded extends CarState {}
            class CarsError extends CarState {}

        Those three subclasses are one FAMILY: they are the lifecycle
        of one state machine. A file that branches on more than one
        of them is reacting to that lifecycle, not merely consuming
        a type whose name happens to contain a signal term.

        Conservative on purpose:

            - Same file only. Cross-file hierarchies need import
              resolution and are a separate hypothesis.
            - The base must itself be declared in that file. Extending
              `Equatable` or `BlocState` from a package is ignored.
            - A lone subclass is not a family. A lifecycle has
              more than one member.
            - Mixins and `with` clauses are ignored. State machines
              in this codebase are `extends` / `implements`.

        Returns
        -------
        dict

            {
                "lib/presentation/bloc/car_state.dart": {
                    "CarState": {"CarsLoading", "CarsLoaded", "CarsError"}
                }
            }
        """

        families = {}

        dart_files = [
            file
            for file in files
            if self.structure._normalize_path(
                file.get("path", "")
            ).endswith(".dart")
        ]

        for file in dart_files:
            path = self.structure._normalize_path(
                file.get("path", "")
            )
            code = self.structure._mask_comments_and_strings(
                file.get("content", "")
            )

            declared = {
                match.group("name")
                for match in (
                    self.structure.TYPE_DECLARATION_PATTERN.finditer(
                        code
                    )
                )
            }

            grouped = {}

            for declaration in (
                self.structure.CLASS_DECLARATION_PATTERN.finditer(
                    code
                )
            ):
                name = declaration.group("name")
                clauses = declaration.group("clauses")

                for relationship in ("extends", "implements"):
                    for base in self._clause_types(
                        clauses,
                        relationship,
                    ):
                        if base not in declared or base == name:
                            continue

                        grouped.setdefault(base, set()).add(name)

            local = {
                base: members
                for base, members in grouped.items()
                if len(members) >= 2
            }

            if local:
                families[path] = local

        return families

    def consumption_index(self, files, kinds=None):
        """
        Same information keyed for per-file lookup.

        Parameters
        ----------
        kinds:
            Restrict to these usage kinds. None means every kind,
            which is rarely what a caller wants — see the class
            docstring.

        Returns
        -------
        dict

            {
                "<consumer path>": {
                    "<identifier>": "<declaring path>"
                }
            }
        """

        index = {}

        for usage in self.analyze_repository(files):

            if kinds is not None and usage["kind"] not in kinds:
                continue

            index.setdefault(
                usage["path"],
                {},
            )[usage["identifier"]] = usage["declared_in"]

        return index

    # =========================================================
    # INTERNALS
    # =========================================================

    def _clause_types(self, clauses, relationship):
        """Type names from an extends / implements / with clause."""

        match = self.structure.CLAUSE_PATTERNS[relationship].search(
            clauses
        )

        if not match:
            return []

        names = []

        for type_reference in self.structure._split_type_references(
            match.group("types")
        ):
            type_match = self.structure.TYPE_REFERENCE_PATTERN.match(
                type_reference
            )

            if type_match:
                names.append(type_match.group("name"))

        return names

    def _analyze_file(
        self,
        file,
        files,
        *,
        file_by_path,
        declared_in,
    ):
        source_path = self.structure._normalize_path(
            file.get("path", "")
        )

        content = file.get("content", "")

        # -----------------------------------------------------
        # Which repository files does this file actually import?
        # -----------------------------------------------------

        imported_paths = set()

        for import_path in self.structure.extract_imports(content):

            resolved = self.structure.resolve_import(
                import_path,
                files,
                source_path=source_path,
                file_by_path=file_by_path,
            )

            if resolved is None:
                continue

            resolved_path = self.structure._normalize_path(
                resolved["path"]
            )

            if resolved_path != source_path:
                imported_paths.add(resolved_path)

        if not imported_paths:
            return []

        # -----------------------------------------------------
        # Which symbols can this file legitimately refer to?
        #
        # A symbol declared by two different imports is ambiguous
        # from here, so it is dropped rather than guessed at.
        # -----------------------------------------------------

        visible = {}

        for symbol, owners in declared_in.items():

            # A file's own declarations are ownership, not
            # consumption.
            if source_path in owners:
                continue

            reachable = owners & imported_paths

            if len(reachable) != 1:
                continue

            visible[symbol] = next(iter(reachable))

        if not visible:
            return []

        # -----------------------------------------------------
        # Where are those symbols actually referenced?
        # -----------------------------------------------------

        code = self.structure._mask_comments_and_strings(content)

        usages = []
        seen = set()

        for line_number, line in enumerate(
            code.splitlines(),
            start=1,
        ):

            tested = set(
                self.STATE_TEST_PATTERN.findall(line)
            )

            parameterised = set()

            for arguments in self.TYPE_ARGUMENT_PATTERN.findall(line):
                parameterised.update(
                    self.IDENTIFIER_PATTERN.findall(arguments)
                )

            for identifier in self.IDENTIFIER_PATTERN.findall(line):

                owner = visible.get(identifier)

                if owner is None:
                    continue

                if identifier in tested:
                    kind = self.STATE_TEST
                elif identifier in parameterised:
                    kind = self.TYPE_ARGUMENT
                else:
                    kind = self.REFERENCE

                key = (identifier, line_number, kind)

                if key in seen:
                    continue

                seen.add(key)

                usages.append({
                    "path": source_path,
                    "identifier": identifier,
                    "declared_in": owner,
                    "line": line_number,
                    "kind": kind,
                })

        return usages
