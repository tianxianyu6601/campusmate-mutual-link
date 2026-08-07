"""Generate transparent, rule-based reasons for a CampusMate recommendation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from data import vocabulary as vocab

from .text_similarity import bidirectional_text_scores


def _labels(values: Sequence[str], mapping: Mapping[str, str]) -> str:
    return "、".join(mapping.get(value, value) for value in values)


def _common_times(user_a: Mapping[str, Any], user_b: Mapping[str, Any]) -> list[str]:
    return sorted(set(user_a.get("available_times", [])) & set(user_b.get("available_times", [])))


def generate_match_explanation(
    user_a: Mapping[str, Any],
    user_b: Mapping[str, Any],
    *,
    dimension_scores: Mapping[str, float] | None = None,
    text_scores: Mapping[str, float] | None = None,
    limit: int = 4,
) -> list[str]:
    """Return concise reasons grounded only in the two anonymous profiles."""

    if limit < 1:
        raise ValueError("理由数量至少为 1")
    reasons: list[str] = []
    common_times = _common_times(user_a, user_b)
    if common_times:
        displayed = _labels(common_times[:2], vocab.TIME_SLOTS)
        reasons.append(f"你们至少有共同空闲时间：{displayed}。")

    common_locations = sorted(
        set(user_a.get("acceptable_locations", []))
        & set(user_b.get("acceptable_locations", []))
    )
    if common_locations:
        reasons.append(f"双方都接受在{_labels(common_locations[:2], vocab.LOCATIONS)}活动。")

    if user_a.get("goal") == user_b.get("goal"):
        match_type = str(user_a.get("match_type", ""))
        goal = vocab.GOALS.get(match_type, {}).get(str(user_a.get("goal")), "相近目标")
        reasons.append(f"本周行动目标一致：{goal}。")

    common_interests = sorted(set(user_a.get("interests", [])) & set(user_b.get("interests", [])))
    if common_interests:
        reasons.append(f"你们共有兴趣标签：{_labels(common_interests[:3], vocab.INTEREST_TAGS)}。")

    if user_a.get("communication_style") == user_b.get("communication_style"):
        style = vocab.COMMUNICATION_STYLES.get(str(user_a.get("communication_style")), "相近的交流方式")
        reasons.append(f"相处方式相近，都偏好“{style}”。")

    scores = text_scores or bidirectional_text_scores(user_a, user_b)
    if min(float(scores["a_to_b"]), float(scores["b_to_a"])) >= 18:
        reasons.append("双方对搭子的文字期待与自我描述具有较高契合度。")

    if dimension_scores:
        best_dimension = max(dimension_scores, key=dimension_scores.get)
        if dimension_scores[best_dimension] >= 80:
            label = vocab.PREFERENCE_DIMENSIONS.get(best_dimension, best_dimension)
            reasons.append(f"在“{label}”维度上得分突出。")

    if not reasons:
        reasons.append("两份行动卡存在可进一步确认的匹配点，建议先沟通具体安排。")
    return reasons[:limit]


__all__ = ["generate_match_explanation"]
