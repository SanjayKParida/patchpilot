"""
Language-agnostic patch generation from bounded context.

Receives only issue, diagnosis, and ContextPackage. Does not search
the repository or assemble its own context.
"""

import json
import logging
import time

from app.code_intelligence.types import ContextPackage
from app.services.patch_context import validate_hunks
from app.services.patch_types import (
    STATUS_AMBIGUOUS,
    STATUS_EMPTY,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_INVALID,
    STATUS_OK,
    VALID_STATUSES,
    PatchHunk,
    PatchProposal,
)

logger = logging.getLogger(__name__)


class PatchGeneratorService:
    """
    Produces structured patch proposals from supplied context.

    `llm_service` is reserved for a later `generate()` implementation.
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service

    def build_prompt(
        self,
        issue,
        diagnosis,
        context_package,
    ):
        """
        Assemble the model prompt from supplied inputs only.

        Does not call the model. Returns a deterministic string for
        the same inputs.
        """

        issue = issue or {}
        diagnosis = diagnosis or {}

        sections = [
            self._rules_section(),
            self._issue_section(issue),
            self._diagnosis_section(diagnosis),
            self._context_warnings_section(context_package),
            self._slices_section(context_package),
            self._response_schema_section(),
        ]

        return "\n\n".join(section for section in sections if section)

    def validate_proposal_hunks(self, hunks_by_path, context_package):
        """
        Context-anchor raw hunks before a proposal is finalized.

        Exposed for tests and for the parse/validate path.
        """

        slices = self._slices_from_package(context_package)
        return validate_hunks(hunks_by_path, slices)

    def generate(self, issue, diagnosis, context_package):
        """
        Ask the model for a patch proposal and validate it against
        the supplied context slices.

        Parse or validation failures return a PatchProposal with
        status=invalid/empty rather than raising, so callers can
        keep diagnosis and context alongside the failure.
        """

        started = time.monotonic()
        logger.info("patch_generator_start")

        slices = self._slices_from_package(context_package)

        if not slices:
            logger.info(
                "patch_proposal_parse_validation_end elapsed_ms=%s status=empty",
                int((time.monotonic() - started) * 1000),
            )
            return empty_context_proposal(
                "no context slices supplied"
            )

        if self.llm is None:
            logger.info(
                "patch_proposal_parse_validation_end elapsed_ms=%s status=invalid",
                int((time.monotonic() - started) * 1000),
            )
            return invalid_proposal(
                "LLM service is not configured"
            )

        prompt = self.build_prompt(
            issue,
            diagnosis,
            context_package,
        )

        try:
            response = self.llm.ask(prompt)
        except Exception as exc:
            logger.info(
                "patch_proposal_parse_validation_end elapsed_ms=%s status=invalid",
                int((time.monotonic() - started) * 1000),
            )
            return invalid_proposal(
                f"LLM call failed: {exc}"
            )

        proposal = self._build_proposal(
            response,
            context_package,
        )
        logger.info(
            "patch_proposal_parse_validation_end elapsed_ms=%s status=%s",
            int((time.monotonic() - started) * 1000),
            proposal.status,
        )
        return proposal

    # =========================================================
    # PARSE / VALIDATE
    # =========================================================

    def _build_proposal(self, response, context_package):
        try:
            data = self._parse_response(response)
        except ValueError as exc:
            return invalid_proposal(str(exc))

        try:
            parsed = self._validate_proposal_payload(data)
        except ValueError as exc:
            return invalid_proposal(str(exc))

        refusal_statuses = {
            STATUS_INSUFFICIENT_CONTEXT,
            STATUS_AMBIGUOUS,
            STATUS_EMPTY,
        }

        if (
            parsed["status"] in refusal_statuses
            and not parsed["hunks_by_path"]
        ):
            return PatchProposal(
                status=parsed["status"],
                summary=parsed["summary"],
                reasoning=parsed["reasoning"],
                confidence=parsed["confidence"],
                files=[],
                warnings=parsed["warnings"],
                errors=[],
            )

        anchored = self.validate_proposal_hunks(
            parsed["hunks_by_path"],
            context_package,
        )

        warnings = list(parsed["warnings"])
        errors = list(anchored.errors)

        if anchored.files:
            return PatchProposal(
                status=STATUS_OK,
                summary=parsed["summary"],
                reasoning=parsed["reasoning"],
                confidence=parsed["confidence"],
                files=anchored.files,
                warnings=warnings,
                errors=errors,
            )

        if parsed["status"] in refusal_statuses:
            final_status = parsed["status"]
        elif parsed["hunks_by_path"]:
            final_status = STATUS_EMPTY
        else:
            final_status = STATUS_EMPTY

        return PatchProposal(
            status=final_status,
            summary=parsed["summary"],
            reasoning=parsed["reasoning"],
            confidence=None,
            files=[],
            warnings=warnings,
            errors=errors,
        )

    def _parse_response(self, response):
        if response is None:
            raise ValueError("LLM returned no response")

        if isinstance(response, dict):
            return response

        text = str(response).strip()

        if not text:
            raise ValueError("LLM returned an empty response")

        text = self._strip_code_fences(text)

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "LLM response is not valid JSON"
            ) from exc

    def _validate_proposal_payload(self, data):
        if not isinstance(data, dict):
            raise ValueError(
                "Patch proposal must be a JSON object"
            )

        required = (
            "status",
            "summary",
            "reasoning",
            "files",
        )

        missing = [
            key for key in required if key not in data
        ]

        if missing:
            raise ValueError(
                "Patch proposal is missing required fields: "
                + ", ".join(missing)
            )

        status = data["status"]

        if not isinstance(status, str):
            raise ValueError("status must be a string")

        status = status.strip()

        if status not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of: "
                f"{', '.join(sorted(VALID_STATUSES))}"
            )

        summary = data["summary"]
        reasoning = data["reasoning"]

        if not isinstance(summary, str):
            raise ValueError("summary must be a string")

        if not isinstance(reasoning, str):
            raise ValueError("reasoning must be a string")

        confidence = data.get("confidence")

        if confidence is not None:
            if isinstance(
                confidence,
                bool,
            ) or not isinstance(
                confidence,
                (int, float),
            ):
                raise ValueError(
                    "confidence must be a number or null"
                )

            if not 0 <= confidence <= 1:
                raise ValueError(
                    "confidence must be between 0 and 1"
                )

            confidence = float(confidence)

        warnings = self._clean_string_list(
            data.get("warnings"),
            "warnings",
        )

        if not isinstance(data["files"], list):
            raise ValueError("files must be a list")

        hunks_by_path = self._extract_hunks_by_path(
            data["files"]
        )

        if status == STATUS_OK and not hunks_by_path:
            raise ValueError(
                "status ok requires at least one hunk"
            )

        if status == STATUS_OK and confidence is None:
            raise ValueError(
                "confidence is required when status is ok"
            )

        return {
            "status": status,
            "summary": summary.strip(),
            "reasoning": reasoning.strip(),
            "confidence": confidence,
            "warnings": warnings,
            "hunks_by_path": hunks_by_path,
        }

    @staticmethod
    def _extract_hunks_by_path(files):
        hunks_by_path = {}

        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError(
                    "every file entry must be an object"
                )

            path = entry.get("path")

            if not isinstance(path, str):
                raise ValueError(
                    "every file entry must include a path string"
                )

            path = path.strip()

            if not path:
                continue

            raw_hunks = entry.get("hunks")

            if raw_hunks is None:
                raw_hunks = []

            if not isinstance(raw_hunks, list):
                raise ValueError(
                    f"hunks for {path} must be a list"
                )

            parsed_hunks = []

            for hunk in raw_hunks:
                parsed_hunks.append(
                    PatchGeneratorService._parse_hunk(
                        path,
                        hunk,
                    )
                )

            if parsed_hunks:
                hunks_by_path.setdefault(
                    path,
                    [],
                ).extend(parsed_hunks)

        return hunks_by_path

    @staticmethod
    def _parse_hunk(path, hunk):
        if not isinstance(hunk, dict):
            raise ValueError(
                f"every hunk in {path} must be an object"
            )

        required = (
            "start_line",
            "end_line",
            "old_text",
            "new_text",
        )

        missing = [
            key for key in required if key not in hunk
        ]

        if missing:
            raise ValueError(
                f"hunk in {path} is missing required fields: "
                + ", ".join(missing)
            )

        start_line = hunk["start_line"]
        end_line = hunk["end_line"]

        if isinstance(
            start_line,
            bool,
        ) or not isinstance(
            start_line,
            int,
        ):
            raise ValueError(
                f"start_line in {path} must be an integer"
            )

        if isinstance(
            end_line,
            bool,
        ) or not isinstance(
            end_line,
            int,
        ):
            raise ValueError(
                f"end_line in {path} must be an integer"
            )

        old_text = hunk["old_text"]
        new_text = hunk["new_text"]

        if not isinstance(old_text, str):
            raise ValueError(
                f"old_text in {path} must be a string"
            )

        if not isinstance(new_text, str):
            raise ValueError(
                f"new_text in {path} must be a string"
            )

        return PatchHunk(
            start_line=start_line,
            end_line=end_line,
            old_text=old_text,
            new_text=new_text,
        )

    @staticmethod
    def _clean_string_list(value, field_name):
        if value is None:
            return []

        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")

        cleaned = []

        for item in value:
            if not isinstance(item, str):
                raise ValueError(
                    f"every {field_name} entry must be a string"
                )

            item = item.strip()

            if item and item not in cleaned:
                cleaned.append(item)

        return cleaned

    @staticmethod
    def _strip_code_fences(text):
        if text.startswith("```"):
            lines = text.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            return "\n".join(lines).strip()

        return text

    # =========================================================
    # PROMPT SECTIONS
    # =========================================================

    @staticmethod
    def _rules_section():
        return _section(
            "RULES",
            """
