"""
Deterministic tests for AnalyzeIssueService.

Uses the frozen car-rental fixture and IssueSignalService so
pytest does not need GitHub, OpenAI, or network access.
"""

import contextlib
import io
import json
from pathlib import Path

from app.services.analyze_issue_service import (
    AnalyzeIssueService,
    build_analyze_issue_service,
)
from app.services.issue_signal_service import IssueSignalService


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "evalutation"
    / "fixtures"
    / "car_rental_app.json"
)


class FakeSignalService:
    def __init__(self, signals):
        self.signals = signals
        self.calls = []

    def extract_signals(self, title, body):
        self.calls.append((title, body))
        return list(self.signals)


def load_snapshot():
    snapshot = json.loads(FIXTURE_PATH.read_text())
    issue = snapshot["issue"]
    return snapshot["files"], {
        "title": issue.get("title") or "",
        "body": issue.get("body") or "",
    }


def run_analysis(signals=None, signal_service=None):
    files, issue = load_snapshot()

    service = build_analyze_issue_service(
        files,
        signal_service=signal_service or IssueSignalService(),
    )

    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        result = service.analyze(
            files=files,
            issue=issue,
            signals=signals,
            top_n=5,
            available_n=10,
        )

    return files, issue, result


def test_analyze_issue_service_returns_expected_shape():
    _, issue, result = run_analysis()

    assert result["issue"] == issue
    assert result["signals"]
    assert result["ranked"]
    assert result["primary_files"]
    assert "available_files" in result
    assert result["direct_evidence"]
    assert result["structural_results"]
    assert result["seed_paths"]


def test_control_signal_contract():
    _, _, result = run_analysis()

    assert {
        signal["term"]
        for signal in result["signals"]
    } == {
        "firebase",
        "firestore",
        "loading",
        "car",
        "repository",
        "bloc",
    }


def test_explicit_signals_bypass_the_signal_service():
    fake = FakeSignalService(
        [{"term": "loading", "type": "behavior"}]
    )

    files, issue = load_snapshot()
    service = build_analyze_issue_service(
        files,
        signal_service=fake,
    )

    injected = [
        {"term": "car", "type": "domain"},
        {"term": "bloc", "type": "architecture"},
    ]

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = service.analyze(
            files=files,
            issue=issue,
            signals=injected,
        )

    assert fake.calls == []
    assert result["signals"] == injected


def test_missing_signals_call_the_injected_service():
    fake = FakeSignalService(
        [{"term": "loading", "type": "behavior"}]
    )

    files, issue = load_snapshot()
    service = build_analyze_issue_service(
        files,
        signal_service=fake,
    )

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = service.analyze(
            files=files,
            issue=issue,
        )

    assert fake.calls == [(issue["title"], issue["body"])]
    assert result["signals"] == [
        {"term": "loading", "type": "behavior"}
    ]


def test_ranked_results_are_sorted():
    _, _, result = run_analysis()
    ranked = result["ranked"]

    assert ranked[0]["rank"] == 1
    scores = [item["total_score"] for item in ranked]
    assert scores == sorted(scores, reverse=True)


def test_phase5_tier_one_is_in_top_five():
    _, _, result = run_analysis()

    top_5 = {item["path"] for item in result["ranked"][:5]}

    assert {
        "lib/presentation/pages/car_list_screen.dart",
        "lib/presentation/bloc/car_bloc.dart",
        "lib/data/repositories/car_repository_impl.dart",
        "lib/data/datasources/firebase_car_data_source.dart",
        "lib/presentation/bloc/car_state.dart",
    }.issubset(top_5)


def test_phase5_tier_two_is_in_top_ten():
    _, _, result = run_analysis()

    top_10 = {item["path"] for item in result["ranked"][:10]}

    assert {
        "lib/domain/repositories/car_repository.dart",
        "lib/domain/usecases/get_cars.dart",
        "lib/main.dart",
        "lib/injection_container.dart",
        "lib/presentation/bloc/car_event.dart",
    }.issubset(top_10)


def test_known_distractors_are_not_in_top_five():
    _, _, result = run_analysis()

    top_5 = {item["path"] for item in result["ranked"][:5]}

    assert top_5.isdisjoint({
        "lib/firebase_options.dart",
        "lib/injection_container.dart",
        "lib/presentation/pages/car_details_page.dart",
        "lib/presentation/widgets/car_card.dart",
        "lib/presentation/widgets/more_card.dart",
        "lib/presentation/pages/MapsDetailsPage.dart",
        "lib/presentation/pages/onboarding_page.dart",
    })


def test_primary_files_match_top_five():
    _, _, result = run_analysis()

    assert [
        file["path"] for file in result["primary_files"]
    ] == [
        item["path"] for item in result["ranked"][:5]
    ]

    assert len(result["primary_files"]) == 5

    for file in result["primary_files"]:
        assert file["content"].strip()


def test_available_files_match_rank_six_to_ten():
    _, _, result = run_analysis()

    assert result["available_files"] == [
        item["path"] for item in result["ranked"][5:10]
    ]


def test_primary_and_available_files_do_not_overlap():
    _, _, result = run_analysis()

    primary = {file["path"] for file in result["primary_files"]}
    available = set(result["available_files"])
    assert primary.isdisjoint(available)


def test_repeated_analysis_has_same_ranking():
    files, issue = load_snapshot()
    service = build_analyze_issue_service(
        files,
        signal_service=IssueSignalService(),
    )

    with contextlib.redirect_stdout(io.StringIO()):
        first = service.analyze(files=files, issue=issue)
        second = service.analyze(files=files, issue=issue)

    def ranking(result):
        return [
            (item["path"], round(item["total_score"], 10))
            for item in result["ranked"]
        ]

    assert ranking(first) == ranking(second)


def test_analyze_requires_issue_and_files():
    files, issue = load_snapshot()
    service = build_analyze_issue_service(
        files,
        signal_service=IssueSignalService(),
    )

    try:
        service.analyze(files=files, issue=None)
        assert False, "expected ValueError"
    except ValueError:
        pass

    try:
        service.analyze(files=[], issue=issue)
        assert False, "expected ValueError"
    except ValueError:
        pass

    assert isinstance(service, AnalyzeIssueService)


def test_production_factory_uses_extraction_service():
    from app.services.issue_signal_extraction_service import (
        IssueSignalExtractionService,
    )

    class DummyLLM:
        def ask(self, prompt):
            raise AssertionError("LLM should not be called")

    files, _ = load_snapshot()
    service = build_analyze_issue_service(
        files,
        llm_service=DummyLLM(),
    )

    assert isinstance(
        service.signal_service,
        IssueSignalExtractionService,
    )
