"""Pin the astroid behaviors that python_setup_lint checkers rely on.

Observed with astroid 4.0.4 (pinned in ``pyproject.toml``).  These tests exercise
the third-party API directly so that a dependency upgrade which changes one of
these contracts fails here, naming the contract, instead of failing in an
unrelated checker test.
"""

from __future__ import annotations

import astroid
import pytest
from astroid import nodes

pytestmark = pytest.mark.no_external_api

_MODULE_SOURCE = '''"""Module doc."""

CONST = 1


class Widget:
    """Widget doc."""

    LIMIT = 2

    def method(self):
        return 3


def factory():
    return 4
'''

_DOC_SOURCE = '''"""Module docstring."""


class Documented:
    """Class docstring."""

    def method(self) -> None:
        """Function docstring."""


class Bare:
    def method(self) -> None:
        return None


def bare_function() -> None:
    return None
'''

_SPAN_SOURCE = 'VALUE = 42\nMESSAGE = f"a{x}b"\nTEXT = """first\nsecond"""\n'


class TestAstroidContracts:
    """Contracts from astroid that the checker source/span logic depends on."""

    def test_module_stream_given_parsed_source_then_read_is_bytes_or_str_tolerated_by_product(
        self,
    ) -> None:
        """OBSERVED at astroid 4.0.4: ``Module.stream().read()`` returns ``bytes``.

        The product tolerates both ``bytes`` and ``str`` by decoding only bytes
        (``raw.decode("utf-8") if isinstance(raw, bytes) else raw``); this test
        pins the observed concrete type and the tolerance expression.
        """
        source = '"""Módulo."""\n\nVALUE = "café"\n'
        module = astroid.parse(source)

        raw = module.stream().read()

        assert isinstance(raw, (bytes, str))
        assert raw.__class__ is bytes, "OBSERVED at astroid 4.0.4: stream().read() returns bytes"
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        assert decoded == source

    def test_doc_node_given_docstrings_then_const_or_joined_str_and_none_when_absent(
        self,
    ) -> None:
        """Docstrings are exposed through ``doc_node`` for module, class and function."""
        module = astroid.parse(_DOC_SOURCE)
        documented_class = module.body[0]
        bare_class = module.body[1]
        bare_function = module.body[2]
        documented_function = documented_class.body[0]

        for container, expected_text in (
            (module, "Module docstring."),
            (documented_class, "Class docstring."),
            (documented_function, "Function docstring."),
        ):
            doc_node = container.doc_node
            assert isinstance(doc_node, (nodes.Const, nodes.JoinedStr))
            # OBSERVED at astroid 4.0.4: docstrings are Const nodes carrying the text in ``value``.
            assert isinstance(doc_node, nodes.Const)
            assert doc_node.value == expected_text

        assert bare_class.doc_node is None
        assert bare_function.doc_node is None
        assert astroid.parse("VALUE = 1\n").doc_node is None

    def test_nodes_of_class_given_class_tuple_then_returns_union_in_document_order(
        self,
    ) -> None:
        """A tuple argument is a union of node kinds, emitted in document (pre-order) order."""
        module = astroid.parse(_MODULE_SOURCE)

        found = list(module.nodes_of_class((nodes.ClassDef, nodes.FunctionDef, nodes.Const)))

        observed = [(type(node).__name__, node.fromlineno) for node in found]
        assert observed == [
            ("Const", 3),
            ("ClassDef", 6),
            ("Const", 9),
            ("FunctionDef", 11),
            ("Const", 12),
            ("FunctionDef", 15),
            ("Const", 16),
        ]
        assert {type(node) for node in found} == {
            nodes.Const,
            nodes.ClassDef,
            nodes.FunctionDef,
        }

    def test_const_and_joined_str_given_literals_then_span_attributes_are_ints(
        self,
    ) -> None:
        """String-literal span logic reads int line/column attributes on Const and JoinedStr."""
        module = astroid.parse(_SPAN_SOURCE)
        const_node = module.body[0].value
        joined_str_node = module.body[1].value
        multiline_const_node = module.body[2].value

        assert isinstance(const_node, nodes.Const)
        assert isinstance(joined_str_node, nodes.JoinedStr)
        assert isinstance(multiline_const_node, nodes.Const)

        for literal, expected_span in (
            (const_node, (1, 1, 8, 10)),
            (joined_str_node, (2, 2, 10, 18)),
            (multiline_const_node, (3, 4, 7, 9)),
        ):
            span = (
                literal.fromlineno,
                literal.end_lineno,
                literal.col_offset,
                literal.end_col_offset,
            )
            assert span == expected_span
            assert all(value.__class__ is int for value in span)
