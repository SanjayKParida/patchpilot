"""
Shared helpers for real-LLM / real-GitHub integration tests.

Deterministic unit tests must not import this module's network
helpers at collection time in a way that contacts the network.
Loading a GitHub repository happens only when a test calls
`load_task_demo_files()`.
"""

import json
import os
from pathlib import Path

from app.services.analyze_issue_service import (
    build_analyze_issue_service,
)
from app.services.github_service import GithubService
from app.services.issue_signal_service import IssueSignalService


CASES_DIR = (
    Path(__file__).resolve().parents[2]
    / "evalutation"
    / "cases"
)

TASK_DEMO_OWNER = "SanjayKParida"
TASK_DEMO_REPO = "patchpilot-diagnosis-demo"


def load_case(name):
    path = CASES_DIR / f"{name}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Case not found: {path}"
        )

    return json.loads(path.read_text())


def load_task_demo_files():
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set")

    github = GithubService(token)
    github.authenticate()

    files = github.get_repository_source_files(
        TASK_DEMO_OWNER,
        TASK_DEMO_REPO,
    )

    if not files:
        raise RuntimeError(
            "No repository source files found"
        )

    return files


def build_control_analysis_service(files):
    """AnalyzeIssueService using hardcoded control signals."""

    return build_analyze_issue_service(
        files,
        signal_service=IssueSignalService(),
    )
