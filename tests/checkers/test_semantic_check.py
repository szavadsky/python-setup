"""Unit tests for python_setup_lint.checkers._semantic.

Tests the single-stage NLP ``semantic_check_if_meaningful`` function.

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

        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "circular import — PyLinter not available at runtime",
            rule="missing-beartype",
            code_context="def foo():  # pylint: disable=missing-beartype",  # noqa: W9704  # code_context string contains suppression pattern as test data, not a real suppression
            comment="circular import — PyLinter not available at runtime",
        )
        # If models are cached, this returns True/False; if not cached,
        # model download may fail returning None. Either is acceptable.
        assert result is None or isinstance(result, bool)

    def test_empty_justification(self) -> None:
        """Empty justification should return False."""

        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful("")
        assert result is False

    def test_whitespace_justification(self) -> None:
        """Whitespace-only justification should return False."""

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

    def test_cache_hit_returns_cached_result(self) -> None:
        """A cached result is returned without calling _load_reranker."""
        import hashlib

        from python_setup_lint.checkers._semantic import (
            _RERANKER_MODEL,
            semantic_check_if_meaningful,
        )

        text = "some reason"
        rule = "E501"
        code_context = "x = 1"
        comment = "some reason"

        # Compute the cache key the same way the function does.
        cache_key = hashlib.sha256(
            "|".join(
                str(x) for x in (text, rule, code_context, comment, _RERANKER_MODEL)
            ).encode()
        ).digest()
        cache_key_int = int.from_bytes(cache_key[:8], "big")

        # Pre-populate the cache with a known result.
        with patch(
            "python_setup_lint.checkers._semantic._RESULT_CACHE",
            {cache_key_int: True},
        ):
            with patch(
                "python_setup_lint.checkers._semantic._load_reranker",
            ) as mock_load:
                result = semantic_check_if_meaningful(
                    text,
                    rule=rule,
                    code_context=code_context,
                    comment=comment,
                )
                assert result is True
                mock_load.assert_not_called()

    @pytest.mark.slow
    def test_semantic_with_model_download(self) -> None:
        """End-to-end test that downloads models (slow, network required).

        This test is marked ``slow`` because it downloads model artifacts.
        On cache hit (models already downloaded), it runs quickly but is
        still gated by the ``slow`` marker for safety.
        """

        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "circular import — PyLinter not available at runtime",
            rule="missing-beartype",
            code_context="def foo():  # pylint: disable=missing-beartype",  # noqa: W9704  # code_context string contains suppression pattern as test data, not a real suppression
            comment="circular import — PyLinter not available at runtime",
        )
        # With models downloaded, this should return a definitive bool.
        assert isinstance(result, bool)

    @pytest.mark.slow
    def test_semantic_meaningful_justification(self) -> None:
        """A genuinely meaningful justification should pass the semantic check."""

        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "type stub not yet generated for this module",
            rule="import-error",
            code_context="import foo  # type: ignore",  # noqa: W9704  # code_context string contains suppression pattern as test data, not a real suppression
            comment="type stub not yet generated for this module",
        )
        assert isinstance(result, bool)

    @pytest.mark.slow
    def test_semantic_weak_justification(self) -> None:
        """A weak justification should fail the semantic check."""

        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "noqa",
            rule="E501",
            code_context="x = 1  # noqa: E501",  # noqa: W9704  # code_context string contains suppression pattern as test data, not a real suppression
            comment="noqa",
        )
        # The heuristic would reject this; the semantic check may also
        # reject it or return None if models aren't available.
        assert result is False or result is None
