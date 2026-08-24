class IssueSignalService:
    """
    Hardcoded control / reference signal provider.

    Production analysis uses IssueSignalExtractionService, which
    reads the issue text. This class ignores the issue and returns
    a fixed vocabulary so ranking and retrieval can be measured
    independently of the LLM.

    AnalyzeIssueService still accepts explicit `signals=` so
    benchmark cases can inject their own manual signals without
    going through either provider.
    """

    CONTROL_SIGNALS = [
        {"term": "firebase", "type": "technology"},
        {"term": "firestore", "type": "technology"},
        {"term": "loading", "type": "behavior"},
        {"term": "car", "type": "domain"},
        {"term": "repository", "type": "architecture"},
        {"term": "bloc", "type": "architecture"},
    ]

    def extract_signals(self, title: str, body: str):
        return [dict(signal) for signal in self.CONTROL_SIGNALS]
