"""Pin the writer, timing, and ``--path`` scoping of the cache written during pylint runs.

Observed at HEAD with pylint 4.0.6 -- the current floor in ``pyproject.toml``
(``pylint>=4.0.6``), so these tests double as the upgrade watchdog: a newer
pylint that shifts the ``jobs`` default or the ``check_parallel`` dispatch
fails them.  The tracked cache in this verdict is the semantic result cache
consumed by ``epic-semantic-infrastructure`` -- not pylint's separate
persistent ``~/.cache/pylint/*.stats`` bookkeeping (a Linux example; pylint's
persistent-data home is platform-dependent).

WRITER-FIRST VERDICT (feeds ``cache-design-spike``)
===================================================
* **Writer identity** -- the checker call path writes the cache while pylint is
  linting: ``python_setup_lint.checkers._semantic.semantic_check_if_meaningful``
  calls ``_save_result_cache``.  The runner performs no post-process merge and
  checker ``open()``/``close()`` hooks do not write the file.
* **Timing** -- one whole-file rewrite per newly computed verdict (cache miss),
  synchronously before the check returns.  Cache hits, heuristic fallbacks
  (reranker unavailable), and the empty-primary short-circuit (``False``
  before key computation) write nothing.
* **``--path`` scoping** -- the runner's ``--path`` narrows only the file
  arguments passed to each pylint invocation.  The cache is a single
  home-directory file and the key is SHA-256 over
  ``(text, rule, code_context, comment, model)``: no file path participates, so
  scoped and full runs share entries across the sequential ``pylint``,
  ``pylint-pyi`` and ``pylint tests`` invocations.
* **Sweep implication** -- because cache identity is path-free, ``--path``
  cannot partition the cache.  Prune/sweep scope would need per-entry file
  references -- a future tracked schema needs a ``files`` field per entry;
  today's schema is only ``dict[int, bool]`` -- not the lint invocation's path
  argument.
* **Concurrency** -- the runner executes tools sequentially and none of the
  three pylint specs passes ``-j``/``--jobs``; pylint's default ``jobs`` is 1,
  and the shipped ``config/.pylintrc*`` files do not raise it (watchdog test).
  The single-writer claim holds *only while the effective ``jobs`` is 1*, so
  no lockfile, runner-side merge, or sidecar files are required today.  The
  runner resolves the rcfile from ``--config pylint=PATH``, then
  ``cwd/config/.pylintrc``, then ``cwd/.pylintrc``: a consumer rcfile or
  override that sets ``jobs > 1`` (or ``jobs = 0`` auto-detect) silently
  enables pylint's process pool and voids the claim.  If that happens, pylint
  dispatches separate processes and the verdict flips to per-writer sidecars
  plus a runner merge (or a crash-safe lock plus atomic replace).
* **Crash safety** -- the writer is a non-atomic ``Path.write_text``.  A crash
  mid-write can lose entries but cannot break lint: unparsable JSON loads as an
  empty cache and is recomputed.

These tests *are* the verdict: when one fails, re-derive the writer-first
semantics before changing the assertion rather than loosening it.
"""

from __future__ import annotations

import ast
import configparser
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pylint.lint.parallel as pylint_parallel
import pytest
from pylint.lint import PyLinter

import python_setup_lint.checkers._semantic as semantic_module
from python_setup_lint.checkers._semantic import semantic_check_if_meaningful
from python_setup_lint.runner._config import _default_config_paths
from python_setup_lint.runner.cmd_build import _resolve_pylintrc
from python_setup_lint.runner.dispatch import TOOLS, TOOLS_BY_NAME, _strategy_for
from python_setup_lint.runner.types import RunnerConfig

pytestmark = pytest.mark.no_external_api

_PYLINT_TOOL_NAMES = ("pylint", "pylint-pyi", "pylint tests")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHIPPED_PYLINT_RCFILES = tuple(sorted((_REPO_ROOT / "config").glob(".pylintrc*")))


class _FakeReranker:
    """Stand-in for the optional cross-encoder so cache writes are exercised offline."""

    def __init__(self, score: float) -> None:
        self.score = score
        self.calls = 0

    def predict(self, _pairs: list[tuple[str, str]]) -> list[float]:
        """Return a fixed score and count invocations."""
        self.calls += 1
        return [self.score]


