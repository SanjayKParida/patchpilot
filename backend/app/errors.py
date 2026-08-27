"""
Domain errors.

Services raise these; the API layer is the only place that knows how to
turn them into HTTP responses. Keeping the mapping in one place stops
transport concerns leaking into the pipeline.
"""


class PatchPilotError(Exception):
    """Base class for errors this application raises deliberately."""


class RepositoryNotFound(PatchPilotError):
    pass


class IssueNotFound(PatchPilotError):
    pass


class InvalidRepositoryUrl(PatchPilotError):
    pass


class UpstreamUnavailable(PatchPilotError):
    """GitHub or the language model failed in a way we cannot recover from."""


class AnalysisNotFound(PatchPilotError):
    pass
