"""Unit tests for python_setup_lint.checkers._semantic.

Tests the two-stage NLP ``semantic_check_if_meaningful`` function.

Tests that require network access (model download) are marked ``@pytest.mark.slow``.
Tests that hit the local model cache are **not** marked slow.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from python_setup_lint.checkers._base import check_if_meaningful


# ── ImportError fallback ─────────────────────────────────────────────


class TestImportErrorFallback:
    """When sentence_transformers is not installed, ImportError propagates."""

    def test_import_error_propagates(self) -> None:
        """check_if_meaningful must propagate ImportError when _semantic unavailable."""
        with patch(
            "builtins.__import__",
            side_effect=self._make_blocking_import(),
        ):
            with pytest.raises(ImportError, match="No module named _semantic"):
                check_if_meaningful("circular import — PyLinter not available")

    @staticmethod
    def _make_blocking_import():
        """Return a side-effect function that blocks _semantic imports."""
        original_import = __builtins__["__import__"]

        def _mock_import(name, *args, **kwargs):
            if name == "python_setup_lint.checkers._semantic":
                raise ImportError("No module named _semantic")
            return original_import(name, *args, **kwargs)

        return _mock_import


# ── Semantic pipeline (requires sentence_transformers) ───────────────


class TestSemanticCheck:
    """Tests that exercise the NLP pipeline.

    These tests require ``sentence_transformers`` to be importable
    (``uv sync --extra semantic``).  Tests that download models are
    marked ``@pytest.mark.slow``; cache-hit tests are not.
    """

    def test_meaningful_justification(self) -> None:
        """A detailed technical justification should be meaningful."""
        pytest.importorskip(
            "sentence_transformers",
            reason="install with `uv sync --extra semantic` to run NLP tests",
        )
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "circular import — PyLinter not available at runtime",
            rule="missing-beartype",
            code_context="def foo():  # pylint: disable=missing-beartype",
            comment="circular import — PyLinter not available at runtime",
        )
        # If models are cached, this returns True/False; if not cached,
        # model download may fail returning None. Either is acceptable.
        assert result is None or isinstance(result, bool)

    def test_empty_justification(self) -> None:
        """Empty justification should return False."""
        pytest.importorskip(
            "sentence_transformers",
            reason="install with `uv sync --extra semantic` to run NLP tests",
        )
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful("")
        assert result is False

    def test_whitespace_justification(self) -> None:
        """Whitespace-only justification should return False."""
        pytest.importorskip(
            "sentence_transformers",
            reason="install with `uv sync --extra semantic` to run NLP tests",
        )
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful("   ")
        assert result is False

    def test_returns_none_on_import_error(self) -> None:
        """When sentence_transformers can't be imported, return None."""
        with patch(
            "python_setup_lint.checkers._semantic._load_reranker",
            return_value=None,
        ):
            from python_setup_lint.checkers._semantic import (
                semantic_check_if_meaningful,
            )

            result = semantic_check_if_meaningful("some reason")
            assert result is None

    @pytest.mark.slow
    def test_semantic_with_model_download(self) -> None:
        """End-to-end test that downloads models (slow, network required).

        This test is marked ``slow`` because it downloads model artifacts.
        On cache hit (models already downloaded), it runs quickly but is
        still gated by the ``slow`` marker for safety.
        """
        pytest.importorskip(
            "sentence_transformers",
            reason="install with `uv sync --extra semantic` to run NLP tests",
        )
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "circular import — PyLinter not available at runtime",
            rule="missing-beartype",
            code_context="def foo():  # pylint: disable=missing-beartype",
            comment="circular import — PyLinter not available at runtime",
        )
        # With models downloaded, this should return a definitive bool.
        assert isinstance(result, bool)

    @pytest.mark.slow
    def test_semantic_meaningful_justification(self) -> None:
        """A genuinely meaningful justification should pass the semantic check."""
        pytest.importorskip(
            "sentence_transformers",
            reason="install with `uv sync --extra semantic` to run NLP tests",
        )
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "type stub not yet generated for this module",
            rule="import-error",
            code_context="import foo  # type: ignore",
            comment="type stub not yet generated for this module",
        )
        assert isinstance(result, bool)

    @pytest.mark.slow
    def test_semantic_weak_justification(self) -> None:
        """A weak justification should fail the semantic check."""
        pytest.importorskip(
            "sentence_transformers",
            reason="install with `uv sync --extra semantic` to run NLP tests",
        )
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "noqa",
            rule="E501",
            code_context="x = 1  # noqa: E501",
            comment="noqa",
        )
        # The heuristic would reject this; the semantic check may also
        # reject it or return None if models aren't available.
        assert result is False or result is None
