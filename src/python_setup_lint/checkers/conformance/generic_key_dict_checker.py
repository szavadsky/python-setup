"""Pylint checker: prohibit generic-key ``dict[str, X]`` annotations.

Flags ``dict[str, X]`` / ``Dict[str, X]`` annotations where the key
semantically represents a typed domain value (e.g. a rule-id, enum, or
other non-string domain concept) and recommends ``LintRuleId``, an enum,
or a ``Literal`` type instead.

Allowed categories (configurable via ``allow-string-keys-for``):
- ``filenames`` — dict keyed by file paths.
- ``identifiers`` — dict keyed by Python identifiers (symbol names).
- ``paths`` — dict keyed by ``pathlib.Path``-like values.
- ``display`` — dict keyed by human-readable display strings.
"""

from __future__ import annotations


from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import LintRuleId, MessageDef

# Domain-type value names — dict values whose type name suggests a
# domain concept rather than a generic string-keyed mapping.
_DOMAIN_VALUE_TYPES: frozenset[str] = frozenset({
    "MessageDef",
    "Record",
    "RuleEntry",
    "LintResult",
    "ToolSpec",
    "RunnerConfig",
})


class GenericKeyDictChecker(BaseChecker):
    """AST visitor that flags ``dict[str, X]`` with domain-typed values."""

    name: str = "generic-key-dict"
    msgs: dict[LintRuleId, MessageDef] = {
        "W9721": MessageDef(
            message="'dict[str, %s]' uses a generic string key; consider LintRuleId, enum, or Literal instead",
            symbol="generic-key-dict",
            description="Dicts keyed by string where the value is a domain type "
            "should use a typed key (LintRuleId, enum, Literal). "
            "Use 'allow-string-keys-for' config to suppress for legitimate categories.",
        ),
    }
    options = (
        (
            "allow-string-keys-for",
            {
                "type": "csv",
                "metavar": "<categories>",
                "default": ["filenames", "identifiers", "paths", "display"],
                "help": "Comma-separated list of allowed string-key categories: "
                "filenames, identifiers, paths, display.",
            },
        ),
    )

    @beartype
    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._allowed: set[str] = set()

    @beartype
    def open(self) -> None:
        self._allowed = {
            c.strip() for c in self.linter.config.allow_string_keys_for
        }

    @beartype
    def visit_subscript(self, node: nodes.Subscript) -> None:
        self._check_dict_str_key(node)

    def _check_dict_str_key(self, node: nodes.Subscript) -> None:
        """Check if *node* is a ``dict[str, X]`` annotation with a domain value."""
        # Must be a subscript like dict[...] or Dict[...]
        if not isinstance(node.value, (nodes.Name, nodes.Attribute)):
            return
        # Check the subscripted name is 'dict' or 'Dict'
        if isinstance(node.value, nodes.Name):
            name = node.value.name
        elif isinstance(node.value, nodes.Attribute):
            name = node.value.attrname
        else:
            return
        if name not in ("dict", "Dict"):
            return

        # Must have a slice (the subscript arguments)
        slc = node.slice
        if not isinstance(slc, nodes.Tuple):
            return
        if len(slc.elts) < 2:
            return

        key_node = slc.elts[0]
        value_node = slc.elts[1]

        # Key must be 'str'
        if not isinstance(key_node, nodes.Name) or key_node.name != "str":
            return

        # Extract the value type name
        value_type = self._extract_type_name(value_node)
        if value_type is None:
            return

        # Check if the value type is a domain type
        if value_type not in _DOMAIN_VALUE_TYPES:
            return

        # Check if the variable name suggests an allowed category
        var_name = self._infer_var_name(node)
        if var_name is not None and self._is_allowed_category(var_name):
            return

        self.add_message(
            "generic-key-dict",
            node=node,
            args=(value_type,),
        )

    @staticmethod
    def _extract_type_name(node: nodes.NodeNG) -> str | None:
        """Extract the type name from a subscript value node."""
        if isinstance(node, nodes.Name):
            return node.name
        if isinstance(node, nodes.Attribute):
            return node.attrname
        if isinstance(node, nodes.Subscript):
            # e.g. tuple[...] — extract the base name
            if isinstance(node.value, nodes.Name):
                return node.value.name
            if isinstance(node.value, nodes.Attribute):
                return node.value.attrname
        return None

    @staticmethod
    def _infer_var_name(node: nodes.Subscript) -> str | None:
        """Walk up to find the variable name this annotation is assigned to."""
        parent = node.parent
        # AnnAssign: x: dict[str, X] = ...
        if isinstance(parent, nodes.AnnAssign) and isinstance(parent.target, nodes.AssignName):
            return parent.target.name
        # Assign: x = ...  (type annotation on the value side)
        if isinstance(parent, nodes.Assign) and isinstance(parent.targets[0], nodes.AssignName):
            return parent.targets[0].name
        return None

    def _is_allowed_category(self, var_name: str) -> bool:
        """Check if a variable name suggests an allowed string-key category."""
        lower = var_name.lower()
        # ``msgs`` is the canonical pylint checker message dict — always allowed.
        if lower == "msgs":
            return True
        if "filename" in lower or "file" in lower or "_path" in lower or "path" in lower:
            return "filenames" in self._allowed or "paths" in self._allowed
        if "index" in lower or "map" in lower or "by_" in lower:
            return "identifiers" in self._allowed
        if "display" in lower or "label" in lower or "name" in lower:
            return "display" in self._allowed
        return False


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype,docstring-in-impl  # pylint entry point, signature fixed by pylint API; one-liner, not usage docs
    """Register the checker with the linter."""
    linter.register_checker(GenericKeyDictChecker(linter))