You are a senior software engineer proposing a minimal code patch.

You may use ONLY the issue, diagnosis, and numbered context slices
below. Do not search the repository. Do not invent files, symbols,
imports, or code that does not appear in the supplied slices.

Requirements:
- Modify only paths that appear in the context slices.
- Prefer edits at the defect site (tier 0) and root-cause locations.
- Preserve unrelated code outside the edited span.
- Use absolute 1-based file line numbers from the slice headers.
- Copy old_text EXACTLY from slice content, including whitespace.
- When context is insufficient to make a safe edit, return:
  status = "insufficient_context", files = [], and explain why.
- When the correct target is unclear, return status = "ambiguous".
- Return JSON only. No markdown fences.
""".strip(),
        )

    @staticmethod
    def _issue_section(issue):
        title = (issue.get("title") or "").strip()
        body = (issue.get("body") or "").strip()

        return _section(
            "ISSUE",
            f"TITLE:\n{title}\n\nBODY:\n{body}",
        )

    @staticmethod
    def _diagnosis_section(diagnosis):
        lines = [
            f"ROOT CAUSE:\n{(diagnosis.get('root_cause') or '').strip()}",
            f"CONFIDENCE:\n{diagnosis.get('confidence', '')}",
            f"EXPLANATION:\n{(diagnosis.get('explanation') or '').strip()}",
            f"SUGGESTED FIX:\n{(diagnosis.get('suggested_fix') or '').strip()}",
        ]

        root_cause_locations = diagnosis.get("root_cause_locations") or []
        if root_cause_locations:
            lines.append("ROOT CAUSE LOCATIONS:")
            for location in root_cause_locations:
                lines.append(
                    "  "
                    f"{location.get('symbol')} -> "
                    f"{location.get('path')}:{location.get('line')} "
                    f"({location.get('kind')})"
                )

        locations = diagnosis.get("locations") or []
        if locations:
            lines.append("SUPPORTING LOCATIONS:")
            for location in locations:
                lines.append(
                    "  "
                    f"{location.get('symbol')} -> "
                    f"{location.get('path')}:{location.get('line')} "
                    f"({location.get('kind')})"
                )

        relevant = diagnosis.get("relevant_files") or []
        if relevant:
            lines.append("RELEVANT FILES (diagnosis cited):")
            for path in relevant:
                lines.append(f"  {path}")

        return _section("DIAGNOSIS", "\n".join(lines))

    @staticmethod
    def _context_warnings_section(package):
        if isinstance(package, ContextPackage):
            omitted = package.omitted
            warnings = package.warnings
            over_budget = package.budget.over_budget
            root_cause = package.root_cause
        else:
            package = package or {}
            omitted = package.get("omitted") or []
            warnings = package.get("warnings") or []
            budget = package.get("budget") or {}
            over_budget = budget.get("over_budget", False)
            root_cause = package.get("root_cause")

        lines = []

        if root_cause:
            lines.append(
                "PACKAGE ROOT CAUSE:"
                f" {root_cause.get('symbol')} -> "
                f"{root_cause.get('path')}:{root_cause.get('line')}"
            )

        if over_budget:
            lines.append(
                "WARNING: context package exceeded its soft budget."
            )

        for warning in warnings:
            lines.append(f"WARNING: {warning}")

        for entry in omitted:
            if isinstance(entry, dict):
                path = entry.get("path")
                reason = entry.get("reason")
            else:
                path = entry.path
                reason = entry.reason
            lines.append(f"OMITTED: {path} ({reason})")

        if not lines:
            lines.append("No context warnings.")

        return _section("CONTEXT WARNINGS", "\n".join(lines))

    @staticmethod
    def _slices_section(package):
        slices = PatchGeneratorService._slices_from_package(package)

        if not slices:
            return _section(
                "CONTEXT SLICES",
                "No context slices were supplied.",
            )

        parts = []

        for index, item in enumerate(slices, start=1):
            if isinstance(item, dict):
                path = item.get("path")
                start = item.get("start_line")
                end = item.get("end_line")
                tier = item.get("tier")
                reason = item.get("reason")
                symbols = item.get("symbols") or []
                truncated = item.get("truncated")
                content = item.get("content") or ""
            else:
                path = item.path
                start = item.start_line
                end = item.end_line
                tier = item.tier
                reason = item.reason
                symbols = list(item.symbols)
                truncated = item.truncated
                content = item.content or ""

            symbol_text = ", ".join(symbols) if symbols else "(none)"

            parts.append(
                f"--- SLICE {index} ---\n"
                f"PATH: {path}\n"
                f"LINES: {start}-{end}\n"
                f"TIER: {tier}\n"
                f"REASON: {reason}\n"
                f"SYMBOLS: {symbol_text}\n"
                f"TRUNCATED: {truncated}\n"
                f"CONTENT:\n```\n{content}\n```"
            )

        editable_paths = sorted({
            item["path"] if isinstance(item, dict) else item.path
            for item in slices
        })

        header = (
            "Editable paths (no others may be modified):\n"
            + "\n".join(f"  {path}" for path in editable_paths)
        )

        return _section(
            "CONTEXT SLICES",
            header + "\n\n" + "\n\n".join(parts),
        )

    @staticmethod
    def _response_schema_section():
        statuses = ", ".join(sorted(VALID_STATUSES))

        return _section(
            "RESPONSE FORMAT",
            f"""
