"""
Interpret validation command output without assuming exit code 0.

PatchValidator stays language-agnostic: it compares diagnostic bags
when a command opts into baseline comparison. Parsers are format
keys supplied by the profile (today: flutter_analyze).

`info` diagnostics are not ignored. A patch fails when it introduces
diagnostics that were not already present on the unpatched tree,
including extra infos. Pre-existing infos that remain are not a
patch regression. Unparseable non-zero exits still fail.
"""

import re
from collections import Counter

FLUTTER_DIAGNOSTIC = re.compile(
    r"^\s*(error|warning|info|hint)\s+•\s+(.*?)\s+•\s+"
    r"(\S+):(\d+):(\d+)\s+•\s+(\S+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_diagnostics(text, format_name):
    if format_name == "flutter_analyze":
        return parse_flutter_analyze(text)
    return []


def parse_flutter_analyze(text):
    """
    Identity is (path, severity, code), not line number.

    A one-line patch that shifts later infos must not look like a
    new diagnostic. A second instance of the same code in the same
    file is a count increase and fails.
    """

    found = []
    for match in FLUTTER_DIAGNOSTIC.finditer(text or ""):
        severity, _message, path, _line, _column, code = match.groups()
        found.append((path, severity.lower(), code))
    return found


def extra_diagnostics(baseline_text, patched_text, format_name):
    baseline = Counter(parse_diagnostics(baseline_text, format_name))
    patched = Counter(parse_diagnostics(patched_text, format_name))
    extra = []
    for key, count in patched.items():
        delta = count - baseline[key]
        if delta > 0:
            extra.append((key, delta))
    return extra


def _combined_output(result):
    if result is None:
        return ""
    return (result.stdout or "") + "\n" + (result.stderr or "")


def command_outcome(command, patched, baseline=None):
    """
    Return (passed, note).

    Exit-code commands keep historical behaviour. Baseline-compare
    commands pass when the patched diagnostic multiset does not grow,
    even if flutter analyze exits 1 for pre-existing infos.
    """

    if patched.timed_out:
        return False, "timed out"

    compare = getattr(command, "compare_baseline", False)
    format_name = getattr(command, "diagnostic_format", "") or ""

    if not compare or not format_name:
        if (patched.exit_code or 0) != 0:
            return False, ""
        return True, ""

    if baseline is not None and baseline.timed_out:
        return False, "baseline timed out"

    if (patched.exit_code or 0) == 0:
        return True, ""

    patched_text = _combined_output(patched)
    patched_diags = parse_diagnostics(patched_text, format_name)
    if not patched_diags:
        return False, "unparseable analyzer failure"

    extra = extra_diagnostics(
        _combined_output(baseline),
        patched_text,
        format_name,
    )
    if extra:
        count = sum(delta for _key, delta in extra)
        return False, f"introduced {count} new diagnostic(s)"

    return True, (
        f"{len(patched_diags)} pre-existing diagnostic(s); "
        "none introduced by the patch"
    )
