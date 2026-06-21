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

from collections.abc import Callable

from .cmd_build import (
    _build_command,
    _build_statistics_flags,
    _config_flag_for,
    _expand_globs,
    _find_py_files,
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
        default_paths=["config/*.yaml"],
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
    """Strategy for a single lint tool.

    Implementations encapsulate per-tool command construction, statistics
    flags, and statistics parsing.  Config-agnostic: the
    ``package_name is None`` skip for ``mypy.stubtest`` /
    ``pyright verify types`` stays in :func:`python_setup_lint.runner.cli.run_lint`,
    not here.

    Subclasses override :meth:`build_command` / :meth:`statistics_flags`
    / :meth:`parse_statistics` to specialise per-tool behaviour.  The
    default implementations consult the module-level dispatch tables
    (``_build_command`` / ``_build_statistics_flags`` /
    ``_STATISTICS_PARSERS``) so built-in behaviour stays verbatim.
    """

    spec: ToolSpec

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        """Tool label — mirrors the spec's name."""
        return self.spec.name

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        """Build the full command list for this tool given runtime flags.

        Default: delegates to the module-level :func:`_build_command`,
        which is the authoritative literal specification of each built-in
        tool's command shape.
        """
        return _build_command(self.spec, config=config, fix=fix, path=path, exclude=exclude)

    def statistics_flags(self) -> list[str]:
        """Extra CLI flags for statistics output mode.

        Default: delegates to :func:`_build_statistics_flags`.
        """
        return _build_statistics_flags(self.spec)

    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:
        """Parse this tool's stdout/stderr into ``(rule, count)`` pairs.

        Default: looks up the parser in :data:`_STATISTICS_PARSERS`.
        Returns an empty list when no parser is registered.
        """
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
    """Strategy for ``mypy.stubtest`` — builds command from ``package_name`` + optional allowlist."""

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
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
    """Strategy for ``pyright verify types`` — builds command from ``package_name`` + optional project."""

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
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
    """Strategy for ``detect-secrets`` — wraps in ``bash -c`` pipeline over git-ls-files."""

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        _ = path, fix, exclude
        return [
            "bash",
            "-c",
            f"git ls-files -z | xargs -0 {' '.join(spec.command)} --baseline {config.secrets_baseline}",
        ]


class _PylintLintTool(LintTool):
    """Strategy for ``pylint`` — always resolves ``_find_py_files()`` for path expansion.

    Pylint expects file arguments, not directory paths.  Unlike other tools
    that accept a directory and recurse internally, pylint needs an explicit
    list of ``.py`` files.  This strategy always calls ``_find_py_files``
    regardless of whether ``spec.default_paths`` is empty, ensuring pylint
    never runs with an empty file list.

    Auto-discovers ``.pylintrc`` when ``config_paths`` has no ``pylint``
    entry: checks ``config/.pylintrc`` (shipped config dir) then
    ``.pylintrc`` (project root).
    """

    @staticmethod
    def _resolve_pylintrc(config_paths: dict[str, Path], cwd: Path) -> Path | None:
        """Return the pylint rcfile path, or ``None`` if none found."""
        explicit = config_paths.get("pylint")
        if explicit is not None:
            return explicit
        # Auto-discover: shipped config dir, then project root.
        for candidate in (cwd / "config" / ".pylintrc", cwd / ".pylintrc"):
            if candidate.is_file():
                return candidate
        return None

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)
        config_paths = config.config_paths or {}

        # ── Shared config files (with auto-discovery) ───────────
        rcfile = self._resolve_pylintrc(config_paths, config.cwd)
        cmd.extend(_config_flag_for(spec.name, rcfile))

        # ── Fix flags ────────────────────────────────────────
        if fix and spec.supports_fix:
            cmd.extend(spec.fix_flags)

        # ── Path scoping — always expand to .py files ────────
        if path is not None:
            paths = _find_py_files([path], cwd=config.cwd)
        else:
            paths = _find_py_files(config.default_py_dirs, cwd=config.cwd)

        # Expand globs (e.g. config/*.yaml)
        paths = _expand_globs(paths, cwd=config.cwd)

        if paths:
            cmd.extend(paths)

        # ── Exclude flags ────────────────────────────────────
        if exclude is not None and spec.supports_exclude:
            cmd.extend([spec.exclude_flag, exclude])

        return cmd


