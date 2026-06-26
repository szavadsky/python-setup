from __future__ import annotations

from pathlib import Path

import structlog
from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TC002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import MessageDef, _is_under_source_root

log = structlog.get_logger(__name__)


class StructlogChecker(BaseChecker):

    name: str = "structlog-checker"
    msgs: dict[str, MessageDef] = {
        "W9710": MessageDef(
            message="Use structlog.get_logger instead of logging.getLogger in '%s'",
            symbol="use-structlog",
            description="Prefer structlog over stdlib logging for structured logging.",
        ),
        "W9711": MessageDef(
            message="Use structured kwargs instead of printf-style formatting in '%s'",
            symbol="use-structured-logging",
            description="Logger calls should use keyword arguments for structured fields, "
            "not printf-style positional args or f-string messages.",
        ),
    }
    options = (
        (
            "source-roots",
            {
                "type": "csv",
                "metavar": "<dirs>",
                "default": ["src"],
                "help": "Source root directories for production code.",
            },
        ),
    )

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._source_roots: list[Path] = []
        self._uses_stdlib_logging: bool = False

    @beartype
    def open(self) -> None:
        config = self.linter.config
        self._source_roots = [
            Path(p).resolve() for p in getattr(config, "source_roots", ["src"])
        ]

    @beartype
    def visit_module(self, _node: nodes.Module) -> None:
        self._uses_stdlib_logging = False

    @beartype
    def visit_call(self, node: nodes.Call) -> None:
        self._check_logging_getlogger(node)
        self._check_logger_method_call(node)

    def _check_logging_getlogger(self, node: nodes.Call) -> None:
        func = node.func
        if not isinstance(func, nodes.Attribute):
            return
        if func.attrname != "getLogger":
            return
        if not isinstance(func.expr, nodes.Name):
            return
        if func.expr.name != "logging":
            return

        file_path = self._get_node_file_path(node)
        if file_path is None or not _is_under_source_root(file_path, self._source_roots):
            return

        self._uses_stdlib_logging = True
        self.add_message("use-structlog", node=node, args=(func.expr.name,))

    def _check_logger_method_call(self, node: nodes.Call) -> None:
        func = node.func
        if not isinstance(func, nodes.Attribute):
            return
        if func.attrname not in ("debug", "info", "warning", "error", "critical"):
            return

        # Source root check: skip files outside configured source roots
        file_path = self._get_node_file_path(node)
        if file_path is None or not _is_under_source_root(file_path, self._source_roots):
            return

        callee = func.expr
        if not isinstance(callee, nodes.Name):
            return
        # Only flag calls on variables named like log/logger (not parser.error, etc.)
        if callee.name not in ("log", "logger", "_log", "_logger"):
            return

        if not node.args:
            return

        first_arg = node.args[0]

        if isinstance(first_arg, nodes.JoinedStr):
            self.add_message(
                "use-structured-logging",
                node=node,
                args=(func.attrname,),
            )
            return

        if len(node.args) > 1:
            self.add_message(
                "use-structured-logging",
                node=node,
                args=(func.attrname,),
            )
            return

        if isinstance(first_arg, nodes.Const) and isinstance(first_arg.value, str):
            val: str = first_arg.value
            if "%" in val and self._has_format_spec(val):
                self.add_message(
                    "use-structured-logging",
                    node=node,
                    args=(func.attrname,),
                )
    @staticmethod
    def _get_node_file_path(node: nodes.NodeNG) -> Path | None:
        try:
            file_val = node.root().file
            if file_val is None:
                return None
            return Path(file_val)
        except (AttributeError, TypeError):
            return None

    @staticmethod
    def _has_format_spec(s: str) -> bool:
        i = 0
        while i < len(s):
            if s[i] == "%" and i + 1 < len(s):
                nxt = s[i + 1]
                if nxt == "%":
                    i += 2
                    continue
                if nxt in "sdfgeEoxXc":
                    return True
                j = i + 1
                while j < len(s) and s[j] in "0123456789.-+#":
                    j += 1
                if j < len(s) and s[j] in "sdfgeEoxXc":
                    return True
            i += 1
        return False


def register(  # pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime
    linter: PyLinter,
) -> None:
    linter.register_checker(StructlogChecker(linter))
