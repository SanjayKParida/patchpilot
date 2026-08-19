class RepositoryGraph:
    """
    Generic repository relationship graph.

    The graph is architecture-agnostic.

    It does not assume:
        - Clean Architecture
        - MVC
        - MVVM
        - BLoC
        - repository/use-case patterns

    It simply understands relationships discovered by the
    language-specific structure analyzer.

    Example relationships:

        A --imports--> B
        A --implements--> B
        A --extends--> B

    The graph stores both forward and reverse relationships so
    callers can traverse the repository in either direction.
    """

    def __init__(self, relationships):
        self.relationships = {}
        self.reverse_relationships = {}

        for relationship in relationships:

            source = relationship.get("source")
            target = relationship.get("target")
            relationship_type = relationship.get(
                "relationship"
            )

            if not source or not target:
                continue

            if not relationship_type:
                continue

            # -------------------------------------------------
            # Forward relationship
            # -------------------------------------------------

            self.relationships.setdefault(
                source,
                []
            ).append({
                "target": target,
                "relationship": relationship_type
            })

            # -------------------------------------------------
            # Reverse relationship
            # -------------------------------------------------

            self.reverse_relationships.setdefault(
                target,
                []
            ).append({
                "source": source,
                "relationship": relationship_type
            })

    # =========================================================
    # GENERIC RELATIONSHIPS
    # =========================================================

    def get_relationships(
        self,
        file_path,
        relationship_type=None
    ):
        """
        Return relationships originating from file_path.

        If relationship_type is provided, only relationships of
        that type are returned.
        """

        relationships = self.relationships.get(
            file_path,
            []
        )

        if relationship_type is None:
            return list(relationships)

        return [
            relationship
            for relationship in relationships
            if relationship["relationship"]
            == relationship_type
        ]

    def get_reverse_relationships(
        self,
        file_path,
        relationship_type=None
    ):
        """
        Return relationships pointing toward file_path.

        This is important for finding files that depend on a
        candidate file.
        """

        relationships = self.reverse_relationships.get(
            file_path,
            []
        )

        if relationship_type is None:
            return list(relationships)

        return [
            relationship
            for relationship in relationships
            if relationship["relationship"]
            == relationship_type
        ]

    # =========================================================
    # IMPORT HELPERS
    # =========================================================

    def get_imports(
        self,
        file_path
    ):
        """
        Return files imported by file_path.
        """

        relationships = self.get_relationships(
            file_path,
            "imports"
        )

        return [
            relationship["target"]
            for relationship in relationships
        ]

    def get_importers(
        self,
        file_path
    ):
        """
        Return files that import file_path.
        """

        relationships = self.get_reverse_relationships(
            file_path,
            "imports"
        )

        return [
            relationship["source"]
            for relationship in relationships
        ]

    # =========================================================
    # NEIGHBORS
    # =========================================================

    def get_neighbors(
        self,
        file_path
    ):
        """
        Return all directly connected files.

        Both forward and reverse relationships are considered.

        This makes the graph useful for issue retrieval because
        a relevant file can be connected either to a dependency
        or to a file that depends on it.
        """

        neighbors = set()

        # Forward relationships

        for relationship in self.get_relationships(
            file_path
        ):
            neighbors.add(
                relationship["target"]
            )

        # Reverse relationships

        for relationship in self.get_reverse_relationships(
            file_path
        ):
            neighbors.add(
                relationship["source"]
            )

        return list(neighbors)

    # =========================================================
    # ONE-HOP EXPANSION
    # =========================================================

    def expand(
        self,
        file_paths
    ):
        """
        Expand a set of seed files by one graph hop.

        The original seed files are always retained.
        """

        expanded = set(
            file_paths
        )

        for file_path in file_paths:

            for neighbor in self.get_neighbors(
                file_path
            ):
                expanded.add(
                    neighbor
                )

        return list(expanded)

    # =========================================================
    # MULTI-DEPTH STRUCTURAL TRAVERSAL
    # =========================================================

    def get_structural_relationships(
        self,
        file_paths,
        max_depth=1,
        include_reverse=False
    ):
        """
        Traverse the graph and return structural evidence.

        Parameters
        ----------
        file_paths:
            Starting files.

        max_depth:
            Maximum number of graph hops.

        include_reverse:
            Whether reverse relationships should also be followed.

        Returns
        -------
        list

        Example result:

            {
                "source": "a.dart",
                "target": "b.dart",
                "relationship": "imports",
                "distance": 1
            }

        The distance is important because the ranking layer can
        reduce the importance of distant structural evidence.
        """

        if not file_paths:
            return []

        if max_depth < 1:
            return []

        results = []

        visited = set(
            file_paths
        )

        current = set(
            file_paths
        )

        for depth in range(
            1,
            max_depth + 1
        ):

            next_files = set()

            for current_file in current:

                # ---------------------------------------------
                # Forward relationships
                # ---------------------------------------------

                relationships = self.get_relationships(
                    current_file
                )

                for relationship in relationships:

                    target = relationship["target"]

                    if target in visited:
                        continue

                    visited.add(target)

                    next_files.add(
                        target
                    )

                    results.append({
                        "source": current_file,
                        "target": target,
                        "relationship": relationship[
                            "relationship"
                        ],
                        "distance": depth
                    })

                # ---------------------------------------------
                # Optional reverse relationships
                # ---------------------------------------------

                if include_reverse:

                    reverse_relationships = (
                        self.get_reverse_relationships(
                            current_file
                        )
                    )

                    for relationship in reverse_relationships:

                        source = relationship["source"]

                        if source in visited:
                            continue

                        visited.add(source)

                        next_files.add(
                            source
                        )

                        results.append({
                            "source": current_file,
                            "target": source,
                            "relationship": relationship[
                                "relationship"
                            ],
                            "distance": depth
                        })

            current = next_files

            if not current:
                break

        return results

    # =========================================================
    # DEPENDENCIES
    # =========================================================

    def get_dependencies(
        self,
        file_path,
        max_depth=1
    ):
        """
        Return forward dependencies of a file.

        This is intentionally generic.

        It follows all known forward relationships rather than
        assuming that "imports" is the only meaningful dependency.
        """

        if max_depth < 1:
            return {}

        dependencies = {}

        current = {
            file_path
        }

        visited = {
            file_path
        }

        for depth in range(
            1,
            max_depth + 1
        ):

            next_files = set()

            for current_file in current:

                for relationship in self.get_relationships(
                    current_file
                ):

                    dependency = relationship["target"]

                    if dependency in visited:
                        continue

                    visited.add(
                        dependency
                    )

                    dependencies[
                        dependency
                    ] = depth

                    next_files.add(
                        dependency
                    )

            current = next_files

            if not current:
                break

        return dependencies

    # =========================================================
    # DEPENDENCY EVIDENCE
    # =========================================================

    def get_dependency_relationships(
        self,
        file_path,
        max_depth=1
    ):
        """
        Return dependency traversal with relationship metadata.

        Unlike get_dependencies(), this preserves the actual
        relationship type so the ranking layer can distinguish:

            imports
            implements
            extends
            etc.
        """

        if max_depth < 1:
            return []

        results = []

        current = {
            file_path
        }

        visited = {
            file_path
        }

        for depth in range(
            1,
            max_depth + 1
        ):

            next_files = set()

            for current_file in current:

                for relationship in self.get_relationships(
                    current_file
                ):

                    dependency = relationship["target"]

                    if dependency in visited:
                        continue

                    visited.add(
                        dependency
                    )

                    next_files.add(
                        dependency
                    )

                    results.append({
                        "source": current_file,
                        "target": dependency,
                        "relationship": relationship[
                            "relationship"
                        ],
                        "distance": depth
                    })

            current = next_files

            if not current:
                break

        return results