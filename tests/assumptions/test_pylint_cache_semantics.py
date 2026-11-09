"""Pin read-only semantic checks and pylint's single-writer invocation shape.

Observed at HEAD with pylint 4.0.6 -- the current floor in ``pyproject.toml``
(``pylint>=4.0.6``), so these tests double as the upgrade watchdog: a newer
pylint that shifts the ``jobs`` default or the ``check_parallel`` dispatch
fails them.

The semantic pipeline is a thin decision-backend adapter: verdicts are
memoized in-process only (one backend call per unique input/model pair) and
normal lint runs write nothing to disk. The git-tracked decision cache is a
separate epic; these tests pin the read-only behavior and the sequential
single-writer invocation shape that the tracked cache will rely on.

WRITER-FIRST VERDICT (feeds ``cache-design-spike``)
===================================================
* **Writer identity** -- no checker call path writes a result cache. The
  in-process memo lives only for the duration of the process.
* **Timing** -- one backend ``decide`` call per unique
  ``(text, rule, context, comment, model_id)`` pair; repeats hit the memo and
  call neither the backend nor the filesystem.
* **``--path`` scoping** -- the runner's ``--path`` narrows only the file
  arguments passed to each pylint invocation; the semantic API takes no path.
* **Concurrency** -- the runner executes tools sequentially and none of the
  three pylint specs passes ``-j``/``--jobs``; pylint's default ``jobs`` is 1,
  and the shipped ``config/.pylintrc*`` files do not raise it (watchdog test).
  The single-writer claim holds *only while the effective ``jobs`` is 1*, so
  no lockfile, runner-side merge, or sidecar files are required today. The
  runner resolves the rcfile from ``--config pylint=PATH``, then
  ``cwd/config/.pylintrc``, then ``cwd/.pylintrc``: a consumer rcfile or
  override that sets ``jobs > 1`` (or ``jobs = 0`` auto-detect) silently
  enables pylint's process pool and voids the claim. If that happens, pylint
  dispatches separate processes and the verdict flips to per-writer sidecars
  plus a runner merge (or a crash-safe lock plus atomic replace).
* **Crash safety** -- there is no partial-write surface: the semantic path does
  not persist anything during lint.

These tests *are* the verdict: when one fails, re-derive the writer-first
semantics before changing the assertion rather than loosening it.
"""

from __future__ import annotations

import ast
import configparser
import inspect
from pathlib import Path

import pylint.lint.parallel as pylint_parallel
import pytest
from pylint.lint import PyLinter

import python_setup_lint.checkers._semantic as semantic_module
from python_setup_lint.checkers._semantic import (  # type: ignore[attr-defined]  # private test helper omitted from .pyi
    _reset_cache,
    semantic_check_if_meaningful,
)
from python_setup_lint.runner._config import _default_config_paths
from python_setup_lint.runner.cmd_build import _resolve_pylintrc
from python_setup_lint.runner.dispatch import TOOLS, TOOLS_BY_NAME, _strategy_for
from python_setup_lint.runner.types import RunnerConfig

pytestmark = pytest.mark.no_external_api

_PYLINT_TOOL_NAMES = ("pylint", "pylint-pyi", "pylint tests")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHIPPED_PYLINT_RCFILES = tuple(sorted((_REPO_ROOT / "config").glob(".pylintrc*")))


def _pylintrc_jobs_overrides(rcfile: Path) -> list[tuple[str, int]]:
    """Return effective ``jobs`` options from *rcfile* as ``(section, value)`` pairs.

    Pylint 4.0.6 flattens options from every rcfile section into CLI flags, so a
    ``jobs`` key anywhere in the file is effective.
    """
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#", ";"))
    parser.read_string(rcfile.read_text())
    return [(section, int(parser[section]["jobs"])) for section in parser.sections() if parser.has_option(section, "jobs")]


class _RecordingBackend:
    """Stand-in for the optional decision backend so calls are exercised offline."""

    def __init__(self, score: float = 0.9, model_id: str = "recording rev test prompt-v1") -> None:
        self.score = score
        self.model_id = model_id
        self.calls: list[tuple[str, str | None, str | None]] = []

    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        """Return a fixed score and count invocations."""
        self.calls.append((justification, rule, context))
        return self.score


