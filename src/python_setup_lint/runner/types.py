from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["LintResult", "RunnerConfig", "ToolSpec", "ViolationCount"]


class ToolSpec(NamedTuple):

    name: str
    command: list[str]
    supports_fix: bool = False
    supports_path: bool = False
    supports_exclude: bool = False
    default_paths: list[str] = []
    fix_flags: tuple[str, ...] = ("--fix",)
    exclude_flag: str = "--exclude"
    timeout: int = 120  # seconds; 0 = no limit
    memory_limit_mb: int = 2048  # RLIMIT_AS cap; 0 = no limit


@dataclass
class LintResult:

    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed: float


@dataclass
class ViolationCount:

    tool: str
    rule: str
    count: int

    def __lt__(self, other: ViolationCount) -> bool:
        return (-self.count, self.tool, self.rule) < (
            -other.count,
            other.tool,
            other.rule,
        )


@dataclass
class RunnerConfig:

    cwd: Path
    package_name: str | None = None
    default_py_dirs: list[str] | None = None
    tools_override: list[str] | None = None
    tool_timeouts: dict[str, int] | None = None  # tool name → override seconds
    tool_memory_limits: dict[str, int] | None = None  # tool name → override MB
    secrets_baseline: str = ".secrets.baseline"
    config_paths: dict[str, Path] | None = None
    ruff_project_overrides: bool = False
    pyright_project_override: Path | None = None

    def __post_init__(self) -> None:
        if self.default_py_dirs is None:
            self.default_py_dirs = ["src"]
        if self.config_paths is None:
            self.config_paths = {}
