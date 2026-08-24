import json

from app.services.issue_signal_extraction_service import (
    IssueSignalExtractionService,
)


class FakeLLMService:

    def __init__(self, response):
        self.response = response
        self.prompt = None

    def ask(self, prompt):
        self.prompt = prompt
        return self.response


def test_extracts_valid_signals():

    fake_llm = FakeLLMService(
        json.dumps({
            "signals": [
                {
                    "term": "refresh",
                    "type": "behavior",
                },
                {
                    "term": "loading",
                    "type": "behavior",
                },
                {
                    "term": "task",
                    "type": "domain",
                },
            ]
        })
    )

    service = (
        IssueSignalExtractionService(
            llm_service=fake_llm
        )
    )

    signals = service.extract_signals(
        "App gets stuck after refresh",
        "The loading spinner never disappears.",
    )

    assert signals == [
        {
            "term": "refresh",
            "type": "behavior",
        },
        {
            "term": "loading",
            "type": "behavior",
        },
        {
            "term": "task",
            "type": "domain",
        },
    ]


def test_prompt_contains_issue_text():

    fake_llm = FakeLLMService(
        json.dumps({
            "signals": [
                {
                    "term": "loading",
                    "type": "behavior",
                }
            ]
        })
    )

    service = (
        IssueSignalExtractionService(
            llm_service=fake_llm
        )
    )

    service.extract_signals(
        "Refresh is broken",
        "The spinner never stops.",
    )

    assert "Refresh is broken" in (
        fake_llm.prompt
    )

    assert "The spinner never stops." in (
        fake_llm.prompt
    )


def test_duplicate_signals_are_removed():

    fake_llm = FakeLLMService(
        json.dumps({
            "signals": [
                {
                    "term": "loading",
                    "type": "behavior",
                },
                {
                    "term": "loading",
                    "type": "behavior",
                },
                {
                    "term": "task",
                    "type": "domain",
                },
            ]
        })
    )

    service = (
        IssueSignalExtractionService(
            llm_service=fake_llm
        )
    )

    signals = service.extract_signals(
        "Refresh problem",
        "Loading never finishes.",
    )

    assert signals == [
        {
            "term": "loading",
            "type": "behavior",
        },
        {
            "term": "task",
            "type": "domain",
        },
    ]


def test_invalid_signal_type_is_removed():

    fake_llm = FakeLLMService(
        json.dumps({
            "signals": [
                {
                    "term": "loading",
                    "type": "behavior",
                },
                {
                    "term": "something",
                    "type": "nonsense",
                },
            ]
        })
    )

    service = (
        IssueSignalExtractionService(
            llm_service=fake_llm
        )
    )

    signals = service.extract_signals(
        "Refresh problem",
        "Loading never finishes.",
    )

    assert signals == [
        {
            "term": "loading",
            "type": "behavior",
        }
    ]


def test_invalid_json_is_rejected():

    fake_llm = FakeLLMService(
        "not json"
    )

    service = (
        IssueSignalExtractionService(
            llm_service=fake_llm
        )
    )

    try:
        service.extract_signals(
            "Refresh problem",
            "Loading never finishes.",
        )

    except ValueError:
        return

    assert False, (
        "Invalid JSON should be rejected"
    )