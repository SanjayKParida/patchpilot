from app.errors import IssueNotFound
from app.services.analyze_issue_service import (
    build_analyze_issue_service,
)
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.services.repository_search_service import (
    RepositorySearchService,
)
from app.utils.dart.dart_symbol_locator import DartSymbolLocator

# Enough evidence to justify a ranking without turning the panel into
# a log. The UI shows these behind a disclosure, not inline.
EVIDENCE_PER_FILE = 12

# Structural edges shown per file, closest first.
STRUCTURAL_PER_FILE = 6

RELEVANT_FILES = 10


class AnalysisRunner:
    """
    Coordinates one end-to-end analysis for the HTTP layer.

    AnalyzeIssueService is deliberately free of GitHub and of the
    diagnosis step: it takes a file set and returns an analysis
    package. Something still has to fetch the repository, invoke the
    diagnosis layer and shape the result for a client, and that is
    this class. It owns no pipeline logic of its own.
    """

    def __init__(self, github_service, llm_service=None):
        self.github = github_service
        self.llm = llm_service

    @property
    def diagnosis_available(self):
        return self.llm is not None

    # =========================================================
    # PUBLIC API
    # =========================================================

    def run(self, owner, repo, issue_number, on_stage=None):
        def stage(name):
            if on_stage:
                on_stage(name)

        stage("fetching_issue")
        issue = self._fetch_issue(owner, repo, issue_number)

        stage("fetching_source")
        files = self.github.get_repository_source_files(owner, repo)

        stage("extracting_signals")
        service = build_analyze_issue_service(
            files,
            llm_service=self.llm,
        )

        stage("ranking")
        analysis = service.analyze(
            files=files,
            issue={
                "title": issue.get("title") or "",
                "body": issue.get("body") or "",
            },
            available_n=RELEVANT_FILES,
        )

        result = {
            # Source for the ranked files, so the client can show the
            # code behind a claim instead of only asserting it. Kept
            # off the analysis payload and served per file, because a
            # repository's source does not belong in a poll response.
            "sources": self._sources(analysis, files),
            "issue": {
                "number": issue.get("number"),
                "title": issue.get("title") or "",
                "body": issue.get("body") or "",
                "state": issue.get("state") or "open",
                "html_url": issue.get("html_url"),
                "comments": issue.get("comments", 0),
            },
            "signals": analysis["signals"],
            "relevant_files": self._describe(analysis),
            "diagnosis": None,
            "diagnosis_error": None,
        }

        # Retained so a follow-up question can be answered against the
        # same evidence the diagnosis was produced from.
        result["context"] = {
            "signals": analysis["signals"],
            "ranked": analysis["ranked"][:RELEVANT_FILES],
        }

        if not self.diagnosis_available:
            result["diagnosis_error"] = (
                "No language model is configured, so only retrieval "
                "results are available."
            )
            return result

        stage("diagnosing")

        try:
            diagnosis = IssueDiagnosisService(
                llm_service=self.llm,
            ).diagnose(analysis)

            # The model named the symbols; where they live is decided
            # here, from the code. Anything unresolvable is dropped,
            # so navigation degrades to file level rather than
            # pointing somewhere wrong.
            #
            # The two lists stay separate all the way to the UI.
            # "View root cause" must land on the defect, and the first
            # SUPPORTING symbol the model happened to mention is not
            # that — it is usually a type the defect merely refers to.
            self.attach_locations(diagnosis, files)

            result["diagnosis"] = diagnosis

        except Exception as e:
            # Retrieval succeeded and is worth returning on its own.
            # A diagnosis failure must not discard it.
            result["diagnosis_error"] = str(e)

        return result

    # =========================================================
    # INTERNALS
    # =========================================================

    def _fetch_issue(self, owner, repo, issue_number):
        issue = self.github.get_issue(owner, repo, issue_number)

        if not isinstance(issue, dict) or "number" not in issue:
            raise IssueNotFound(
                f"Issue #{issue_number} not found in {owner}/{repo}"
            )

        return issue

    @staticmethod
    def attach_locations(diagnosis, files):
        """
        Resolve the symbols a diagnosis named to file and line.

        Shared with the offline benchmark runner so both take exactly
        the same path; a benchmark measuring different behaviour from
        production measures nothing.
        """

        locator = DartSymbolLocator()

        # Index product code only. Retrieval and evidence already
        # exclude tests; the locator must too, or a name declared
        # once in `lib/` and once in a test looks ambiguous and is
        # dropped. `main` is exactly that case.
        search = RepositorySearchService()

        index = locator.build_index([
            file
            for file in files
            if search.is_candidate_file(file)
        ])

        diagnosis["root_cause_locations"] = locator.resolve(
            diagnosis.get("root_cause_symbols"),
            index=index,
        )

        diagnosis["locations"] = locator.resolve(
            diagnosis.get("symbols"),
            index=index,
        )

        return diagnosis

    @staticmethod
    def _sources(analysis, files):
        """Source text for every file the client can open."""

        wanted = {
            entry["path"]
            for entry in analysis["ranked"][:RELEVANT_FILES]
        }

        return {
            file["path"]: file.get("content", "")
            for file in files
            if file["path"] in wanted
        }

    @staticmethod
    def _describe(analysis):
        """
        Attach the strongest evidence to each ranked file.

        A ranked list without its reasons is only an assertion, so the
        UI is given what put each file where it is.
        """

        by_path = {}

        for item in analysis.get("direct_evidence") or []:

            file = item.get("file") or {}
            path = file.get("path")

            if not path:
                continue

            by_path.setdefault(path, []).append(item)

        # Structural edges, keyed by the file they point at. Only the
        # closest edge of each (relationship, source) pair is kept —
        # the same rule ranking applies, so the UI does not show ten
        # copies of one relationship.
        structural_by_path = {}

        for edge in analysis.get("structural_results") or []:

            target = edge.get("target")
            source = edge.get("source")
            relationship = edge.get("relationship")

            if not target or not source or not relationship:
                continue

            bucket = structural_by_path.setdefault(target, {})
            key = (relationship, source)
            distance = edge.get("distance", 99)

            if key not in bucket or distance < bucket[key]:
                bucket[key] = distance

        described = []

        for entry in analysis["ranked"][:RELEVANT_FILES]:

            evidence = sorted(
                by_path.get(entry["path"], []),
                key=lambda item: item.get("strength", 0),
                reverse=True,
            )[:EVIDENCE_PER_FILE]

            edges = sorted(
                (
                    {
                        "relationship": relationship,
                        "source": source,
                        "distance": distance,
                    }
                    for (relationship, source), distance
                    in structural_by_path.get(entry["path"], {}).items()
                ),
                key=lambda edge: (edge["distance"], edge["source"]),
            )[:STRUCTURAL_PER_FILE]

            described.append({
                "rank": entry["rank"],
                "path": entry["path"],
                "total_score": round(entry.get("total_score", 0), 3),
                "signals_matched": entry.get("signals_matched", 0),
                "structural": edges,
                "evidence": [
                    {
                        "concept": item.get("concept", ""),
                        "kind": item.get("evidence_type", ""),
                        "identifier": item.get("identifier", ""),
                        "line": item.get("line", 0),
                    }
                    for item in evidence
                ],
            })

        return described
