"""python-setup: shared linting, formatting, and dev tooling for Python projects."""

from importlib.metadata import version as _version

__version__: str = _version("python-setup")
__all__: list[str] = []
