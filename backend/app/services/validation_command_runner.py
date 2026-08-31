"""
Pluggable validation command execution.

The validator core does not know about Flutter, pytest, or any
language toolchain. Adapters supply argv lists; this module runs
them with a timeout and bounded logs.

A future FlutterValidationCommandRunner would only choose argv
recipes (flutter analyze / flutter test). It is not implemented here.
"""

import os
import subprocess
import time
from typing import List, Protocol, runtime_checkable

from app.services.patch_validation_types import (
    CommandResult,
    ValidationCommand,
    ValidationConfig,
)


def command_cwd(base, command):
    """Resolve a profile-relative cwd without leaving the workspace."""

    extra = getattr(command, "cwd", "") or ""
    if not extra:
        return base

    joined = os.path.normpath(os.path.join(base, extra))
    root = os.path.normpath(base)
    if joined != root and not joined.startswith(root + os.sep):
        return base
    return joined


def truncate_log(text, max_bytes):
    """Keep the last max_bytes of text, UTF-8 safe."""

    if text is None:
        return ""

    encoded = text.encode("utf-8", errors="replace")

    if len(encoded) <= max_bytes:
        return encoded.decode("utf-8", errors="replace")

    sliced = encoded[-max_bytes:]
    return ("…\n" + sliced.decode("utf-8", errors="replace"))


@runtime_checkable
class ValidationCommandRunner(Protocol):
    def run(
        self,
        command: ValidationCommand,
        cwd: str,
        config: ValidationConfig,
    ) -> CommandResult:
        ...


class FakeValidationCommandRunner:
    """
    Deterministic runner for tests.

    `results` is a list of CommandResult or a mapping name -> result.
    If empty, every command succeeds with exit_code 0.
    """

    def __init__(self, results=None, default_exit=0, timed_out=False):
        self.results = results or []
        self.default_exit = default_exit
        self.timed_out = timed_out
        self.calls = []

    def run(self, command, cwd, config):
        self.calls.append({
            "name": command.name,
            "argv": list(command.argv),
            "cwd": command_cwd(cwd, command),
        })

        if isinstance(self.results, dict):
            preset = self.results.get(command.name)
        elif self.results:
            preset = self.results.pop(0) if isinstance(
                self.results, list
            ) else None
        else:
            preset = None

        if isinstance(preset, CommandResult):
            return preset

        exit_code = (
            preset if isinstance(preset, int) else self.default_exit
        )

        return CommandResult(
            name=command.name,
            argv=list(command.argv),
            exit_code=None if self.timed_out else exit_code,
            timed_out=self.timed_out,
            stdout="",
            stderr="timed out" if self.timed_out else "",
            duration_ms=0,
            passed=not self.timed_out and exit_code == 0,
        )


class ShellValidationCommandRunner:
    """
    Run argv in cwd with timeout. Never uses shell=True.

    Commands are operator-trusted. Killing uses the process group
    when the platform supports it.
    """

    def run(self, command, cwd, config):
        timeout = config.timeout_seconds
        max_bytes = config.max_log_bytes
        argv: List[str] = list(command.argv)
        cwd = command_cwd(cwd, command)
        started = time.monotonic()
        timed_out = False
        exit_code = None
        stdout = ""
        stderr = ""

        kwargs = {
            "args": argv,
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "timeout": timeout,
        }

        if os.name != "nt":
            kwargs["start_new_session"] = True

        try:
            completed = subprocess.run(**kwargs)
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
        except OSError as exc:
            exit_code = -1
            stderr = str(exc)

        duration_ms = int((time.monotonic() - started) * 1000)

        return CommandResult(
            name=command.name,
            argv=argv,
            exit_code=exit_code,
            timed_out=timed_out,
            stdout=truncate_log(stdout, max_bytes),
            stderr=truncate_log(stderr, max_bytes),
            duration_ms=duration_ms,
            passed=not timed_out and (exit_code or 0) == 0,
        )
