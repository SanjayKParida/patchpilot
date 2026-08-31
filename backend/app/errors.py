"""
Domain errors.

Services raise these; the API layer is the only place that knows how to
turn them into HTTP responses. Keeping the mapping in one place stops
transport concerns leaking into the pipeline.
"""


class PatchPilotError(Exception):
    """Base class for errors this application raises deliberately."""


class InvalidRef(PatchPilotError):
    """An explicit commit/ref could not be resolved. Never fall back to HEAD."""


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


class GithubPermissionDenied(PatchPilotError):
    """The GitHub token cannot write (401/403)."""


class GitRefConflict(PatchPilotError):
    """create_ref lost because the branch name already exists."""


class PatchNotApproved(PatchPilotError):
    """Delivery requires an explicit server-side approval."""


class PatchNotValidated(PatchPilotError):
    """Delivery requires a passed, runnable validation result."""


class PatchDeliveryInProgress(PatchPilotError):
    """A delivery attempt is already running for this analysis."""


class PatchGenerationInProgress(PatchPilotError):
    """A patch generation attempt is already running for this analysis."""


class SnapshotPreparationInProgress(PatchPilotError):
    """A repository snapshot download is already running for this commit."""


class PatchDeliveryRejected(PatchPilotError):
    """Stored analysis state cannot authorize delivery or approval."""


class PatchApprovalNotFound(PatchPilotError):
    pass


class PatchDeliveryNotFound(PatchPilotError):
    pass


class NotAuthenticated(PatchPilotError):
    """A PatchPilot session is required."""


class NotAuthorized(PatchPilotError):
    """The session cannot access this repository or analysis."""


class InvalidOAuthState(PatchPilotError):
    """GitHub returned a missing or mismatched OAuth state."""


class AuthorizationFailed(PatchPilotError):
    """GitHub refused to complete App authorization."""
