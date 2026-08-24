import json


class IssueSignalExtractionService:
    """
    Extracts structured issue signals using an LLM.

    This service has the same public interface expected by
    AnalyzeIssueService:

        extract_signals(title, body)

    It does NOT:
        - search the repository
        - rank files
        - diagnose the issue
        - inspect repository code

    It only converts issue text into a small, structured
    vocabulary used by the deterministic retrieval pipeline.
    """

    ALLOWED_TYPES = {
        "technology",
        "behavior",
        "domain",
        "architecture",
        "data",
        "ui",
        "error",
    }

    def __init__(self, llm_service):
        if llm_service is None:
            raise ValueError(
                "llm_service is required"
            )

        self.llm_service = llm_service

    # ========================================================
    # PUBLIC API
    # ========================================================

    def extract_signals(
        self,
        title: str,
        body: str
    ):
        """
        Extract issue signals from title and body.

        Returns:

            [
                {
                    "term": "loading",
                    "type": "behavior"
                },
                ...
            ]
        """

        prompt = self._build_prompt(
            title,
            body
        )

        response = self.llm_service.ask(
            prompt
        )

        return self._parse_response(
            response
        )

    # ========================================================
    # PROMPT
    # ========================================================

    def _build_prompt(
        self,
        title,
        body
    ):
        return f"""
Extract a small set of retrieval signals from this software bug report.

The signals will be used to search a source-code repository.

Your task is ONLY to extract retrieval signals.
Do not diagnose the bug.
Do not identify the faulty file.
Do not propose a fix.

IMPORTANT:
You do not have access to the repository code.
Never invent class names, function names, file names, architecture
components, or other identifiers that are not explicitly present in
the issue.

Extract concepts that are explicitly stated or directly normalized
from the issue text.

Prefer short, atomic, repository-search-friendly terms.

Examples:
- "Active filter" -> "active", "filter"
- "completed tasks" -> "completed", "task"
- "task list" -> "task"
- "refresh action" -> "refresh"
- "loading spinner" -> "loading"
- "empty state" -> "empty"
- "local storage" -> "storage"

For an explicitly mentioned code identifier, preserve its original
casing. For example:
- "isCompleted" -> "isCompleted"
- "TaskBloc" -> "TaskBloc"

Do not invent:
- "Active filter" -> "getActiveTasks"
- "task storage" -> "TaskRepository"
- "filtering tasks" -> "GetFilteredTasks"

Avoid incidental UI details unless they are central to the bug:
- app bar
- icon
- chip
- tab
- button

Avoid generic report wording such as:
- no error message
- works fine
- Android
- Chrome
- emulator

Prefer 3-6 useful signals.
Do not emit duplicate or near-duplicate phrases.

Allowed types:
- technology
- behavior
- domain
- architecture
- data
- ui
- error

Return JSON only:

{{
  "signals": [
    {{
      "term": "active",
      "type": "behavior"
    }},
    {{
      "term": "filter",
      "type": "behavior"
    }},
    {{
      "term": "completed",
      "type": "behavior"
    }}
  ]
}}

ISSUE TITLE:
{title}

ISSUE BODY:
{body}
""".strip()
    # ========================================================
    # RESPONSE PARSING
    # ========================================================

    def _parse_response(
        self,
        response
    ):
        if response is None:
            raise ValueError(
                "LLM returned no signal response"
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
                    "LLM returned an empty signal response"
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
                    "LLM signal response is not valid JSON"
                ) from exc

        return self._validate_signals(
            data
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    def _validate_signals(
        self,
        data
    ):
        if not isinstance(
            data,
            dict
        ):
            raise ValueError(
                "Signal response must be a JSON object"
            )

        signals = data.get(
            "signals"
        )

        if not isinstance(
            signals,
            list
        ):
            raise ValueError(
                "Signal response must contain a signals list"
            )

        validated = []

        seen = set()

        for signal in signals:

            if not isinstance(
                signal,
                dict
            ):
                continue

            term = signal.get(
                "term"
            )

            signal_type = signal.get(
                "type"
            )

            if not isinstance(
                term,
                str
            ):
                continue

            if not isinstance(
                signal_type,
                str
            ):
                continue

            term = term.strip()

            signal_type = (
                signal_type
                .strip()
                .lower()
            )

            if not term:
                continue

            if signal_type not in (
                self.ALLOWED_TYPES
            ):
                continue

            key = (
                term,
                signal_type
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            validated.append({
                "term": term,
                "type": signal_type
            })

        if not validated:
            raise ValueError(
                "LLM returned no valid signals"
            )

        return validated

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _strip_code_fences(
        text
    ):
        if not text.startswith(
            "```"
        ):
            return text

        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        return "\n".join(
            lines
        ).strip()