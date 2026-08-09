"""Directional soft-preference scoring for CampusMate profiles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai.text_similarity import bidirectional_text_scores
from data import vocabulary as vocab

from .hard_filter import best_common_time_window


_LEVEL_ORDER = {"novice": 1, "basic": 2, "intermediate": 3, "advanced": 4}


def _bounded(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 1)


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = {vocab.comparison_key(value) for value in left}
    right_set = {vocab.comparison_key(value) for value in right}
    left_set.discard("")
    right_set.discard("")
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def _rating_similarity(left: int, right: int) -> float:
    return _bounded(100 - abs(int(left) - int(right)) * 25)


def _categorical_similarity(left: Any, right: Any, partial: float = 60.0) -> float:
    return 100.0 if left == right else partial


def _level_score(preference_owner: Mapping[str, Any], candidate: Mapping[str, Any]) -> float:
    candidate_level = str(candidate.get("self_level"))
    acceptable = set(preference_owner.get("acceptable_partner_levels", []))
    if candidate_level not in acceptable:
        return 0.0
    owner_level = _LEVEL_ORDER.get(str(preference_owner.get("self_level")), 0)
    other_level = _LEVEL_ORDER.get(candidate_level, 0)
    if not owner_level or not other_level:
        return 50.0
    return _bounded(100 - abs(owner_level - other_level) * 16)


def _planning_score(
    preference_owner: Mapping[str, Any], candidate: Mapping[str, Any]
) -> float:
    style_score = _categorical_similarity(
        preference_owner.get("planning_style"),
        candidate.get("planning_style"),
        partial=68.0,
    )
    owner_role = preference_owner.get("organization_role")
    candidate_role = candidate.get("organization_role")
    if owner_role == "organizer" and candidate_role == "participant":
        role_score = 100.0
    elif owner_role == "participant" and candidate_role == "organizer":
        role_score = 100.0
    elif owner_role == candidate_role:
        role_score = 78.0
    elif "balanced" in {owner_role, candidate_role}:
        role_score = 88.0
    else:
        role_score = 70.0
    return _bounded(style_score * 0.65 + role_score * 0.35)


def _time_score(preference_owner: Mapping[str, Any], candidate: Mapping[str, Any]) -> float:
    best_window = best_common_time_window(preference_owner, candidate)
    if not best_window:
        return 0.0
    required_slots = max(1, int(preference_owner.get("min_session_minutes", 60)) // 30)
    duration_score = min(1.0, len(best_window) / required_slots) * 70
    overlap_score = _jaccard(
        list(preference_owner.get("available_times", [])),
        list(candidate.get("available_times", [])),
    ) * 30
    return _bounded(duration_score + overlap_score)


def directional_dimension_scores(
    preference_owner: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    text_score: float | None = None,
) -> dict[str, float]:
    """Calculate A -> B dimension scores before applying A's weights."""

    if text_score is None:
        text_score = bidirectional_text_scores(preference_owner, candidate)["a_to_b"]
    return {
        "time": _time_score(preference_owner, candidate),
        "goal": _categorical_similarity(
            preference_owner.get("goal"), candidate.get("goal"), partial=58.0
        ),
        "level": _level_score(preference_owner, candidate),
        "planning": _planning_score(preference_owner, candidate),
        "interest": _bounded(
            _jaccard(
                list(preference_owner.get("interests", [])),
                list(candidate.get("interests", [])),
            )
            * 100
        ),
        "communication": _categorical_similarity(
            preference_owner.get("communication_style"),
            candidate.get("communication_style"),
            partial=62.0,
        ),
        "text": _bounded(text_score),
    }


def directional_score(
    preference_owner: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    text_score: float | None = None,
) -> float:
    """Return A -> B weighted satisfaction using A's own weights."""

    dimensions = directional_dimension_scores(
        preference_owner, candidate, text_score=text_score
    )
    weights = preference_owner.get("preference_weights", {})
    total = sum(float(weights[dimension]) * dimensions[dimension] for dimension in dimensions)
    return _bounded(total)


__all__ = ["directional_dimension_scores", "directional_score"]
