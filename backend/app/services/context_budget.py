"""
Soft limits on a ContextPackage.

The numbers are starting points, not calibrated values. Do not tune
them against the three commit-grounded cases from the ranking work —
that measurement is a later step, and guessing here would discard it.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ContextBudget:
    max_files: int = 12
    max_lines_total: int = 1200
    max_lines_per_file: int = 400
    max_tests: int = 2
    chars_per_token: int = 4
    max_tokens: Optional[int] = None

    # Slicing knobs live here so tests can isolate one behaviour
    # without forking the builder.
    pad_lines: int = 3
    fallback_before: int = 12
    fallback_after: int = 40
    merge_gap: int = 6
    whole_file_fraction: float = 0.70