# Populate the strategy registry from the 11 built-ins.
_STRATEGY_CLASSES: dict[str, type[LintTool]] = {
    "mypy.stubtest": _StubtestLintTool,
    "pyright verify types": _VerifyTypesLintTool,
    "detect-secrets": _DetectSecretsLintTool,
    "pylint": _PylintLintTool,
}
STRATEGIES: dict[str, LintTool] = {spec.name: (_STRATEGY_CLASSES.get(spec.name) or LintTool)(spec) for spec in TOOLS}


class GenericLintTool(LintTool):
    """Minimal strategy for extras registered via :func:`register_lint_tool`.

    Carries three optional declarative fields supplied at registration:

    * ``statistics_flag`` — explicit CLI flag(s) for statistics output.
    * ``parser`` — callable returning ``list[tuple[str, int]]`` for stats.
    * ``config_flag`` — explicit CLI flag(s) for external config file.

    Unset fields fall back to the generic ``_build_command`` /
    ``_build_statistics_flags`` / ``_STATISTICS_PARSERS`` lookups, mirroring
    the common-case branches of :func:`_build_command`.  The 11 built-ins
    keep their own strategies; only extras land on :class:`GenericLintTool`.
    """

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

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        """Build the command, forwarding the declarative ``config_flag``.

        The 11 built-ins inherit :meth:`LintTool.build_command` which uses
        :func:`_config_flag_for`'s hardcoded name→flags dict.  Extras declare
        their own ``config_flag`` (a list like ``["--config"]``) at registration;
        this override forwards it to :func:`_build_command` via the
        ``config_flag_override`` seam so the declarative flag actually reaches
        the constructed command (the dict lookup would otherwise return ``[]``
        for an unknown name, silently dropping the flag).
        """
        return _build_command(
            self.spec,
            config=config,
            fix=fix,
            path=path,
            exclude=exclude,
            config_flag_override=self._config_flag,
        )

    def statistics_flags(self) -> list[str]:
        """Return the explicit statistics flag(s) when set; else module-level lookup."""
        if self._statistics_flag is not None:
            return list(self._statistics_flag)
        return _build_statistics_flags(self.spec)

    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:
        """Use the explicit parser when set; else module-level lookup."""
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
    """Resolve a strategy for *name*, default-aware.

    Lookup uses :data:`STRATEGIES` first.  Unknown names synthesise a
    :class:`GenericLintTool` for *spec* — this is the default-aware
    dispatch seam that lets extras reach the pipeline without
    ``KeyError``.  A cached strategy under :data:`STRATEGIES` (the built-ins
    or any previously-registered extra) is returned as-is.
    """
    cached = STRATEGIES.get(name)
    if cached is not None:
        return cached
    return GenericLintTool(spec)


def register_lint_tool(
    tool: ToolSpec,
    *,
    statistics_flag: list[str] | None = None,
    parser: Callable[..., list[tuple[str, int]]] | None = None,
    config_flag: list[str] | None = None,
) -> None:
    """Append *tool* to the live registry and register its strategy.

    For names not already in :data:`STRATEGIES`, a :class:`GenericLintTool`
    is synthesised from ``tool`` + the three optional declarative fields
    and registered under ``STRATEGIES[tool.name]``.  For built-in names
    (already present in :data:`STRATEGIES`), the existing strategy is kept
    and only :data:`LINT_TOOLS`'s entry for that name is updated.

    Idempotent per ``tool.name`` — a re-call with the same name is an
    update-in-place (no duplicate append).  This protects against repeated
    ``run_lint`` calls accumulating duplicate entries.
    """
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
