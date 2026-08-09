"""Public Part 2 matching entry points consumed by the UI adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai.explanation import generate_match_explanation

from .graph_matching import max_weight_matching
from .hard_filter import pass_hard_constraints
from .reciprocal_score import reciprocal_match_score


def _fallback_reasons(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any], dimensions: Mapping[str, float]
) -> list[str]:
    reasons: list[str] = []
    if dimensions.get("time", 0) >= 80:
        reasons.append("双方有稳定且连续的共同空闲时间。")
    if user_a.get("goal") == user_b.get("goal"):
        reasons.append("两人的本周行动目标一致。")
    if dimensions.get("level", 0) >= 80:
        reasons.append("活动水平处于双方可接受范围内。")
    if dimensions.get("communication", 0) >= 80:
        reasons.append("交流方式偏好接近。")
    if dimensions.get("interest", 0) >= 50:
        reasons.append("兴趣标签存在明显重合。")
    return reasons


def build_match(user_a: Mapping[str, Any], user_b: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build one contract-compatible match if the pair passes hard filters."""

    hard = pass_hard_constraints(user_a, user_b)
    if not hard.passed:
        return None

    scores = reciprocal_match_score(user_a, user_b)
    dimension_scores = scores["dimension_scores"]
    reasons = generate_match_explanation(
        user_a,
        user_b,
        dimension_scores=dimension_scores,
        text_scores=scores["text_scores"],
        limit=4,
    )
    for reason in _fallback_reasons(user_a, user_b, dimension_scores):
        if len(reasons) >= 4:
            break
        if reason not in reasons:
            reasons.append(reason)

    return {
        "user_a": str(user_a["user_id"]),
        "user_b": str(user_b["user_id"]),
        "a_to_b": round(float(scores["a_to_b"]), 1),
        "b_to_a": round(float(scores["b_to_a"]), 1),
        "score": round(float(scores["score"]), 1),
        "dimension_scores": dimension_scores,
        "reasons": reasons or ["两份行动卡通过硬性条件过滤，可进一步沟通安排。"],
        "common_times": list(hard.common_times),
        "common_locations": list(hard.common_locations),
    }


def run_matching(
    current_profile: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return the top compatible candidates for one current profile."""

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k 必须是大于 0 的整数")
    matches: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    current_id = str(current_profile["user_id"])
    for candidate in candidates:
        candidate_id = str(candidate.get("user_id", ""))
        if not candidate_id or candidate_id == current_id or candidate_id in seen_candidates:
            continue
        seen_candidates.add(candidate_id)
        match = build_match(current_profile, candidate)
        if match is not None:
            matches.append(match)
    return sorted(matches, key=lambda item: (-item["score"], item["user_b"]))[:top_k]


def _all_edges(users: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    user_list = list(users)
    for index, user_a in enumerate(user_list):
        for user_b in user_list[index + 1 :]:
            match = build_match(user_a, user_b)
            if match is not None:
                edges.append(match)
    return edges


def run_global_matching(users: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Run a one-to-one maximum-weight matching across a whole cohort."""

    return max_weight_matching(_all_edges(users))


__all__ = ["build_match", "run_global_matching", "run_matching"]
