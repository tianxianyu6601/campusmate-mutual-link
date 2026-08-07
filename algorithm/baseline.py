"""Baseline matchers for Part 2 experiments."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from .hard_filter import pass_hard_constraints
from .pipeline import build_match


def random_matching(
    users: Sequence[Mapping[str, Any]], *, seed: int = 20260802
) -> list[dict[str, Any]]:
    """Randomly pair compatible users after hard filtering."""

    remaining = list(users)
    random.Random(seed).shuffle(remaining)
    matches: list[dict[str, Any]] = []
    used: set[str] = set()
    for user_a in remaining:
        user_a_id = str(user_a["user_id"])
        if user_a_id in used:
            continue
        for user_b in remaining:
            user_b_id = str(user_b["user_id"])
            if user_b_id in used or user_a_id == user_b_id:
                continue
            if pass_hard_constraints(user_a, user_b).passed:
                match = build_match(user_a, user_b)
                if match is not None:
                    matches.append(match)
                    used.update((user_a_id, user_b_id))
                break
    return matches


def interest_greedy_matching(users: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Greedily match pairs with the highest shared-interest count."""

    edges: list[tuple[int, str, str, dict[str, Any]]] = []
    user_list = list(users)
    for index, user_a in enumerate(user_list):
        for user_b in user_list[index + 1 :]:
            if not pass_hard_constraints(user_a, user_b).passed:
                continue
            shared_count = len(set(user_a.get("interests", [])) & set(user_b.get("interests", [])))
            match = build_match(user_a, user_b)
            if match is not None:
                edges.append((shared_count, str(user_a["user_id"]), str(user_b["user_id"]), match))

    matches: list[dict[str, Any]] = []
    used: set[str] = set()
    for _shared_count, user_a_id, user_b_id, match in sorted(
        edges, key=lambda item: (-item[0], item[1], item[2])
    ):
        if user_a_id in used or user_b_id in used:
            continue
        matches.append(match)
        used.update((user_a_id, user_b_id))
    return matches


__all__ = ["interest_greedy_matching", "random_matching"]
