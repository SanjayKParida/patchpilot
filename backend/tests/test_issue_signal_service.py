from app.services.issue_signal_service import IssueSignalService


def test_control_signals_ignore_issue_text():
    service = IssueSignalService()

    first = service.extract_signals(
        "Cars keep loading indefinitely",
        "The list never appears.",
    )
    second = service.extract_signals("", "")

    assert first == second
    assert {
        signal["term"] for signal in first
    } == {
        "firebase",
        "firestore",
        "loading",
        "car",
        "repository",
        "bloc",
    }


def test_control_signals_are_independent_copies():
    service = IssueSignalService()
    signals = service.extract_signals("a", "b")
    signals[0]["term"] = "mutated"

    original = service.extract_signals("a", "b")
    assert original[0]["term"] == "firebase"
