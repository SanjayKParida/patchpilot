class AnalyzeIssueService:
    """
    Orchestrates repository issue analysis.

    This service owns the pipeline:

        issue
          ↓
        signals
          ↓
        structural graph
          ↓
        direct evidence
          ↓
        retrieval
          ↓
        ranking
          ↓
        analysis package

    It does NOT:
        - diagnose the bug
        - call the LLM itself (signal extraction is delegated)
        - extract code regions
        - implement ranking rules
        - implement language-specific analysis

    Those responsibilities remain in their respective services.
    """

    STRUCTURAL_MAX_DEPTH = 2
    STRUCTURAL_INCLUDE_REVERSE = True

    def __init__(
        self,
        signal_service,
        search_service,
        evidence_service,
        ranking_service,
        structure_analyzer,
    ):
        self.signal_service = signal_service
        self.search_service = search_service
        self.evidence_service = evidence_service
        self.ranking_service = ranking_service
        self.structure_analyzer = structure_analyzer

    # =========================================================
    # PUBLIC API
    # =========================================================

    def analyze(
        self,
        files,
        issue,
        signals=None,
        top_n=5,
        available_n=10,
    ):
        """
        Analyze an issue against a repository snapshot.

        Parameters
        ----------
        files:
            Repository source files.

        issue:
            {
                "title": "...",
                "body": "..."
            }

        signals:
            Optional precomputed signals.

            When None, the injected signal_service extracts
            them from the issue. Production injects
            IssueSignalExtractionService. Tests may inject
            IssueSignalService or pass signals explicitly.

        top_n:
            Number of highest-ranked files whose full contents
            are included in the primary package.

        available_n:
            Number of ranked files whose paths remain available
            to the diagnosis layer.

        Returns
        -------
        dict
            {
                "issue": {...},
                "signals": [...],
                "ranked": [...],
                "primary_files": [...],
                "available_files": [...],
                "direct_evidence": [...],
                "structural_results": [...],
                "seed_paths": [...]
            }
        """

        if not issue:
            raise ValueError(
                "issue is required"
            )

        if not files:
            raise ValueError(
                "files are required"
            )

        # -----------------------------------------------------
        # Signals
        # -----------------------------------------------------

        if signals is None:

            title, body = self._issue_text(issue)

            signals = (
                self.signal_service.extract_signals(
                    title,
                    body,
                )
            )

        # -----------------------------------------------------
        # Repository graph
        # -----------------------------------------------------

        graph = self.evidence_service.graph

        if graph is None:
            from app.utils.repository_graph import RepositoryGraph

            graph = RepositoryGraph(
                self.structure_analyzer.analyze_repository(
                    files
                )
            )

        # -----------------------------------------------------
        # Direct evidence
        # -----------------------------------------------------

        direct_evidence = (
            self.evidence_service.analyze_files(
                files,
                signals
            )
        )

        direct_evidence = [
            item
            for item in direct_evidence
            if self.search_service.is_candidate_file(
                item["file"]
            )
        ]

        # -----------------------------------------------------
        # Retrieval + structural expansion + ranking
        # -----------------------------------------------------

        rankings = []

        all_seed_paths = set()

        all_structural_results = []

        for signal in signals:

            term = signal["term"]

            # ---------------------------------------------
            # Generic retrieval
            # ---------------------------------------------

            path_results = (
                self.search_service.search(
                    files,
                    term
                )
            )

            content_results = (
                self.search_service.search_content(
                    files,
                    term
                )
            )

            # ---------------------------------------------
            # Seed paths
            # ---------------------------------------------

            seed_paths = (
                {
                    file["path"]
                    for file in path_results
                }
                |
                {
                    result["file"]["path"]
                    for result in content_results
                }
            )

            seed_paths = {
                path
                for path in seed_paths
                if self.search_service.is_candidate_file(
                    {
                        "path": path
                    }
                )
            }

            all_seed_paths.update(
                seed_paths
            )

            # ---------------------------------------------
            # Structural expansion
            # ---------------------------------------------

            structural_results = (
                self.evidence_service.expand_candidates(
                    seed_paths,
                    max_depth=self.STRUCTURAL_MAX_DEPTH,
                    include_reverse=self.STRUCTURAL_INCLUDE_REVERSE,
                )
            )

            structural_results = [
                result
                for result in structural_results
                if self.search_service.is_candidate_file(
                    {
                        "path": result["target"]
                    }
                )
            ]

            all_structural_results.extend(
                structural_results
            )

            # ---------------------------------------------
            # Convert structural result format
            # ---------------------------------------------

            ranking_structural_results = (
                self._convert_structural_results(
                    structural_results,
                    files
                )
            )

            # ---------------------------------------------
            # Rank this signal
            # ---------------------------------------------

            ranking = (
                self.ranking_service.rank(
                    signal=signal,
                    path_results=path_results,
                    content_results=content_results,
                    structural_results=ranking_structural_results,
                    direct_evidence=direct_evidence,
                )
            )

            rankings.append(
                ranking
            )

        # -----------------------------------------------------
        # Aggregate
        # -----------------------------------------------------

        final_scores = (
            self.ranking_service.aggregate(
                rankings
            )
        )

        # -----------------------------------------------------
        # Ranked output
        # -----------------------------------------------------

        ranked = self._build_ranked_output(
            final_scores
        )

        # -----------------------------------------------------
        # File lookup
        # -----------------------------------------------------

        files_by_path = {
            file["path"]: file
            for file in files
        }

        primary_files = [
            files_by_path[path]
            for path in (
                item["path"]
                for item in ranked[:top_n]
            )
            if path in files_by_path
        ]

        available_files = [
            path
            for path in (
                item["path"]
                for item in ranked[
                    top_n:available_n
                ]
            )
            if path in files_by_path
        ]

        # -----------------------------------------------------
        # Return analysis package
        # -----------------------------------------------------

        return {
            "issue": issue,
            "signals": signals,

            "ranked": ranked,

            "primary_files": primary_files,

            "available_files": available_files,

            "direct_evidence": direct_evidence,

            "structural_results": all_structural_results,

            "seed_paths": sorted(
                all_seed_paths
            )
        }

    # =========================================================
    # STRUCTURAL CONVERSION
    # =========================================================

    @staticmethod
    def _convert_structural_results(
        structural_results,
        files
    ):
        """
        Convert RepositoryGraph relationships into the format
        expected by RepositoryRankingService.
        """

        files_by_path = {
            file["path"]: file
            for file in files
        }

        converted = []

        for result in structural_results:

            target_path = result["target"]

            target_file = files_by_path.get(
                target_path
            )

            if target_file is None:
                continue

            converted.append({
                "file": target_file,
                "source": result.get("source"),
                "target": target_path,
                "relationship": result.get("relationship"),
                "distance": result.get("distance"),
            })

        return converted

    # =========================================================
    # RANKED OUTPUT
    # =========================================================

    @staticmethod
    def _build_ranked_output(
        final_scores
    ):
        """
        Normalize ranking service output into a stable,
        serializable ranked representation.
        """

        ranked = []

        sorted_scores = sorted(
            final_scores.items(),
            key=lambda item: item[1].get("total_score", 0),
            reverse=True
        )

        for index, (
            sha,
            score
        ) in enumerate(
            sorted_scores,
            start=1
        ):

            ranked.append({
                "rank": index,
                "sha": sha,
                "path": score["path"],
                "total_score": score.get("total_score", 0),
                "direct_score": score.get(
                    "direct_score",
                    0
                ),
                "structural_score": score.get(
                    "structural_score",
                    0
                ),
                "signals_matched": score.get("signals_matched", 0),
                "path_confidence": score.get(
                    "path_confidence",
                    0
                ),
                "content_confidence": score.get(
                    "content_confidence",
                    0
                ),
                "evidence_confidence": score.get(
                    "evidence_confidence",
                    0
                )
            })

        return ranked

    @staticmethod
    def _issue_text(issue):
        title = issue.get("title") or ""
        body = issue.get("body") or ""
        return title, body


