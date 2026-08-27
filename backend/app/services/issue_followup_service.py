from app.errors import UpstreamUnavailable

MAX_QUESTION_CHARS = 500
MAX_FILE_CHARS = 6000
MAX_CONTEXT_FILES = 5


class IssueFollowUpService:
    """
    Answers one question about an analysis that has already run.

    Deliberately not a conversation. Each question is answered against
    the same fixed evidence the diagnosis was produced from — the
    issue, the signals, the ranked files and their source — so an
    answer can never drift onto code the analysis never looked at.

    There is no transcript and no memory between questions. That keeps
    the guarantee simple: every answer is grounded in the analysis, not
    in whatever was said earlier.
    """

    def __init__(self, llm_service):
        self.llm_service = llm_service

    def answer(self, question, analysis, sources):
        question = (question or "").strip()

        if not question:
            raise ValueError("A question is required")

        if not self.llm_service:
            raise UpstreamUnavailable(
                "No language model is configured"
            )

        response = self.llm_service.ask(
            self._prompt(
                question[:MAX_QUESTION_CHARS],
                analysis,
                sources,
            )
        )

        return (response or "").strip()

    # =========================================================
    # PROMPT
    # =========================================================

    def _prompt(self, question, analysis, sources):
        issue = analysis.get("issue") or {}
        diagnosis = analysis.get("diagnosis") or {}
        context = analysis.get("context") or {}

        signals = ", ".join(
            f"{signal['term']} ({signal['type']})"
            for signal in context.get("signals") or []
        ) or "none"

        ranked = "\n".join(
            f"{entry['rank']}. {entry['path']}"
            for entry in analysis.get("relevant_files") or []
        ) or "none"

        # Prefer the files the diagnosis leaned on; they are what a
        # follow-up is almost always about.
        cited = diagnosis.get("relevant_files") or []

        chosen = [path for path in cited if path in sources]

        for entry in analysis.get("relevant_files") or []:
            if len(chosen) >= MAX_CONTEXT_FILES:
                break
            if entry["path"] in sources and entry["path"] not in chosen:
                chosen.append(entry["path"])

        source_text = "\n\n".join(
            f"--- {path} ---\n{sources[path][:MAX_FILE_CHARS]}"
            for path in chosen[:MAX_CONTEXT_FILES]
        ) or "no source available"

        return f"""You are answering a developer's follow-up question about a
bug analysis that has already been performed.

Answer ONLY from the material below. If it does not contain the answer,
say so plainly rather than guessing. Reference real file paths and
identifiers. Be concise — a few sentences, not an essay. Plain prose,
no JSON, no markdown headings.

ISSUE #{issue.get('number')}: {issue.get('title')}

{(issue.get('body') or '')[:2000]}

SIGNALS: {signals}

RANKED FILES:
{ranked}

DIAGNOSIS:
root cause: {diagnosis.get('root_cause') or 'not available'}
explanation: {diagnosis.get('explanation') or 'not available'}
suggested fix: {diagnosis.get('suggested_fix') or 'not available'}

SOURCE:
{source_text}

QUESTION: {question}
"""
