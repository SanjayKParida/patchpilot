"""
Response models.

The API contract is declared here rather than inferred from whatever
the services happen to return, so a change in the pipeline cannot
silently reshape what the frontend receives.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class Repository(BaseModel):
    owner: str
    repo: str
    full_name: str
    description: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    html_url: Optional[str] = None
    demo: bool = False
    can_read: Optional[bool] = None
    can_write: Optional[bool] = None
    access: Optional[str] = None
    github_repo_id: Optional[int] = None


class RepositorySnapshot(BaseModel):
    commit_sha: Optional[str] = None
    status: str
    file_count: int = 0
    progress_percent: int = 0
    files_downloaded: int = 0
    files_total: int = 0


class AuthUser(BaseModel):
    id: str
    github_id: int
    github_login: str
    avatar_url: str = ""
    name: str = ""


class AuthMe(BaseModel):
    authenticated: bool
    user: Optional[AuthUser] = None


class AuthLoginStart(BaseModel):
    authorization_url: str
    installation_url: str


class AuthInstallStart(BaseModel):
    installation_url: str


class Issue(BaseModel):
    number: int
    title: str
    body: str = ""
    state: str = "open"
    html_url: Optional[str] = None
    comments: int = 0
    updated_at: Optional[str] = None


class Signal(BaseModel):
    term: str
    type: str


class EvidenceItem(BaseModel):
    concept: str
    kind: str
    identifier: str
    line: int


class StructuralEdge(BaseModel):
    relationship: str
    source: str
    distance: int


class RelevantFile(BaseModel):
    rank: int
    path: str
    total_score: float
    signals_matched: int = 0
    evidence: List[EvidenceItem] = Field(default_factory=list)
    structural: List[StructuralEdge] = Field(default_factory=list)


class SymbolLocation(BaseModel):
    """Where a symbol the diagnosis named is actually declared."""

    symbol: str
    path: str
    line: int
    kind: str


class Diagnosis(BaseModel):
    root_cause: str
    # A probability in [0, 1], as produced by IssueDiagnosisService.
    confidence: float
    explanation: str
    suggested_fix: str
    relevant_files: List[str] = Field(default_factory=list)
    # The declaration containing the defect — what "View root cause"
    # navigates to. Kept separate from supporting symbols so the
    # primary action never lands on a merely-related type.
    root_cause_symbols: List[str] = Field(default_factory=list)
    root_cause_locations: List[SymbolLocation] = Field(
        default_factory=list
    )
    # Supporting declarations that explain the failure. Optional, so
    # an older or terser diagnosis stays valid.
    symbols: List[str] = Field(default_factory=list)
    # Resolved deterministically from the source. Only symbols that
    # resolved unambiguously appear here.
    locations: List[SymbolLocation] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    owner: str
    repo: str
    issue_number: int
    # Either name is accepted. `ref` is the canonical field; `commit`
    # is an alias so a SHA can be sent without knowing the GitHub
    # word for it.
    ref: Optional[str] = None
    commit: Optional[str] = None
    # When true, skip reuse of a completed or in-flight job.
    force: bool = False

    @model_validator(mode="after")
    def _ref_and_commit_agree(self):
        values = []

        for raw in (self.ref, self.commit):
            if raw is None:
                continue
            stripped = raw.strip()
            if stripped:
                values.append(stripped)

        unique = list(dict.fromkeys(values))

        if len(unique) > 1:
            raise ValueError(
                "ref and commit both set and do not match"
            )

        return self

    def effective_ref(self):
        for raw in (self.ref, self.commit):
            if raw is None:
                continue
            stripped = raw.strip()
            if stripped:
                return stripped
        return None


class Analysis(BaseModel):
    id: str
    status: str
    stage: Optional[str] = None
    error: Optional[str] = None
    repository: dict
    issue_number: int
    issue: Optional[Issue] = None
    signals: List[Signal] = Field(default_factory=list)
    relevant_files: List[RelevantFile] = Field(default_factory=list)
    diagnosis: Optional[Diagnosis] = None
    diagnosis_error: Optional[str] = None
    # Requested ref as the client sent it (branch, tag, or SHA).
    ref: Optional[str] = None
    # Full commit SHA actually analysed. Every source fetch and later
    # patch/validation for this job uses this snapshot.
    commit_sha: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class FileSource(BaseModel):
    path: str
    content: str
    lines: int


class QuestionRequest(BaseModel):
    question: str


class Answer(BaseModel):
    question: str
    answer: str


class BudgetUsage(BaseModel):
    max_files: int
    files_used: int
    max_lines_total: int
    lines_used: int
    estimated_tokens: int
    over_budget: bool


class ContextSlice(BaseModel):
    path: str
    start_line: int
    end_line: int
    tier: int
    reason: str
    symbols: List[str] = Field(default_factory=list)
    content: str
    truncated: bool
    language: str
    adapter: str


class ContextFileRollup(BaseModel):
    path: str
    total_lines: int
    included_lines: int
    complete: bool


class ContextOmittedEntry(BaseModel):
    path: str
    reason: str


class ContextPackage(BaseModel):
    """
    Bounded source context for patch generation.

    Served from GET /analyses/{id}/context, not from the polling
    Analysis payload — slice content does not belong in a response
    the client refetches while a job is running.
    """

    slices: List[ContextSlice] = Field(default_factory=list)
    files: List[ContextFileRollup] = Field(default_factory=list)
    omitted: List[ContextOmittedEntry] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    budget: BudgetUsage
    language: str
    adapter: str
    issue: Optional[dict] = None
    diagnosis: Optional[dict] = None
    root_cause: Optional[dict] = None


class PatchHunk(BaseModel):
    start_line: int
    end_line: int
    old_text: str
    new_text: str


class PatchFile(BaseModel):
    path: str
    language: str = ""
    hunks: List[PatchHunk] = Field(default_factory=list)


class PatchProposal(BaseModel):
    """
    Structured patch proposal from PatchGeneratorService.

    Served from /analyses/{id}/patch, not from the polling Analysis
    payload — the same separation ContextPackage uses.
    """

    status: str
    summary: str
    reasoning: str
    confidence: Optional[float] = None
    files: List[PatchFile] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class ValidationCommandResult(BaseModel):
    name: str
    argv: List[str] = Field(default_factory=list)
    exit_code: Optional[int] = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    passed: Optional[bool] = None


class FileApplyResult(BaseModel):
    path: str
    applied: bool
    hunks_applied: int = 0
    error: Optional[str] = None


class WorkspaceMeta(BaseModel):
    root: Optional[str] = None
    cleaned_up: bool = True


class PatchValidation(BaseModel):
    """
    Outcome of PatchValidatorService for a stored proposal.

    Served from /analyses/{id}/patch/validate, not from the polling
    Analysis payload. `runnable` is profile metadata: a `passed`
    apply with no Flutter commands is not a compile success.
    """

    status: str
    applied: bool
    validation_passed: bool
    files: List[FileApplyResult] = Field(default_factory=list)
    commands: List[ValidationCommandResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    workspace: Optional[WorkspaceMeta] = None
    runnable: bool = False
    unavailable_reason: str = ""


class PatchApproval(BaseModel):
    """
    Server-side approval of a stored, validated proposal.

    Served from /analyses/{id}/patch/approve, not from the polling
    Analysis payload.
    """

    approved: bool
    approved_at: str
    commit_sha: str
    analysis_id: str


class PatchDelivery(BaseModel):
    """
    Outcome of opening a draft PR from a stored approved proposal.

    Served from /analyses/{id}/patch/deliver, not from the polling
    Analysis payload. `status` is succeeded only when a PR exists.
    """

    status: str
    stage: str
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    base_commit_sha: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    draft: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
