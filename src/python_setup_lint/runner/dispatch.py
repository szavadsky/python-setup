"""Strategy registry and per-tool command-construction strategies.

A :class:`LintTool` strategy wraps per-tool command construction, statistics
flags, and statistics parsing.  Built-in tools reuse the module-level
helpers in :mod:`python_setup_lint.runner.cmd_build` (command shape) and
:mod:`python_setup_lint.runner.parsers` (statistics) via the default
:class:`LintTool` methods; four built-ins override ``build_command`` for
tool-specific shapes that cannot be expressed via :class:`~python_setup_lint.runner.types.ToolSpec`
declarative fields alone.  Extras registered via :func:`register_lint_tool`
land on :class:`GenericLintTool`, which composes the same generic flag logic
via the spec's ``supports_*`` booleans.

The dispatch is DEFAULT-aware: ``STRATEGIES.get(name)`` returns ``None`` for
unknown names, and :func:`_strategy_for` synthesises a
:class:`GenericLintTool` on lookup so extras never ``KeyError``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .cmd_build import (
    _build_command,
    _build_statistics_flags,
    _config_flag_for,
    _expand_globs,
    _find_py_files,
    _resolve_pylintrc,
)
from .parsers import _STATISTICS_PARSERS
from .types import RunnerConfig, ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = [
    "LINT_TOOLS",
    "STRATEGIES",
    "TOOLS",
    "TOOLS_BY_NAME",
    "GenericLintTool",
    "LintTool",
    "_DetectSecretsLintTool",
    "_PylintLintTool",
    "_StubtestLintTool",
    "_VerifyTypesLintTool",
    "_strategy_for",
    "register_lint_tool",
]


# ── Tool definitions ────────────────────────────────────────────────

TOOLS: list[ToolSpec] = [
    ToolSpec("tach check", ["tach", "check"], supports_exclude=True, exclude_flag="-e"),
    ToolSpec(
        "ruff check",
        ["ruff", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        default_paths=["src/", "tests/"],
        fix_flags=("--fix", "--exit-non-zero-on-fix"),
    ),
    ToolSpec(
        "rumdl check",
        ["rumdl", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        fix_flags=("--fix",),
    ),
    ToolSpec(
        "mypy",
        ["mypy"],
        supports_path=True,
        default_paths=["."],
    ),
    ToolSpec(
        "yamllint",
        ["yamllint"],
        supports_path=True,
        default_paths=["."],
    ),
    ToolSpec(
        "ty check",
        ["ty", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        fix_flags=("--fix",),
    ),
    ToolSpec(
        "mypy.stubtest",
        ["python", "-m", "mypy.stubtest"],
    ),
    ToolSpec(
        "pyright check",
        ["pyright", "--outputjson"],
        supports_path=True,
        default_paths=["."],
    ),
    ToolSpec(
        "pyright verify types",
        ["pyright", "--verifytypes"],
    ),
    ToolSpec(
        "pylint",
        ["pylint"],
        supports_path=True,
    ),
    ToolSpec(
        "detect-secrets",
        ["detect-secrets-hook"],
    ),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


class LintTool:
    spec: ToolSpec

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:  # pylint: disable=missing-beartype
        return self.spec.name

    def build_command(  # pylint: disable=missing-beartype
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        return _build_command(
            self.spec, config=config, fix=_fix, path=_path, exclude=_exclude
        )

    def statistics_flags(self) -> list[str]:  # pylint: disable=missing-beartype
        return _build_statistics_flags(self.spec)

    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:  # pylint: disable=missing-beartype
        parser = _STATISTICS_PARSERS.get(self.spec.name)
        if parser is None:
            return []
        return parser(stdout, stderr)


# ── Per-tool strategy subclasses ─────────────────────────────────
# Four built-in tools have fundamentally different command shapes that
# cannot be expressed via ToolSpec declarative fields alone.  Each
# overrides ``build_command`` with tool-specific logic, eliminating
# ``if spec.name ==`` branches from ``_build_command``.


class _StubtestLintTool(LintTool):
    def build_command(  # pylint: disable=missing-beartype
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cwd = config.cwd
        cmd = list(spec.command)
        config_paths = config.config_paths or {}
        mypy_config = config_paths.get("mypy")
        cmd.extend(
            [
                config.package_name,
                "--concise",
                "--ignore-missing-stub",
                "--mypy-config-file",
                str(mypy_config) if mypy_config is not None else "pyproject.toml",
            ]
        )
        allowlist_path = cwd / "stubtest_allowlist.txt"
        if allowlist_path.exists():
            cmd.extend(["--allowlist", "stubtest_allowlist.txt"])
        return cmd


class _VerifyTypesLintTool(LintTool):
    def build_command(  # pylint: disable=missing-beartype
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)
        config_paths = config.config_paths or {}
        pyright_config = config_paths.get("pyright check")
        cmd.extend([config.package_name, "--ignoreexternal", "--outputjson"])
        if pyright_config is not None:
            cmd.extend(["--project", str(pyright_config)])
        return cmd


class _DetectSecretsLintTool(LintTool):
    def build_command(  # pylint: disable=missing-beartype
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        _ = _path, _fix, _exclude
        baseline_path = config.cwd / config.secrets_baseline
        if baseline_path.is_file():
            return [
                "bash",
                "-c",
                f"git ls-files -z | xargs -0 {' '.join(spec.command)} --baseline {config.secrets_baseline}",
            ]
        # Bootstrap: scan all files and create baseline on first invocation.
        return [
            "bash",
            "-c",
            f"detect-secrets scan > {config.secrets_baseline}",
        ]


class _PylintLintTool(LintTool):
    @staticmethod
    def _resolve_pylintrc(config_paths: dict[str, Path], cwd: Path) -> Path | None:
        return _resolve_pylintrc(config_paths, cwd)

    def build_command(  # pylint: disable=missing-beartype
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)
        config_paths = config.config_paths or {}

        # ── Shared config files (with auto-discovery) ───────────
        rcfile = self._resolve_pylintrc(config_paths, config.cwd)
        print(f"[pylint] Using rcfile: {rcfile}", file=sys.stderr)
        cmd.extend(_config_flag_for(spec.name, rcfile))

        # ── Fix flags ────────────────────────────────────────
        if _fix and spec.supports_fix:
            cmd.extend(spec.fix_flags)

        # ── Path scoping — always expand to .py files ────────
        if _path is not None:
            paths = _find_py_files([_path], cwd=config.cwd)
        else:
            paths = _find_py_files(config.default_py_dirs, cwd=config.cwd)

        # Expand globs (e.g. config/*.yaml)
        paths = _expand_globs(paths, cwd=config.cwd)

        if paths:
            cmd.extend(paths)

        # ── Exclude flags ────────────────────────────────────
        if _exclude is not None and spec.supports_exclude:
            cmd.extend([spec.exclude_flag, _exclude])

        return cmd


# Populate the strategy registry from the 11 built-ins.
_STRATEGY_CLASSES: dict[str, type[LintTool]] = {
    "mypy.stubtest": _StubtestLintTool,
    "pyright verify types": _VerifyTypesLintTool,
    "detect-secrets": _DetectSecretsLintTool,
    "pylint": _PylintLintTool,
}
STRATEGIES: dict[str, LintTool] = {
    spec.name: (_STRATEGY_CLASSES.get(spec.name) or LintTool)(spec) for spec in TOOLS
}


class GenericLintTool(LintTool):
    def __init__(
        self,
        spec: ToolSpec,
        *,
        statistics_flag: list[str] | None = None,
        parser: Callable[..., list[tuple[str, int]]] | None = None,
        config_flag: list[str] | None = None,
    ) -> None:
        super().__init__(spec)
        self._statistics_flag = statistics_flag
        self._parser = parser
        self._config_flag = config_flag

    def build_command(  # pylint: disable=missing-beartype
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        return _build_command(
            self.spec,
            config=config,
            fix=_fix,
            path=_path,
            exclude=_exclude,
            config_flag_override=self._config_flag,
        )

    def statistics_flags(self) -> list[str]:  # pylint: disable=missing-beartype
        if self._statistics_flag is not None:
            return list(self._statistics_flag)
        return _build_statistics_flags(self.spec)

    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:  # pylint: disable=missing-beartype
        if self._parser is not None:
            return self._parser(stdout, stderr)
        parser = _STATISTICS_PARSERS.get(self.spec.name)
        if parser is None:
            return []
        return parser(stdout, stderr)


# Live registry of declared ``ToolSpec`` instances.
# At import time it mirrors the 11 built-ins from :data:`TOOLS`; extras
# registered via :func:`register_lint_tool` append to it.  :data:`TOOLS`
# stays the frozen built-in list and is kept as a legacy-compat alias.
LINT_TOOLS: list[ToolSpec] = list(TOOLS)


def _strategy_for(name: str, spec: ToolSpec) -> LintTool:
    cached = STRATEGIES.get(name)
    if cached is not None:
        return cached
    return GenericLintTool(spec)


def register_lint_tool(  # pylint: disable=missing-beartype
    tool: ToolSpec,
    *,
    statistics_flag: list[str] | None = None,
    parser: Callable[..., list[tuple[str, int]]] | None = None,
    config_flag: list[str] | None = None,
) -> None:
    # Idempotent: replace any existing LINT_TOOLS entry with the same name;
    # otherwise append.
    for i, existing in enumerate(LINT_TOOLS):
        if existing.name == tool.name:
            LINT_TOOLS[i] = tool
            break
    else:
        LINT_TOOLS.append(tool)

    # Register strategy only when no per-tool class already exists (built-ins
    # keep their strategies; non-builtin names get a GenericLintTool).
    if tool.name not in STRATEGIES:
        STRATEGIES[tool.name] = GenericLintTool(
            tool,
            statistics_flag=statistics_flag,
            parser=parser,
            config_flag=config_flag,
        )
