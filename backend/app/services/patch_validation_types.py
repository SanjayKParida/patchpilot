"""
Structured results from PatchValidator.

Apply and command outcomes are recorded here; a future API may
expose them. Serialization matches PatchProposal: sort_keys JSON.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

STATUS_PROPOSAL_INVALID = "proposal_invalid"
STATUS_APPLY_FAILED = "apply_failed"
STATUS_VALIDATION_FAILED = "validation_failed"
STATUS_PASSED = "passed"

VALID_VALIDATION_STATUSES = frozenset({
    STATUS_PROPOSAL_INVALID,
    STATUS_APPLY_FAILED,
    STATUS_VALIDATION_FAILED,
    STATUS_PASSED,
})


@dataclass(frozen=True)
class ValidationCommand:
    """One operator-supplied argv to run in the patched workspace."""

    name: str
    argv: Tuple[str, ...]
    cwd: str = ""
    compare_baseline: bool = False
    diagnostic_format: str = ""


@dataclass
class ValidationConfig:
    """
    How the validator runs after a successful apply.

    Commands are trusted operator recipes (later: flutter analyze /
    flutter test). They are not issue-supplied shell strings.
    """

    commands: List[ValidationCommand] = field(default_factory=list)
    timeout_seconds: float = 60.0
    max_log_bytes: int = 32 * 1024
    allowed_path_prefixes: Tuple[str, ...] = ()


@dataclass
class FileApplyResult:
    path: str
    applied: bool
    hunks_applied: int = 0
    error: Optional[str] = None


@dataclass
class CommandResult:
    name: str
    argv: List[str]
    exit_code: Optional[int]
    timed_out: bool
    stdout: str
    stderr: str
    duration_ms: int
    passed: bool = True


@dataclass
class WorkspaceMeta:
    root: Optional[str]
    cleaned_up: bool


@dataclass
class PatchValidationResult:
    """
    Outcome of applying a proposal against a full pre-fix snapshot
    and running configured validation commands.

    Success means the patch applied and checks passed — not that it
    matches a historical fix commit byte-for-byte.
    """

    status: str
    applied: bool
    validation_passed: bool
    files: List[FileApplyResult] = field(default_factory=list)
    commands: List[CommandResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    workspace: Optional[WorkspaceMeta] = None

    def to_dict(self):
        return {
            "applied": self.applied,
            "commands": [asdict(item) for item in self.commands],
            "errors": list(self.errors),
            "files": [asdict(item) for item in self.files],
            "status": self.status,
            "validation_passed": self.validation_passed,
            "warnings": list(self.warnings),
            "workspace": (
                asdict(self.workspace) if self.workspace else None
            ),
        }

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