def _expected_cache_key(text: str, *, rule: str, code_context: str, comment: str) -> int:
    """Compute the documented path-free cache key independently of the writer."""
    model = cast(Any, semantic_module)._RERANKER_MODEL
    payload = f"{text}|{rule}|{code_context}|{comment}|{model}"
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def _is_save_result_cache_call(node: ast.Call) -> bool:
    """Match bare and attribute-qualified calls to the cache writer."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "_save_result_cache"
    return isinstance(func, ast.Attribute) and func.attr == "_save_result_cache"


def _pylintrc_jobs_overrides(rcfile: Path) -> list[tuple[str, int]]:
    """Return effective ``jobs`` options from *rcfile* as ``(section, value)`` pairs.

    Pylint 4.0.6 flattens options from every rcfile section into CLI flags, so a
    ``jobs`` key anywhere in the file is effective.
    """
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#", ";"))
    parser.read_string(rcfile.read_text())
    return [(section, int(parser[section]["jobs"])) for section in parser.sections() if parser.has_option(section, "jobs")]


@pytest.fixture
def semantic_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route the semantic result cache to a per-test directory."""
    cache_dir = tmp_path / "semantic"
    cache_file = cache_dir / "results.json"
    monkeypatch.setattr("python_setup_lint.checkers._semantic._CACHE_DIR", cache_dir)
    monkeypatch.setattr("python_setup_lint.checkers._semantic._RESULT_CACHE_FILE", cache_file)
    monkeypatch.setattr("python_setup_lint.checkers._semantic._RESULT_CACHE", None)
    return cache_file


