from __future__ import annotations

from collections.abc import Callable

from beartype import beartype

from ._strategies import (  # type: ignore[attr-defined]  # private symbols removed from .pyi per M3(b); runtime re-export still works
    _STRATEGY_CLASSES,
    GenericLintTool,
    LintTool,
    _DetectSecretsLintTool,
    _PylintLintTool,
    _RuffFormatLintTool,
    _StubtestLintTool,
    _VerifyTypesLintTool,
)
from .parsers import _RECORD_PARSERS, _STATISTICS_PARSERS
from .types import ToolSpec

__all__ = [
    "EXPECTED_TOOL_NAMES",
    "FORMATTER_ONLY",
    "LINT_TOOLS",
    "RECORDLESS_TOOLS",
    "RECORD_PARSER_TOOLS",
    "STATISTICS_PARSER_TOOLS",
    "STRATEGIES",
    "TOOLS",
    "TOOLS_BY_NAME",
    "GenericLintTool",
    "LintTool",
    "_DetectSecretsLintTool",
    "_PylintLintTool",
    "_RuffFormatLintTool",
    "_StubtestLintTool",
    "_VerifyTypesLintTool",
    "_strategy_for",
    "register_lint_tool",
]


# ── Tool definitions ────────────────────────────────────────────────

TOOLS: list[ToolSpec] = [
    ToolSpec("tach check", ["tach", "check"], supports_exclude=True, exclude_flag="-e"),
    ToolSpec(
        "ruff format",
        ["ruff", "format"],
        supports_fix=False,
        supports_path=True,
        supports_exclude=True,
        default_paths=["src/", "tests/"],
    ),
    ToolSpec(
        "ruff check",
        ["ruff", "check", "--output-format", "concise"],
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
        default_paths=[
            "src"
        ],  # ty scoped to src/ only: ty honors its own ignore-comment syntax (not mypy's `# type: ignore[code]`), so 67 existing `# type: ignore[mypy-code]` test suppressions are invisible to ty, producing 38 false positives on test-fixture patterns (monkeypatch, dict-invariance, isinstance-narrowing) that mypy + pyright both certify clean; tests are already type-checked by those 2 independent tools; re-enabling ty on tests would require ~38 duplicate ty-specific ignore comments for zero marginal type-safety gain. (pylint-pyi at line 105 also has default_paths=["src"]—that's a stylistic stub-linter scope, not a type-checker restriction.)  # pylint: disable=unjustified-suppression
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

# ── Single-source registry invariants ───────────────────────────────
# Public constants consumed by the runner and its tests.  Each set is
# derived from TOOLS or the parser tables so no test hardcodes counts.
EXPECTED_TOOL_NAMES: frozenset[str] = frozenset(t.name for t in TOOLS)
FORMATTER_ONLY: frozenset[str] = frozenset({"ruff format"})
STATISTICS_PARSER_TOOLS: frozenset[str] = frozenset(_STATISTICS_PARSERS)
RECORD_PARSER_TOOLS: frozenset[str] = frozenset(_RECORD_PARSERS)
# The complement of RECORD_PARSER_TOOLS: tools whose output has no
# per-violation record structure (tach/mypy.stubtest/pyright verify
# types/detect-secrets emit counts or a pass-fail verdict, and
# ruff format emits only a file-count summary).  Documented intentional.
RECORDLESS_TOOLS: frozenset[str] = EXPECTED_TOOL_NAMES - RECORD_PARSER_TOOLS


# Populate the strategy registry from the 14 built-ins.
STRATEGIES: dict[str, LintTool] = {spec.name: (_STRATEGY_CLASSES.get(spec.name) or LintTool)(spec) for spec in TOOLS}


# Live registry of declared ``ToolSpec`` instances.
# At import time it mirrors the 14 built-ins from :data:`TOOLS`; extras
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
