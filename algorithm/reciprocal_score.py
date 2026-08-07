"""Bidirectional satisfaction aggregation for CampusMate matching."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai.text_similarity import bidirectional_text_scores

from .scoring import directional_dimension_scores, directional_score


def harmonic_mean(left: float, right: float) -> float:
    """Return the harmonic mean on a 0--100 scale."""

    left = float(left)
    right = float(right)
    if left <= 0 or right <= 0:
        return 0.0
    return round(2 * left * right / (left + right), 1)


def reciprocal_match_score(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> dict[str, Any]:
    """Return directional and mutual scores for a pair."""

    text_scores = bidirectional_text_scores(user_a, user_b)
    a_dimensions = directional_dimension_scores(
        user_a, user_b, text_score=text_scores["a_to_b"]
    )
    b_dimensions = directional_dimension_scores(
        user_b, user_a, text_score=text_scores["b_to_a"]
    )
    a_to_b = directional_score(user_a, user_b, text_score=text_scores["a_to_b"])
    b_to_a = directional_score(user_b, user_a, text_score=text_scores["b_to_a"])
    dimension_scores = {
        dimension: harmonic_mean(a_dimensions[dimension], b_dimensions[dimension])
        for dimension in a_dimensions
    }
    return {
        "a_to_b": a_to_b,
        "b_to_a": b_to_a,
        "score": harmonic_mean(a_to_b, b_to_a),
        "dimension_scores": dimension_scores,
        "text_scores": text_scores,
    }


__all__ = ["harmonic_mean", "reciprocal_match_score"]
