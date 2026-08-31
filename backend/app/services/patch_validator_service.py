"""
Language-agnostic patch validation against a full pre-fix snapshot.

Receives only a PatchProposal, a file map, and ValidationConfig.
Does not search the repository, call an LLM, or create PRs.
"""

from app.services.patch_apply import (
    apply_proposal_to_map,
    files_to_map,
)
from app.services.patch_validation_types import (
    STATUS_APPLY_FAILED,
    STATUS_PASSED,
    STATUS_PROPOSAL_INVALID,
    STATUS_VALIDATION_FAILED,
    PatchValidationResult,
    ValidationConfig,
    WorkspaceMeta,
)
from app.services.patch_workspace import cleanup, materialize, write_files
from app.services.validation_command_runner import (
    FakeValidationCommandRunner,
)
from app.services.validation_diagnostics import command_outcome


class PatchValidatorService:
    """
    Apply a proposal in an isolated workspace, then run commands.

    `command_runner` defaults to a fake that always succeeds so unit
    tests never spawn processes. Production callers inject
    ShellValidationCommandRunner (or a future language adapter).
    """

    def __init__(self, command_runner=None):
        self.command_runner = (
            command_runner or FakeValidationCommandRunner()
        )

    def validate(self, proposal, files, config=None):
        config = config or ValidationConfig()
        file_map = files_to_map(files)
        allowed = config.allowed_path_prefixes

        patched, file_results, errors = apply_proposal_to_map(
            proposal,
            file_map,
            allowed_prefixes=allowed,
        )

        if errors:
            structural = any(
                "unsafe path" in error
                or "overlapping" in error
                or "invalid hunk range" in error
                or "no files" in error
                or "no hunks" in error
                or "status is" in error
                for error in errors
            )
            status = (
                STATUS_PROPOSAL_INVALID
                if structural
                else STATUS_APPLY_FAILED
            )

            return PatchValidationResult(
                status=status,
                applied=False,
                validation_passed=False,
                files=file_results,
                commands=[],
                errors=errors,
                warnings=[],
                workspace=WorkspaceMeta(root=None, cleaned_up=True),
            )

        warnings = []
        command_results = []
        command_errors = []
        workspace_root = None
        cleaned_up = False

        try:
            workspace_root = materialize(file_map)
            baselines = self._baseline_results(
                config.commands,
                str(workspace_root),
                config,
            )
            write_files(workspace_root, patched)

            if not config.commands:
                warnings.append("no validation commands configured")
            else:
                for command in config.commands:
                    raw = self.command_runner.run(
                        command,
                        str(workspace_root),
                        config,
                    )
                    passed, note = command_outcome(
                        command,
                        raw,
                        baselines.get(command.name),
                    )
                    raw.passed = passed
                    command_results.append(raw)
                    if note and getattr(command, "compare_baseline", False):
                        labelled = f"{command.name}: {note}"
                        if passed:
                            warnings.append(labelled)
                        else:
                            command_errors.append(labelled)
        except Exception as exc:
            return PatchValidationResult(
                status=STATUS_APPLY_FAILED,
                applied=False,
                validation_passed=False,
                files=file_results,
                commands=command_results,
                errors=[str(exc)],
                warnings=warnings,
                workspace=WorkspaceMeta(
                    root=None,
                    cleaned_up=True,
                ),
            )
        finally:
            try:
                cleaned_up = cleanup(workspace_root)
            except Exception as exc:
                cleaned_up = False
                warnings.append(f"workspace cleanup failed: {exc}")

        failed = any(
            result.timed_out or not result.passed
            for result in command_results
        )

        if failed:
            status = STATUS_VALIDATION_FAILED
            validation_passed = False
        else:
            status = STATUS_PASSED
            validation_passed = True

        return PatchValidationResult(
            status=status,
            applied=True,
            validation_passed=validation_passed,
            files=file_results,
            commands=command_results,
            errors=command_errors,
            warnings=warnings,
            workspace=WorkspaceMeta(
                root=None,
                cleaned_up=cleaned_up,
            ),
        )

    def _baseline_results(self, commands, workspace_root, config):
        """
        Run prefix + compare_baseline commands on the unpatched tree.

        Later commands (flutter test) are not run twice. Apply has
        already produced `patched`; this runs before those files are
        written.
        """

        if not any(
            getattr(command, "compare_baseline", False)
            for command in commands
        ):
            return {}

        baselines = {}
        seen_compare = False
        for command in commands:
            if getattr(command, "compare_baseline", False):
                seen_compare = True
                baselines[command.name] = self.command_runner.run(
                    command,
                    workspace_root,
                    config,
                )
                continue
            if seen_compare:
                break
            self.command_runner.run(command, workspace_root, config)
        return baselines
