"""Stub for :mod:`python_setup_lint.runner._record_types`.

Shared types for the runner module.
"""


from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Record:
    """A single lint violation, order-tolerant + multiset-accurate.

    Fields mirror the standard ``path:line:col: rule: message`` format.
    ``file``, ``line``, and ``col`` are ``None`` when the violation is
    project-wide (e.g. pylint R0801 duplicate-code spans).
    """

    file: str | None
    line: int | None
    col: int | None
    rule: str
    msg: str


