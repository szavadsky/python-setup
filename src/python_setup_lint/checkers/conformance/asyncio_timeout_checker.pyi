
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class AsyncTimeoutChecker(BaseChecker):
    name: str = "asyncio-timeout"

    def visit_await(self, node: nodes.Await) -> None: ...

def register(linter: PyLinter) -> None: ...