Return JSON with exactly these fields:

{{
  "status": one of [{statuses}],
  "summary": "one-line description of the proposed change",
  "reasoning": "why these edits fix the issue using only supplied context",
  "confidence": number between 0 and 1, or null when refusing,
  "warnings": ["optional strings"],
  "files": [
    {{
      "path": "must appear in context slices",
      "hunks": [
        {{
          "start_line": 1,
          "end_line": 1,
          "old_text": "exact text copied from slice content",
          "new_text": "replacement text"
        }}
      ]
    }}
  ]
}}

When refusing to patch, set files to [] and use an appropriate status.
Return JSON only.
""".strip(),
        )

    @staticmethod
    def _slices_from_package(package):
        if isinstance(package, ContextPackage):
            return list(package.slices)

        package = package or {}
        return list(package.get("slices") or [])


def _section(title, content):
    return f"========== {title} ==========\n{content}"


def empty_context_proposal(reason):
    """Deterministic proposal when there is nothing to edit."""

    return PatchProposal(
        status=STATUS_INSUFFICIENT_CONTEXT,
        summary="No patch produced",
        reasoning=reason,
        confidence=None,
        files=[],
        warnings=[],
        errors=[],
    )


def invalid_proposal(message):
    """Deterministic proposal for parse or schema failures."""

    return PatchProposal(
        status=STATUS_INVALID,
        summary="No patch produced",
        reasoning="Patch generation failed during validation.",
        confidence=None,
        files=[],
        warnings=[],
        errors=[message],
    )
