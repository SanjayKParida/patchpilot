import json


class IssueDiagnosisService:
    """
    Turns the deterministic repository analysis produced by
    AnalyzeIssueService into a structured diagnosis by asking
    an LLM.

    This service does NOT:
        - search the repository
        - rank files
        - build the repository graph
        - perform language-specific analysis

    Those responsibilities belong to AnalyzeIssueService and
    its underlying services.

    This service only:
        1. validates the analysis package
        2. builds the diagnosis prompt
        3. calls LLMService
        4. parses the structured response
    """

    def __init__(self, llm_service):
        if llm_service is None:
            raise ValueError(
                "llm_service is required"
            )

        self.llm_service = llm_service

    # =========================================================
    # PUBLIC API
    # =========================================================

    def diagnose(self, analysis):
        """
        Diagnose an issue from an AnalyzeIssueService result.
        """

        if not analysis:
            raise ValueError(
                "analysis is required"
            )

        prompt = self._build_prompt(
            analysis
        )

        response = self.llm_service.ask(
            prompt
        )

        return self._parse_response(
            response
        )

    # =========================================================
    # PROMPT
    # =========================================================

    def _build_prompt(self, analysis):
        issue = analysis.get(
            "issue",
            {}
        )

        signals = analysis.get(
            "signals",
            []
        )

        ranked = analysis.get(
            "ranked",
            []
        )

        primary_files = analysis.get(
            "primary_files",
            []
        )

        available_files = analysis.get(
            "available_files",
            []
        )

        direct_evidence = analysis.get(
            "direct_evidence",
            []
        )

        structural_results = analysis.get(
            "structural_results",
            []
        )

        sections = []

        # -----------------------------------------------------
        # Role
        # -----------------------------------------------------

        sections.append(
            """
You are a senior software debugging assistant.

Your task is to diagnose the reported software issue using
only the repository context provided below.

The ranked files were selected by a deterministic retrieval
system. Ranking indicates relevance, NOT causality.

Do not assume the highest-ranked file is the root cause.

Do not invent code, runtime behavior, or dependencies that
are not supported by the supplied repository context.
""".strip()
        )

        # -----------------------------------------------------
        # Issue
        # -----------------------------------------------------

        issue_title = issue.get(
            "title",
            ""
        )

        issue_body = issue.get(
            "body",
            ""
        )

        sections.append(
            self._section(
                "ISSUE",
                (
                    f"Title:\n{issue_title}\n\n"
                    f"Body:\n{issue_body}"
                )
            )
        )

        # -----------------------------------------------------
        # Signals
        # -----------------------------------------------------

        signal_lines = []

        for signal in signals:

            term = signal.get(
                "term",
                ""
            )

            signal_type = signal.get(
                "type",
                ""
            )

            signal_lines.append(
                f"- {term} [{signal_type}]"
            )

        sections.append(
            self._section(
                "ISSUE SIGNALS",
                "\n".join(
                    signal_lines
                )
            )
        )

        # -----------------------------------------------------
        # Ranked candidates
        # -----------------------------------------------------

        ranking_lines = []

        for item in ranked:

            rank = item.get(
                "rank"
            )

            path = item.get(
                "path"
            )

            score = item.get(
                "total_score",
                0
            )

            ranking_lines.append(
                f"Rank {rank}: "
                f"{path} "
                f"(score={score:.4f})"
            )

        sections.append(
            self._section(
                "RANKED CANDIDATES",
                "\n".join(
                    ranking_lines
                )
            )
        )

        # -----------------------------------------------------
        # Primary files
        # -----------------------------------------------------

        primary_sections = []

        for index, file in enumerate(
            primary_files,
            start=1
        ):

            path = file.get(
                "path",
                ""
            )

            content = file.get(
                "content",
                ""
            )

            primary_sections.append(
                (
                    f"--- PRIMARY FILE {index} ---\n"
                    f"PATH: {path}\n\n"
                    f"{content}"
                )
            )

        sections.append(
            self._section(
                "PRIMARY FILE CONTENT",
                "\n\n".join(
                    primary_sections
                )
            )
        )

        # -----------------------------------------------------
        # Available files
        # -----------------------------------------------------

        available_lines = [
            f"- {path}"
            for path in available_files
        ]

        sections.append(
            self._section(
                "ADDITIONAL AVAILABLE FILES",
                "\n".join(
                    available_lines
                ) if available_lines else
                "None"
            )
        )

        # -----------------------------------------------------
        # Direct evidence
        # -----------------------------------------------------

        evidence_lines = []

        for item in direct_evidence:

            file = item.get(
                "file",
                {}
            )

            path = file.get(
                "path",
                ""
            )

            evidence_type = item.get(
                "evidence_type",
                ""
            )

            concept = item.get(
                "concept",
                ""
            )

            strength = item.get(
                "strength",
                0
            )

            line = item.get(
                "line"
            )

            identifier = item.get(
                "identifier"
            )

            evidence_lines.append(
                f"- {path}: "
                f"{concept} → "
                f"{evidence_type} "
                f"'{identifier}' "
                f"(strength={strength}, "
                f"line={line})"
            )

        sections.append(
            self._section(
                "DIRECT EVIDENCE",
                "\n".join(
                    evidence_lines
                ) if evidence_lines else
                "None"
            )
        )

        # -----------------------------------------------------
        # Structural relationships
        # -----------------------------------------------------

        structural_lines = []

        for item in structural_results:

            source = item.get(
                "source",
                ""
            )

            target = item.get(
                "target",
                ""
            )

            relationship = item.get(
                "relationship",
                ""
            )

            distance = item.get(
                "distance"
            )

            structural_lines.append(
                f"- {source} "
                f"→ {target} "
                f"[{relationship}, "
                f"distance={distance}]"
            )

        sections.append(
            self._section(
                "STRUCTURAL RELATIONSHIPS",
                "\n".join(
                    structural_lines
                ) if structural_lines else
                "None"
            )
        )

        # -----------------------------------------------------
        # Task
        # -----------------------------------------------------

        sections.append(
            self._section(
                "TASK",
                """
Determine the most likely root cause of the reported issue.

Return JSON with exactly these fields:

{
  "root_cause": "string",
  "confidence": 0.0,
  "relevant_files": ["path"],
  "explanation": "string",
  "suggested_fix": "string"
}

Requirements:

- root_cause should describe the likely failure mechanism.
- confidence must be a number between 0 and 1.
- relevant_files should contain only repository files supported
  by the provided evidence.
- explanation should connect the issue to the supplied code.
- suggested_fix should describe the likely corrective action.
- Do not assume rank #1 is the culprit.
- Do not blame a configuration file merely because it contains
  a technology name.
- Do not claim certainty when the evidence is insufficient.
- Return JSON only.
""".strip()
            )
        )

        return "\n\n".join(
            sections
        )

    # =========================================================
    # RESPONSE PARSING
    # =========================================================

    def _parse_response(self, response):
        if response is None:
            raise ValueError(
                "LLM returned no response"
            )

        if isinstance(
            response,
            dict
        ):
            data = response

        else:

            text = str(
                response
            ).strip()

            if not text:
                raise ValueError(
                    "LLM returned an empty response"
                )

            text = self._strip_code_fences(
                text
            )

            try:
                data = json.loads(
                    text
                )

            except json.JSONDecodeError as exc:
                raise ValueError(
                    "LLM response is not valid JSON"
                ) from exc

        return self._validate_diagnosis(
            data
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    def _validate_diagnosis(
        self,
        data
    ):
        if not isinstance(
            data,
            dict
        ):
            raise ValueError(
                "Diagnosis must be a JSON object"
            )

        required = (
            "root_cause",
            "confidence",
            "relevant_files",
            "explanation",
            "suggested_fix",
        )

        missing = [
            key
            for key in required
            if key not in data
        ]

        if missing:
            raise ValueError(
                "Diagnosis is missing required fields: "
                + ", ".join(
                    missing
                )
            )

        if not isinstance(
            data["root_cause"],
            str
        ):
            raise ValueError(
                "root_cause must be a string"
            )

        if not isinstance(
            data["explanation"],
            str
        ):
            raise ValueError(
                "explanation must be a string"
            )

        if not isinstance(
            data["suggested_fix"],
            str
        ):
            raise ValueError(
                "suggested_fix must be a string"
            )

        confidence = data[
            "confidence"
        ]

        if isinstance(
            confidence,
            bool
        ) or not isinstance(
            confidence,
            (int, float)
        ):
            raise ValueError(
                "confidence must be a number"
            )

        if not 0 <= confidence <= 1:
            raise ValueError(
                "confidence must be between 0 and 1"
            )

        if not isinstance(
            data["relevant_files"],
            list
        ):
            raise ValueError(
                "relevant_files must be a list"
            )

        for path in data[
            "relevant_files"
        ]:

            if not isinstance(
                path,
                str
            ):
                raise ValueError(
                    "every relevant file must be a string"
                )

        return {
            "root_cause": data[
                "root_cause"
            ].strip(),

            "confidence": float(
                confidence
            ),

            "relevant_files": [
                path.strip()
                for path in data[
                    "relevant_files"
                ]
                if path.strip()
            ],

            "explanation": data[
                "explanation"
            ].strip(),

            "suggested_fix": data[
                "suggested_fix"
            ].strip(),
        }

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _section(
        title,
        content
    ):
        return (
            f"========== {title} ==========\n"
            f"{content}"
        )

    @staticmethod
    def _strip_code_fences(
        text
    ):
        """
        Handle models that return:

        ```json
        {...}
        ```

        even though the prompt requests raw JSON.
        """

        if text.startswith(
            "```"
        ):

            lines = text.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            return "\n".join(
                lines
            ).strip()

        return text