from __future__ import annotations

import sys
from collections.abc import Callable

from beartype import beartype

from ._config import _default_config_paths
from .cmd_build import (
    _build_command,
    _build_statistics_flags,
    _config_flag_for,
    _find_py_files,
    _find_pyi_files,
    _resolve_pylintrc,
)
from .parsers import _STATISTICS_PARSERS
from .types import RunnerConfig, ToolSpec

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
        default_paths=["."],
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
        memory_limit_mb=0,  # 0 disables RLIMIT_AS for ty: Rust runtime reserves ~2.5GB+ virtual address space (thread stacks, mmap arenas) though peak RSS is ~124MB; RLIMIT_AS caps virtual address space, not physical RAM, so the default 2048 MB would crash the Rust binary on startup
        default_paths=["src"],  # ty scoped to src/ only: ty honors its own ignore-comment syntax (not mypy's `# type: ignore[code]`), so 67 existing `# type: ignore[mypy-code]` test suppressions are invisible to ty, producing 38 false positives on test-fixture patterns (monkeypatch, dict-invariance, isinstance-narrowing) that mypy + pyright both certify clean; tests are already type-checked by those 2 independent tools; re-enabling ty on tests would require ~38 duplicate ty-specific ignore comments for zero marginal type-safety gain. (pylint-pyi at line 105 also has default_paths=["src"]—that's a stylistic stub-linter scope, not a type-checker restriction.)  # pylint: disable=unjustified-suppression
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
        "pylint-pyi",
        ["pylint"],
        supports_fix=False,
        supports_path=True,
        supports_exclude=False,
        default_paths=["src"],
    ),
    ToolSpec(
        "pylint tests",
        ["pylint"],
        supports_fix=False,
        supports_path=True,
        supports_exclude=False,
        default_paths=["tests"],
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
    @beartype
    def name(self) -> str:
        return self.spec.name

    @beartype
    def build_command(
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

    @beartype
    def statistics_flags(self) -> list[str]:
        return _build_statistics_flags(self.spec)

    @beartype
    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:
        parser = _STATISTICS_PARSERS.get(self.spec.name)
        if parser is None:
            return []
        return parser(stdout, stderr)


# ── Per-tool strategy subclasses ─────────────────────────────────
# Six built-ins have fundamentally different command shapes that
# cannot be expressed via ToolSpec declarative fields alone.  Each
# overrides ``build_command`` with tool-specific logic, eliminating
# ``if spec.name ==`` branches from ``_build_command``.


class _StubtestLintTool(LintTool):
    @beartype
    def build_command(
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
        pkg_name = config.package_name
        if pkg_name is not None:
            cmd.append(pkg_name)
        cmd.extend(
            [
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
    @beartype
    def build_command(
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
        pkg_name = config.package_name
        if pkg_name is not None:
            cmd.append(pkg_name)
        cmd.extend(["--ignoreexternal", "--outputjson"])
        if pyright_config is not None:
            cmd.extend(["--project", str(pyright_config)])
        return cmd


class _DetectSecretsLintTool(LintTool):
    @beartype
    def build_command(
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
                (
                    f"git ls-files -z | xargs -0 {' '.join(spec.command)} --baseline {config.secrets_baseline} && "
                    f"python3 -c \"import json,sys; p=sys.argv[1]; d=json.load(open(p)); d.pop('generated_at',None); json.dump(d,open(p,'w'),indent=2,sort_keys=True)\" {config.secrets_baseline}"
                ),
            ]
        # Bootstrap: scan all files, create baseline, strip volatile metadata.
        return [
            "bash",
            "-c",
            (
                f"detect-secrets scan > {config.secrets_baseline} && "
                f"python3 -c \"import json,sys; p=sys.argv[1]; d=json.load(open(p)); d.pop('generated_at',None); json.dump(d,open(p,'w'),indent=2,sort_keys=True)\" {config.secrets_baseline}"
            ),
        ]


class _PylintLintTool(LintTool):
    @beartype
    def build_command(
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
        rcfile = _resolve_pylintrc(config_paths, config.cwd)

        # ── Shared config files (with auto-discovery) ───────────
        print(f"[pylint] Using rcfile: {rcfile}", file=sys.stderr)
        cmd.extend(_config_flag_for(spec.name, rcfile))

        # ── Suppress structlog debug/info noise from checkers ──
        cmd.extend([
            "--init-hook",
            "import structlog, logging; structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))",
        ])

        # ── Fix flags ────────────────────────────────────────
        if _fix and spec.supports_fix:
            cmd.extend(spec.fix_flags)

        # ── Path scoping — always expand to .py files ────────
        if _path is not None:
            paths = _find_py_files([_path], cwd=config.cwd)
        else:
            dirs = config.default_py_dirs or []
            paths = _find_py_files(dirs, cwd=config.cwd)

        if paths:
            cmd.extend(paths)

        # ── Exclude flags ────────────────────────────────────
        if _exclude is not None and spec.supports_exclude:
            cmd.extend([spec.exclude_flag, _exclude])

        return cmd


class _PylintPyiLintTool(LintTool):
    @beartype
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)
        # Use .pylintrc-pyi — explicit override first, then auto-discovery.
        rcfile = config.config_paths.get("pylint-pyi")
        if rcfile is None:
            rcfile = _default_config_paths(config.cwd).get("pylint-pyi")
        if rcfile is not None:
            cmd.extend(["--rcfile", str(rcfile)])

        # Find .pyi files
        if _path is not None:
            paths = _find_pyi_files([_path], cwd=config.cwd)
        else:
            dirs = config.default_py_dirs or []
            paths = _find_pyi_files(dirs, cwd=config.cwd)

        if paths:
            cmd.extend(paths)
        return cmd


class _PylintTestsLintTool(LintTool):
    @beartype
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)

        # Use .pylintrc-tests — explicit override first, then auto-discovery.
        rcfile = config.config_paths.get("pylint tests")
        if rcfile is None:
            rcfile = _default_config_paths(config.cwd).get("pylint tests")
        if rcfile is not None:
            cmd.extend(["--rcfile", str(rcfile)])

        # Find .py files in tests/ (excluding tests/data/)
        if _path is not None:
            paths = _find_py_files([_path], cwd=config.cwd)
        else:
            dirs = spec.default_paths or []
            paths = _find_py_files(dirs, cwd=config.cwd)

        if paths:
            cmd.extend(paths)
        return cmd


# Populate the strategy registry from the 13 built-ins.
_STRATEGY_CLASSES: dict[str, type[LintTool]] = {
    "mypy.stubtest": _StubtestLintTool,
    "pyright verify types": _VerifyTypesLintTool,
    "detect-secrets": _DetectSecretsLintTool,
    "pylint": _PylintLintTool,
    "pylint-pyi": _PylintPyiLintTool,
    "pylint tests": _PylintTestsLintTool,
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

    @beartype
    def build_command(
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

    @beartype
    def statistics_flags(self) -> list[str]:
        if self._statistics_flag is not None:
            return list(self._statistics_flag)
        return _build_statistics_flags(self.spec)

    @beartype
    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:
        if self._parser is not None:
            return self._parser(stdout, stderr)
        parser = _STATISTICS_PARSERS.get(self.spec.name)
        if parser is None:
            return []
        return parser(stdout, stderr)


# Live registry of declared ``ToolSpec`` instances.
# At import time it mirrors the 13 built-ins from :data:`TOOLS`; extras
# registered via :func:`register_lint_tool` append to it.  :data:`TOOLS`
# stays the frozen built-in list and is kept as a legacy-compat alias.
LINT_TOOLS: list[ToolSpec] = list(TOOLS)


def _strategy_for(name: str, spec: ToolSpec) -> LintTool:
    cached = STRATEGIES.get(name)
    if cached is not None:
        return cached
    return GenericLintTool(spec)


@beartype
def register_lint_tool(
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
