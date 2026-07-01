
from __future__ import annotations

import fnmatch
from pathlib import Path

from astroid import nodes  # noqa: TC002


def _matches_path(str_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if "/" in pattern or "\\" in pattern:
            # Directory prefix pattern
            if str_path.startswith(pattern) or f"/{pattern.lstrip('/')}" in str_path:
                return True
        elif fnmatch.fnmatch(str_path, pattern) or fnmatch.fnmatch(
            Path(str_path).name, pattern
        ):
            return True
    return False


def _is_under_source_root(path: Path, source_roots: list[Path]) -> bool:
    resolved = path.resolve()
    for root in source_roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _get_file_path(node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> Path | None:
    try:
        file_val = node.root().file
        if file_val is None:
            return None
        return Path(file_val)
    except (AttributeError, TypeError):  # pylint: disable=W9740  # node may not have file attribute or it may be untyped
        return None