@pytest.fixture
def semantic_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the retired home cache at a per-test directory to prove no writes."""
    cache_dir = tmp_path / "semantic"
    monkeypatch.setattr("python_setup_lint.checkers._semantic._CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(
        "python_setup_lint.checkers._semantic._RESULT_CACHE_FILE",
        cache_dir / "results.json",
        raising=False,
    )
    monkeypatch.setattr("python_setup_lint.checkers._semantic._RESULT_CACHE", None, raising=False)
    _reset_cache()
    return cache_dir / "results.json"


class TestSemanticInProcessMemo:
    """Backend calls are memoized in-process; nothing is persisted during lint."""

    def test_given_new_verdicts_then_backend_calls_once_each_and_writes_nothing(self, semantic_disk: Path) -> None:
        """One backend call per unique pair; the retired cache path stays absent."""
        backend = _RecordingBackend(score=0.9)

        first = semantic_check_if_meaningful(
            "guarded by a lock",
            rule="W9704",
            code_context="lock = Lock()",
            comment="guarded by a lock",
            backend=backend,
        )
        second = semantic_check_if_meaningful(
            "retry is idempotent",
            rule="W9704",
            code_context="retry()",
            comment="retry is idempotent",
            backend=backend,
        )

        assert first is True
        assert second is True
        assert len(backend.calls) == 2
        assert not semantic_disk.exists()
        assert not semantic_disk.parent.exists()

    def test_given_repeated_pair_then_serves_memory_without_backend_or_write(self, semantic_disk: Path) -> None:
        """An in-memory hit calls neither the backend nor the filesystem."""
        backend = _RecordingBackend(score=0.9)
        kwargs = {
            "rule": "W9704",
            "code_context": "lock = Lock()",
            "comment": "guarded by a lock",
        }

        assert semantic_check_if_meaningful("guarded by a lock", backend=backend, **kwargs) is True
        assert semantic_check_if_meaningful("guarded by a lock", backend=backend, **kwargs) is True

        assert len(backend.calls) == 1
        assert not semantic_disk.exists()

    def test_given_backend_unavailable_then_returns_none_and_writes_nothing(
        self, semantic_disk: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The heuristic fallback path (None) creates neither cache file nor directory."""
        monkeypatch.setattr("python_setup_lint.checkers._decision_backend.get_backend", lambda: None)

        assert semantic_check_if_meaningful("checked elsewhere", comment="checked elsewhere") is None
        assert not semantic_disk.exists()
        assert not semantic_disk.parent.exists()

    def test_given_empty_primary_then_returns_false_without_backend_or_write(self, semantic_disk: Path) -> None:
        """The empty-primary short-circuit returns False before any backend call."""
        backend = _RecordingBackend(score=0.9)

        assert semantic_check_if_meaningful("", backend=backend) is False
        assert backend.calls == []
        assert not semantic_disk.parent.exists()


class TestSemanticPathScoping:
    """The semantic API is path-free and does not persist a result store."""

    def test_semantic_check_if_meaningful_given_identical_inputs_then_signature_is_path_free(self, semantic_disk: Path) -> None:
        """The API takes no path and writes no cache."""
        backend = _RecordingBackend(score=0.9)

        assert semantic_check_if_meaningful("path free key", comment="path free key", backend=backend) is True
        signature = inspect.signature(semantic_check_if_meaningful)
        assert set(signature.parameters).isdisjoint({"path", "file", "filename"})
        assert not semantic_disk.exists()

    def test_runner_pylint_commands_given_path_scope_then_scope_file_targets_only(self, tmp_path: Path) -> None:
        """OBSERVED: --path narrows lint targets; default runs keep each tool's own scope."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("APP = 1\n")
        (tmp_path / "src" / "app.pyi").write_text("APP: int\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text("def test_app() -> None: ...\n")
        config = RunnerConfig(cwd=tmp_path)

        scoped_targets = {
            "pylint": "src/app.py",
            "pylint-pyi": "src/app.pyi",
            "pylint tests": "src/app.py",
        }
        for tool_name, expected_target in scoped_targets.items():
            command = _strategy_for(tool_name, TOOLS_BY_NAME[tool_name]).build_command(config=config, _path="src")
            assert expected_target in command
            assert "tests/test_app.py" not in command

        default_targets = {
            "pylint": "src/app.py",
            "pylint-pyi": "src/app.pyi",
            "pylint tests": "tests/test_app.py",
        }
        for tool_name, expected_target in default_targets.items():
            command = _strategy_for(tool_name, TOOLS_BY_NAME[tool_name]).build_command(config=config)
            assert expected_target in command

    def test_checker_sources_given_source_tree_then_no_result_cache_writer(
        self,
    ) -> None:
        """OBSERVED: no checker module persists semantic results during lint."""
        checkers_dir = Path(semantic_module.__file__).parent
        offenders = [
            path.name
            for path in checkers_dir.rglob("*.py")
            if "_save_result_cache" in path.read_text() or "results.json" in path.read_text()
        ]

        assert offenders == []


class TestPylintRcfileJobsWatchdog:
    """Shipped rcfiles must leave pylint's ``jobs`` at 1 so the cache writer stays single."""

    def test_shipped_pylint_rcfiles_given_effective_options_then_never_enable_worker_pool(
        self,
    ) -> None:
        """OBSERVED: every shipped rcfile leaves ``jobs`` at its default of 1."""
        assert _SHIPPED_PYLINT_RCFILES
        for rcfile in _SHIPPED_PYLINT_RCFILES:
            assert all(value == 1 for _, value in _pylintrc_jobs_overrides(rcfile)), rcfile

    def test_pylintrc_jobs_scan_given_consumer_jobs_override_then_detects_it(self, tmp_path: Path) -> None:
        """NEGATIVE CONTROL: the watchdog parser flags an rcfile that raises ``jobs``."""
        rcfile = tmp_path / ".pylintrc"
        rcfile.write_text("[MAIN]\njobs=2\n")

        assert _pylintrc_jobs_overrides(rcfile) == [("MAIN", 2)]

    def test_runner_pylint_config_resolution_given_repo_root_then_uses_shipped_jobs_free_rcfiles(
        self,
    ) -> None:
        """OBSERVED: all three pylint invocations resolve to shipped, jobs-free rcfiles."""
        expected_names = {
            "pylint": ".pylintrc",
            "pylint-pyi": ".pylintrc-pyi",
            "pylint tests": ".pylintrc-tests",
        }
        resolved = {
            "pylint": _resolve_pylintrc({}, _REPO_ROOT),
            "pylint-pyi": _default_config_paths(_REPO_ROOT).get("pylint-pyi"),
            "pylint tests": _default_config_paths(_REPO_ROOT).get("pylint tests"),
        }
        for tool_name, rcfile in resolved.items():
            assert rcfile is not None, tool_name
            assert rcfile.name == expected_names[tool_name], tool_name
            assert all(value == 1 for _, value in _pylintrc_jobs_overrides(rcfile)), tool_name


