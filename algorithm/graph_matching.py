"""Maximum-weight one-to-one graph matching utilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _networkx_matching(edges: Sequence[Mapping[str, Any]]) -> set[frozenset[str]] | None:
    try:
        import networkx as nx  # type: ignore
    except ModuleNotFoundError:
        return None

    graph = nx.Graph()
    for edge in edges:
        graph.add_edge(
            str(edge["user_a"]),
            str(edge["user_b"]),
            weight=int(round(float(edge["score"]) * 1000)),
        )
    return {
        frozenset(pair)
        for pair in nx.max_weight_matching(graph, maxcardinality=True, weight="weight")
    }


def _greedy_fallback(edges: Sequence[Mapping[str, Any]]) -> set[frozenset[str]]:
    """Deterministic fallback for environments without NetworkX installed."""

    selected: set[frozenset[str]] = set()
    used: set[str] = set()
    ordered = sorted(
        edges,
        key=lambda edge: (
            -float(edge["score"]),
            str(edge["user_a"]),
            str(edge["user_b"]),
        ),
    )
    for edge in ordered:
        user_a = str(edge["user_a"])
        user_b = str(edge["user_b"])
        if user_a in used or user_b in used:
            continue
        selected.add(frozenset((user_a, user_b)))
        used.update((user_a, user_b))
    return selected


def max_weight_matching(edges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Select non-overlapping matches, preferring NetworkX when available."""

    if isinstance(edges, (str, bytes)):
        raise TypeError("候选边必须是列表")
    normalized = [dict(edge) for edge in edges]
    selected_pairs = _networkx_matching(normalized)
    if selected_pairs is None:
        selected_pairs = _greedy_fallback(normalized)
    selected = [
        edge
        for edge in normalized
        if frozenset((str(edge["user_a"]), str(edge["user_b"]))) in selected_pairs
    ]
    return sorted(selected, key=lambda edge: (-float(edge["score"]), edge["user_a"], edge["user_b"]))


__all__ = ["max_weight_matching"]
