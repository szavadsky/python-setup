"""Shared adapter helpers: corpus loading, prompt rendering, timing, output."""

from __future__ import annotations

import json
import math
import resource
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "out"


def load_corpus() -> list[dict[str, Any]]:
    with (DATA / "corpus.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def load_prompts() -> dict[str, Any]:
    return json.loads((ROOT / "eval" / "prompts.json").read_text(encoding="utf-8"))


def render_state(item: dict[str, Any], variant: dict[str, Any]) -> str:
    return variant["state"].format(
        justification=item["justification"],
        rule=item.get("rule") or "(unknown)",
        context=item.get("context") or "(none)",
    )


def render_query(item: dict[str, Any], variant: dict[str, Any]) -> str:
    return variant["query"].format(
        rule=item.get("rule") or "(unknown)",
        context=(item.get("context") or "(none)")[:200],
    )


def decision_question(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "meaningful": {
            "type": "noul",
            "instructions": variant["instructions"],
            "criteria": {"true": variant["true"], "false": variant["false"]},
        }
    }


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


@contextmanager
def timed() -> Iterator[dict[str, float]]:
    start = time.perf_counter()
    box: dict[str, float] = {}
    try:
        yield box
    finally:
        box["latency_ms"] = (time.perf_counter() - start) * 1000.0


def write_scores(model: str, prompt_name: str, rows: list[dict[str, Any]], meta: dict[str, Any]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    scores_path = OUT / f"scores__{model}__{prompt_name}.jsonl"
    with scores_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    meta_path = OUT / f"meta__{model}__{prompt_name}.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return scores_path


def item_id(item: dict[str, Any]) -> str:
    return str(item["id"])
