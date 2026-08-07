"""Reproducible wrappers for comparing matching algorithms.

Member 4 owns evaluation, while each callable passed in is supplied by the
matching-algorithm module. This keeps the experimental code independent of a
specific Part 2 implementation.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

from .metrics import evaluate_matches


Matcher = Callable[[Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]]


def compare_algorithms(
    users: Sequence[Mapping[str, Any]], algorithms: Mapping[str, Matcher]
) -> list[dict[str, Any]]:
    """Run each named matcher once and return comparable result rows."""

    if not algorithms:
        raise ValueError("至少提供一种匹配算法")
    reports: list[dict[str, Any]] = []
    for name, matcher in algorithms.items():
        if not isinstance(name, str) or not name.strip() or not callable(matcher):
            raise TypeError("算法名称必须是非空文本，算法必须可调用")
        started = perf_counter()
        matches = list(matcher(users))
        elapsed_ms = (perf_counter() - started) * 1000
        report = evaluate_matches(matches, participant_count=len(users))
        reports.append({"algorithm": name, "runtime_ms": round(elapsed_ms, 3), **report})
    return reports


def save_experiment_report(report: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    """Save a UTF-8 JSON report for charts and the written experiment section."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(list(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


__all__ = ["compare_algorithms", "save_experiment_report"]
