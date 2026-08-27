"""
Response models.

The API contract is declared here rather than inferred from whatever
the services happen to return, so a change in the pipeline cannot
silently reshape what the frontend receives.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class Repository(BaseModel):
    owner: str
    repo: str
    full_name: str
    description: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    html_url: Optional[str] = None


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