def build_analyze_issue_service(
    files,
    signal_service=None,
    llm_service=None,
):
    """
    Wire AnalyzeIssueService with production defaults.

    Production:
        issue → IssueSignalExtractionService (LLM)
              → retrieval / ranking

    Tests:
        pass IssueSignalService() for the hardcoded control,
        or pass signals= into analyze() to skip extraction.
    """

    from app.services.issue_signal_extraction_service import (
        IssueSignalExtractionService,
    )
    from app.services.repository_evidence_service import (
        RepositoryEvidenceService,
    )
    from app.services.repository_ranking_service import (
        RepositoryRankingService,
    )
    from app.services.repository_search_service import (
        RepositorySearchService,
    )
    from app.utils.dart.dart_evidence_analyzer import (
        DartEvidenceAnalyzer,
    )
    from app.utils.dart.dart_structure_analyzer import (
        DartStructureAnalyzer,
    )
    from app.utils.repository_graph import RepositoryGraph

    if signal_service is None:
        from app.services.llm_service import LLMService

        if llm_service is None:
            llm_service = LLMService()

        signal_service = IssueSignalExtractionService(
            llm_service=llm_service,
        )

    structure_analyzer = DartStructureAnalyzer()

    graph = RepositoryGraph(
        structure_analyzer.analyze_repository(files)
    )

    return AnalyzeIssueService(
        signal_service=signal_service,
        search_service=RepositorySearchService(),
        evidence_service=RepositoryEvidenceService(
            evidence_analyzer=DartEvidenceAnalyzer(),
            graph=graph,
        ),
        ranking_service=RepositoryRankingService(),
        structure_analyzer=structure_analyzer,
    )