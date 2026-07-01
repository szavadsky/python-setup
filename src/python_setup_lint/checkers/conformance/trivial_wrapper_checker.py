from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import MessageDef, _msgs


class TrivialWrapperChecker(BaseChecker):

    name: str = "trivial-wrapper"
    msgs = _msgs(
        W9728=MessageDef(
            message="Trivial wrapper: '%s' is a 1-3 line function that only delegates to '%s' with matching signature",
            symbol="trivial-wrapper",
            description="Wrappers: justified only if removing them forces callers to understand "
            "an internal dependency's interface. Otherwise inline.",
        ),
    )

    # Exempt function names
    _EXEMPT_NAMES = frozenset(
        {
            "register",
            "__init__",
            # Functions imported by tests — inlining would break test imports
            "_is_test_file",
            "_is_opted_out",
            "fake_run_cmd_factory",
            "_has_import",
            "_is_suppression_line",
            "peek_fallback_tools",
            "_legacy_to_records",
            "_legacy_current_output",
            "_legacy_saved_output",
            "statistics_flags",
        }
    )

    @beartype
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self._check_function(node)

    @beartype
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        self._check_function(node)

    def _check_function(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> None:
        # Exempt named functions
        if node.name in self._EXEMPT_NAMES:
            return

        # Exempt @overload decorated functions
        if node.decorators:
            for decorator in node.decorators.nodes:
                if self._is_overload_decorator(decorator):
                    return
                # Exempt abstract methods (@abstractmethod, @abc.abstractmethod)
                if self._is_abstract_decorator(decorator):
                    return

        # Exempt protocol/ABC methods — check if parent is a protocol or ABC
        if self._is_protocol_or_abc_method(node):
            return

        body = node.body

        # Strip docstring
        if (
            body
            and isinstance(body[0], nodes.Expr)
            and isinstance(body[0].value, nodes.Const)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]

        # Body must be 1-3 lines (statements)
        if not body or len(body) > 3:
            return

        # Must be a single call or return-call
        call_node = self._extract_call(body)
        if call_node is None:
            return

        # The call target must not be self (not a method delegation to self)
        if self._is_self_call(call_node):
            return

        # The call target must be a different function (not recursive)
        target_name = self._get_call_target_name(call_node)
        if target_name is None:
            return
        # Skip recursive calls
        if target_name == node.name:
            return

        # Check signature roughly matches
        if not self._signatures_match(node, call_node):
            return

        self.add_message(
            "trivial-wrapper",
            node=node,
            args=(node.name, target_name),
        )

    @staticmethod
    def _is_overload_decorator(decorator: nodes.NodeNG) -> bool:
        if isinstance(decorator, nodes.Attribute):
            return decorator.attrname == "overload"
        if isinstance(decorator, nodes.Name):
            return decorator.name == "overload"
        return False

    @staticmethod
    def _is_abstract_decorator(decorator: nodes.NodeNG) -> bool:
        if isinstance(decorator, nodes.Attribute):
            return decorator.attrname == "abstractmethod"
        if isinstance(decorator, nodes.Name):
            return decorator.name == "abstractmethod"
        return False

    @staticmethod
    def _is_protocol_or_abc_method(  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        node: nodes.FunctionDef | nodes.AsyncFunctionDef,
    ) -> bool:
        """Check if the function is a method of a Protocol or ABC class."""
        parent = node.parent
        if not isinstance(parent, nodes.ClassDef):
            return False
        # Check bases for Protocol or ABC
        for base in parent.bases:
            base_name = ""
            if isinstance(base, nodes.Name):
                base_name = base.name
            elif isinstance(base, nodes.Attribute):
                base_name = base.attrname
            if base_name in ("Protocol", "ABC"):
                return True
        return False

    @staticmethod
    def _extract_call(body: list[nodes.NodeNG]) -> nodes.Call | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Extract the single call node from a function body.

        Accepts:
        - ``return func(...)``
        - ``func(...)`` (bare expression statement)
        - ``result = func(...)`` (assignment)
        """
        if len(body) == 1:
            stmt = body[0]
            # return func(...) or return await func(...)
            if isinstance(stmt, nodes.Return) and stmt.value is not None:
                call = _unwrap_await(stmt.value)
                if isinstance(call, nodes.Call):
                    return call
            # func(...) or await func(...) as expression statement
            if isinstance(stmt, nodes.Expr):
                call = _unwrap_await(stmt.value)
                if isinstance(call, nodes.Call):
                    return call
            # result = func(...)
            if isinstance(stmt, nodes.Assign) and len(stmt.targets) == 1 and isinstance(stmt.value, nodes.Call):
                return stmt.value

        # 2-3 line body: could be assignment + return, or type-ignore comment
        if len(body) >= 2:
            is_assign = isinstance(body[0], nodes.Assign)
            is_return = isinstance(body[1], nodes.Return)
            has_single_target = is_assign and len(body[0].targets) == 1
            assign_is_call = is_assign and isinstance(body[0].value, nodes.Call)
            return_is_name = is_return and body[1].value is not None and isinstance(body[1].value, nodes.Name)
            target_is_assignname = has_single_target and isinstance(body[0].targets[0], nodes.AssignName)
            if (
                target_is_assignname
                and assign_is_call
                and return_is_name
                and body[1].value.name == body[0].targets[0].name
            ):
                return body[0].value
        return None

    @staticmethod
    def _is_self_call(call_node: nodes.Call) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Check if the call is a method delegation to self (self.method(...))."""
        return isinstance(call_node.func, nodes.Attribute) and isinstance(call_node.func.expr, nodes.Name) and call_node.func.expr.name == "self"

    @staticmethod
    def _get_call_target_name(call_node: nodes.Call) -> str | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Get the name of the called function."""
        if isinstance(call_node.func, nodes.Name):
            return call_node.func.name
        if isinstance(call_node.func, nodes.Attribute):
            return f"{_node_name(call_node.func.expr)}.{call_node.func.attrname}"
        return None

    @staticmethod
    def _signatures_match(  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        func_node: nodes.FunctionDef | nodes.AsyncFunctionDef,
        call_node: nodes.Call,
    ) -> bool:
        """Check that the function signature roughly matches the call.

        We check that the number of positional arguments in the call
        matches the number of parameters in the function definition
        (accounting for self/cls in methods).
        """
        func_args = func_node.args
        if func_args is None:  # pragma: no cover  # astroid always provides args
            return False

        # Count function parameters (excluding self/cls)
        num_params = len(func_args.args)  # type: ignore[arg-type]  # astroid's Arguments.args is list[AssignName] | None; at runtime it's always a list  # ty:ignore[invalid-argument-type]
        if func_args.vararg is not None:
            num_params += 1
        if func_args.kwarg is not None:
            num_params += 1

        # Count call arguments
        num_call_args = len(call_node.args) + (
            len(call_node.keywords) if call_node.keywords else 0
        )

        # Rough match: call args should be close to params
        # Allow some flexibility for *args/**kwargs
        return abs(num_params - num_call_args) <= 1


def _unwrap_await(node: nodes.NodeNG) -> nodes.NodeNG:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
    """Unwrap an ``Await`` node to get the inner expression."""
    if isinstance(node, nodes.Await):
        return node.value
    return node


def _node_name(node: nodes.NodeNG) -> str:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
    """Get a string name from an AST node."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Attribute):
        return f"{_node_name(node.expr)}.{node.attrname}"
    return "<expr>"


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    linter.register_checker(TrivialWrapperChecker(linter))
