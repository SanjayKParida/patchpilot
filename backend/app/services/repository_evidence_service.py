class RepositoryEvidenceService:
    """
    Combines language-specific code evidence with generic repository
    structural evidence.

    This service intentionally knows nothing about Dart, Flutter,
    BLoC, MVC, MVVM, Clean Architecture, etc.

    Language-specific analysis belongs to an evidence analyzer such as:

        DartEvidenceAnalyzer

    Generic repository relationships belong to:

        RepositoryGraph

    This service simply combines their outputs into a common format
    that the ranking layer can consume.
    """

    def __init__(
        self,
        evidence_analyzer,
        graph
    ):
        self.evidence_analyzer = evidence_analyzer
        self.graph = graph

    # =========================================================
    # DIRECT CODE EVIDENCE
    # =========================================================

    def analyze_files(
        self,
        files,
        signals
    ):
        """
        Run the language-specific evidence analyzer over all files.

        Returns a flat list of evidence records.

        Example:

            [
                {
                    "file": {...},
                    "evidence_type": "class",
                    "concept": "firebase",
                    "strength": 1.0,
                    "line": 12,
                    "identifier": "FirebaseCarDataSource"
                }
            ]
        """

        # A language pack may offer a repository-wide entry point when
        # some of its evidence needs cross-file knowledge, such as
        # resolving a type reference to the file that declares it.
        # Prefer it; fall back to per-file analysis for packs that
        # only implement that.
        analyze_repository = getattr(
            self.evidence_analyzer,
            "analyze_repository",
            None
        )

        if callable(analyze_repository):
            return analyze_repository(
                files,
                signals
            )

        evidence = []

        for file in files:

            file_evidence = (
                self.evidence_analyzer.analyze_file(
                    file,
                    signals
                )
            )

            if not file_evidence:
                continue

            evidence.extend(
                file_evidence
            )

        return evidence

    # =========================================================
    # STRUCTURAL EVIDENCE
    # =========================================================

    def expand_candidates(
        self,
        seed_paths,
        max_depth=1,
        include_reverse=False
    ):
        """
        Expand seed files through the generic repository graph.

        Returns structural relationships rather than merely a list
        of files.

        This is important because the ranking layer needs to know:

            - which file led to the candidate
            - which candidate was discovered
            - relationship type
            - graph distance
        """

        if not seed_paths:
            return []

        return self.graph.get_structural_relationships(
            seed_paths,
            max_depth=max_depth,
            include_reverse=include_reverse
        )

    # =========================================================
    # COMBINED EVIDENCE
    # =========================================================

    def collect(
        self,
        files,
        signals,
        seed_paths=None,
        max_depth=1,
        include_reverse=False
    ):
        """
        Collect both direct and structural evidence.

        Parameters
        ----------
        files:
            Repository files.

        signals:
            Issue signals.

        seed_paths:
            Files already identified through path/content retrieval.

        max_depth:
            Maximum structural traversal depth.

        include_reverse:
            Whether reverse graph relationships should be followed.

        Returns
        -------
        dict

        Example:

            {
                "direct": [...],
                "structural": [...]
            }
        """

        direct_evidence = self.analyze_files(
            files,
            signals
        )

        structural_evidence = []

        if seed_paths:

            structural_evidence = (
                self.expand_candidates(
                    seed_paths,
                    max_depth=max_depth,
                    include_reverse=include_reverse
                )
            )

        return {
            "direct": direct_evidence,
            "structural": structural_evidence
        }

    # =========================================================
    # GROUP DIRECT EVIDENCE BY FILE
    # =========================================================

    def group_direct_evidence(
        self,
        evidence
    ):
        """
        Group direct evidence by repository file path.

        This is useful for ranking and debugging.

        Returns:

            {
                "lib/foo.dart": [
                    {...},
                    {...}
                ]
            }
        """

        grouped = {}

        for item in evidence:

            file = item.get(
                "file"
            )

            if not file:
                continue

            path = file.get(
                "path"
            )

            if not path:
                continue

            grouped.setdefault(
                path,
                []
            ).append(
                item
            )

        return grouped

    # =========================================================
    # GROUP STRUCTURAL EVIDENCE BY FILE
    # =========================================================

    def group_structural_evidence(
        self,
        evidence
    ):
        """
        Group structural evidence by candidate target.

        Example:

            {
                "lib/data/models/car.dart": [
                    {
                        "source": "...",
                        "target": "...",
                        "relationship": "imports",
                        "distance": 2
                    }
                ]
            }
        """

        grouped = {}

        for item in evidence:

            target = item.get(
                "target"
            )

            if not target:
                continue

            grouped.setdefault(
                target,
                []
            ).append(
                item
            )

        return grouped

    # =========================================================
    # DEBUG SUMMARY
    # =========================================================

    def summarize(
        self,
        evidence
    ):
        """
        Produce a compact summary useful during development.

        This does not affect ranking.
        """

        direct = evidence.get(
            "direct",
            []
        )

        structural = evidence.get(
            "structural",
            []
        )

        direct_files = {
            item["file"]["path"]
            for item in direct
            if item.get("file")
        }

        structural_files = {
            item["target"]
            for item in structural
            if item.get("target")
        }

        return {
            "direct_evidence_count": len(
                direct
            ),
            "direct_file_count": len(
                direct_files
            ),
            "structural_evidence_count": len(
                structural
            ),
            "structural_file_count": len(
                structural_files
            )
        }