class TestPylintInvocationConcurrency:
    """Single-writer assumptions on the pylint invocations that produce cache entries."""

    @pytest.mark.parametrize("tool_name", _PYLINT_TOOL_NAMES)
    def test_runner_pylint_command_given_default_runner_config_then_passes_no_jobs_flag(
        self, tool_name: str, tmp_path: Path
    ) -> None:
        """OBSERVED: the runner keeps every pylint invocation single-process."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("APP = 1\n")
        config = RunnerConfig(cwd=tmp_path)

        spec = TOOLS_BY_NAME[tool_name]
        assert spec.command == ["pylint"]
        command = _strategy_for(tool_name, spec).build_command(config=config)
        assert "-j" not in command
        assert "--jobs" not in command
        assert not any(argument.startswith("--jobs=") for argument in command)

    def test_runner_pylint_tools_given_registry_order_then_three_sequential_specs_share_executable(
        self,
    ) -> None:
        """OBSERVED: pylint, pylint-pyi and pylint tests are separate sequential invocations."""
        pylint_tools = [spec for spec in TOOLS if spec.command == ["pylint"]]
        assert [spec.name for spec in pylint_tools] == list(_PYLINT_TOOL_NAMES)
        assert all(spec.supports_path for spec in pylint_tools)

    def test_pylint_linter_given_default_options_then_jobs_equals_one(self) -> None:
        """OBSERVED at pylint 4.0.6: the default run has no worker pool."""
        assert PyLinter().config.jobs == 1

    def test_pylint_linter_given_jobs_over_one_then_dispatches_parallel_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: ``-j > 1`` hands lints to ``check_parallel`` (separate process writers)."""
        source = tmp_path / "sample.py"
        source.write_text("VALUE = 1\n")
        dispatched: list[int] = []

        def _record_parallel(
            _linter: PyLinter,
            jobs: int,
            _files: object,
            _extra_packages_paths: object = None,
        ) -> None:
            dispatched.append(jobs)

        monkeypatch.setattr("pylint.lint.pylinter.check_parallel", _record_parallel)
        linter = PyLinter()
        linter.set_option("jobs", 2)
        linter.check([str(source)])

        assert dispatched == [2]

    def test_pylint_check_parallel_given_worker_pool_then_uses_process_pool_executor(
        self,
    ) -> None:
        """OBSERVED: parallel pylint workers are processes, not threads, so each writes separately."""
        assert "ProcessPoolExecutor" in inspect.getsource(pylint_parallel.check_parallel)

    def test_runner_pipeline_given_tool_selection_then_dispatches_tools_serially(
        self,
    ) -> None:
        """OBSERVED: ``_run_tool_pipeline`` blocks on ``_run_cmd`` in one loop; no pool imports."""
        runner_dir = Path(semantic_module.__file__).parent.parent / "runner"
        for path in runner_dir.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                assert roots.isdisjoint({"concurrent", "multiprocessing"}), path.name

        cli_tree = ast.parse((runner_dir / "cli.py").read_text())
        pipeline = next(
            node for node in ast.walk(cli_tree) if isinstance(node, ast.FunctionDef) and node.name == "_run_tool_pipeline"
        )
        serial_loops = [
            node
            for node in ast.walk(pipeline)
            if isinstance(node, ast.For)
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "_select_lint_tools"
        ]
        assert len(serial_loops) == 1
        assert any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_run_cmd"
            for call in ast.walk(serial_loops[0])
        )