class TestSemanticCacheWriter:
    """Writer identity and timing of the cache produced inside a pylint run."""

    def test_semantic_check_if_meaningful_given_new_verdicts_then_writes_each_miss_immediately(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the in-process check call is the writer; each miss rewrites the file."""
        reranker = _FakeReranker(score=0.9)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: reranker)

        assert not semantic_cache.exists()

        assert (
            semantic_check_if_meaningful(
                "guarded by a lock",
                rule="W9704",
                code_context="lock = Lock()",
                comment="guarded by a lock",
            )
            is True
        )
        first_payload = json.loads(semantic_cache.read_text())
        assert list(first_payload.values()) == [True]

        assert (
            semantic_check_if_meaningful(
                "retry is idempotent",
                rule="W9704",
                code_context="retry()",
                comment="retry is idempotent",
            )
            is True
        )
        second_payload = json.loads(semantic_cache.read_text())
        assert len(second_payload) == 2
        assert first_payload.keys() <= second_payload.keys()
        assert set(second_payload.values()) == {True}
        assert reranker.calls == 2

        # In-memory hit: no reranker call and no extra file rewrite.
        assert (
            semantic_check_if_meaningful(
                "guarded by a lock",
                rule="W9704",
                code_context="lock = Lock()",
                comment="guarded by a lock",
            )
            is True
        )
        assert reranker.calls == 2
        assert json.loads(semantic_cache.read_text()) == second_payload

    def test_semantic_check_if_meaningful_given_persisted_entry_then_serves_it_without_model_or_write(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the cache is lazy-loaded from disk; a hit reaches neither writer nor model."""
        text, rule, code_context, comment = (
            "persisted verdict",
            "W9704",
            "guard()",
            "persisted verdict",
        )
        key = _expected_cache_key(text, rule=rule, code_context=code_context, comment=comment)
        semantic_cache.parent.mkdir(parents=True)
        semantic_cache.write_text(json.dumps({str(key): False}))
        persisted = semantic_cache.read_text()

        def _unexpected_load() -> None:
            raise AssertionError("cache hit must not load the reranker")

        def _unexpected_write() -> None:
            raise AssertionError("cache hit must not rewrite the result cache")

        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", _unexpected_load)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._save_result_cache", _unexpected_write)

        assert semantic_check_if_meaningful(text, rule=rule, code_context=code_context, comment=comment) is False
        assert semantic_cache.read_text() == persisted

    def test_semantic_check_if_meaningful_given_reranker_unavailable_then_writes_no_entry(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the heuristic fallback path (None) creates neither cache file nor directory."""
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: None)

        assert semantic_check_if_meaningful("checked elsewhere", rule="W9704", code_context="x = 1") is None
        assert not semantic_cache.exists()
        assert not semantic_cache.parent.exists()

    def test_semantic_check_if_meaningful_given_empty_primary_then_returns_false_without_writing(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the empty-primary short-circuit returns False before key computation and writes nothing."""
        reranker = _FakeReranker(score=0.9)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: reranker)

        assert semantic_check_if_meaningful("", rule="W9704", code_context="x = 1", comment="   ") is False
        assert reranker.calls == 0
        assert not semantic_cache.exists()
        assert not semantic_cache.parent.exists()

    def test_semantic_check_if_meaningful_given_truncated_cache_file_then_recovers_with_new_entry(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: a crash-truncated file loads as empty and is replaced by a valid rewrite."""
        semantic_cache.parent.mkdir(parents=True)
        semantic_cache.write_text('{"truncated": tru')
        reranker = _FakeReranker(score=0.9)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: reranker)

        assert (
            semantic_check_if_meaningful(
                "crash tolerant",
                rule="W9704",
                code_context="cache = load()",
                comment="crash tolerant",
            )
            is True
        )
        payload = json.loads(semantic_cache.read_text())
        assert payload == {
            str(
                _expected_cache_key(
                    "crash tolerant",
                    rule="W9704",
                    code_context="cache = load()",
                    comment="crash tolerant",
                )
            ): True
        }

    def test_semantic_result_cache_given_single_writer_then_leaves_no_lock_or_sidecar_artifacts(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: sequential writes leave exactly ``results.json`` -- no lock or sidecar files."""
        monkeypatch.setattr(
            "python_setup_lint.checkers._semantic._load_reranker",
            lambda: _FakeReranker(0.9),
        )

        assert semantic_check_if_meaningful("only writer", rule="W9704", code_context="x = 1", comment="only writer") is True
        assert [entry.name for entry in sorted(semantic_cache.parent.iterdir())] == ["results.json"]


class TestSemanticCachePathScoping:
    """The cache is a single path-free store shared by every pylint invocation."""

    def test_semantic_check_if_meaningful_given_identical_inputs_then_cache_key_ignores_source_path(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: key = SHA-256(text, rule, context, comment, model); the API takes no path."""
        monkeypatch.setattr(
            "python_setup_lint.checkers._semantic._load_reranker",
            lambda: _FakeReranker(0.9),
        )
        text, rule, code_context, comment = (
            "path free key",
            "W9704",
            "value = load()",
            "path free key",
        )

        assert semantic_check_if_meaningful(text, rule=rule, code_context=code_context, comment=comment) is True
        expected = _expected_cache_key(text, rule=rule, code_context=code_context, comment=comment)
        assert json.loads(semantic_cache.read_text()) == {str(expected): True}

        signature = inspect.signature(semantic_check_if_meaningful)
        assert set(signature.parameters).isdisjoint({"path", "file", "filename"})

    def test_semantic_result_cache_file_given_runner_invocations_then_single_home_location(
        self,
    ) -> None:
        """OBSERVED: one process-independent cache file, not a per-path or per-cwd cache."""
        module = cast(Any, semantic_module)
        expected_dir = Path.home() / ".cache" / "python-setup" / "semantic"
        assert expected_dir == module._CACHE_DIR
        assert (expected_dir / "results.json") == module._RESULT_CACHE_FILE

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

    def test_semantic_cache_writer_given_source_tree_then_only_check_call_path_writes(
        self,
    ) -> None:
        """OBSERVED: `_save_result_cache` has one caller; runner code never performs a merge."""
        source = Path(semantic_module.__file__).read_text()
        tree = ast.parse(source)
        save_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_save_result_cache_call(node)]
        assert len(save_calls) == 1
        callers = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(call, ast.Call) and _is_save_result_cache_call(call) for call in ast.walk(node))
        ]
        assert callers == ["semantic_check_if_meaningful"]

        runner_dir = Path(semantic_module.__file__).parent.parent / "runner"
        assert not [
            path.name
            for path in runner_dir.rglob("*.py")
            if "_save_result_cache" in path.read_text() or "_RESULT_CACHE_FILE" in path.read_text()
        ]

        checkers_dir = Path(semantic_module.__file__).parent
        assert not [
            path.name
            for path in checkers_dir.rglob("*.py")
            if path.name != Path(semantic_module.__file__).name
            and ("_save_result_cache" in path.read_text() or "_RESULT_CACHE_FILE" in path.read_text())
        ]


class TestPylintRcfileJobsWatchdog:
    """Shipped rcfiles must leave pylint's ``jobs`` at 1 so the cache writer stays single."""

    def test_shipped_pylint_rcfiles_given_effective_options_then_never_enable_worker_pool(self) -> None:
        """OBSERVED: every shipped rcfile leaves ``jobs`` at its default of 1."""
        assert _SHIPPED_PYLINT_RCFILES
        for rcfile in _SHIPPED_PYLINT_RCFILES:
            assert all(value == 1 for _, value in _pylintrc_jobs_overrides(rcfile)), rcfile

    def test_pylintrc_jobs_scan_given_consumer_jobs_override_then_detects_it(self, tmp_path: Path) -> None:
        """NEGATIVE CONTROL: the watchdog parser flags an rcfile that raises ``jobs``."""
        rcfile = tmp_path / ".pylintrc"
        rcfile.write_text("[MAIN]\njobs=2\n")

        assert _pylintrc_jobs_overrides(rcfile) == [("MAIN", 2)]

    def test_runner_pylint_config_resolution_given_repo_root_then_uses_shipped_jobs_free_rcfiles(self) -> None:
        """OBSERVED: all three pylint invocations resolve to shipped, jobs-free rcfiles."""
        expected_names = {"pylint": ".pylintrc", "pylint-pyi": ".pylintrc-pyi", "pylint tests": ".pylintrc-tests"}
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

    def test_pylint_check_parallel_given_worker_pool_then_uses_process_pool_executor(self) -> None:
        """OBSERVED: parallel pylint workers are processes, not threads, so each writes separately."""
        assert "ProcessPoolExecutor" in inspect.getsource(pylint_parallel.check_parallel)

    def test_runner_pipeline_given_tool_selection_then_dispatches_tools_serially(self) -> None:
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
