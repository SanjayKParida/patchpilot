"""
Run retrieval + ranking offline against a frozen fixture.

Wiring lives in AnalyzeIssueService. This module only loads a
snapshot and returns the analysis package that `score_ranking`
measures.

Nothing here scores or judges.
"""

import contextlib
import io
import json
from pathlib import Path

from app.services.analyze_issue_service import (
    build_analyze_issue_service,
)
from app.services.issue_signal_service import IssueSignalService


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name):
    """Load a frozen repository snapshot by name or path."""

    path = Path(name)

    if not path.exists():
        path = FIXTURE_DIR / f"{name}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"no fixture named {name} "
            f"(looked in {FIXTURE_DIR})"
        )

    return json.loads(path.read_text())


def run(snapshot, signals=None):
    """
    Run AnalyzeIssueService over a snapshot.

    When `signals` is omitted, the hardcoded IssueSignalService
    is used so ranking evaluation stays independent of the LLM.
    Benchmark cases should pass their manual signals explicitly.
    """

    files = snapshot["files"]
    raw_issue = snapshot.get("issue") or {}

    issue = {
        "title": raw_issue.get("title") or "",
        "body": raw_issue.get("body") or "",
    }

    service = build_analyze_issue_service(
        files,
        signal_service=IssueSignalService(),
    )

    return service.analyze(
        files=files,
        issue=issue,
        signals=signals,
    )


def run_quiet(snapshot, signals=None):
    """Run the pipeline with service debug printing suppressed."""

    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        return run(snapshot, signals=signals)
