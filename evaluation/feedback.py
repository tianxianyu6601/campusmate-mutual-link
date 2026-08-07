"""Anonymous post-match feedback validation and aggregation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


FEEDBACK_FIELDS = ("match_score", "explanation_helpfulness", "would_meet_again")


def build_feedback(
    *,
    match_id: str,
    match_score: int,
    explanation_helpfulness: int,
    would_meet_again: bool,
    comment: str = "",
) -> dict[str, Any]:
    """Validate and create one anonymous feedback record.

    The record contains no contact details or free-form personal profile data.
    """

    if not isinstance(match_id, str) or not match_id.strip():
        raise ValueError("match_id 必须是非空字符串")
    for field, value in (
        ("match_score", match_score),
        ("explanation_helpfulness", explanation_helpfulness),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise ValueError(f"{field} 必须是 1—5 的整数")
    if not isinstance(would_meet_again, bool):
        raise ValueError("would_meet_again 必须是布尔值")
    if not isinstance(comment, str) or len(comment) > 300:
        raise ValueError("comment 必须是不超过 300 字的文本")
    return {
        "match_id": match_id.strip(),
        "match_score": match_score,
        "explanation_helpfulness": explanation_helpfulness,
        "would_meet_again": would_meet_again,
        "comment": comment.strip(),
    }


def summarize_feedback(records: Sequence[Mapping[str, Any]]) -> dict[str, float | int]:
    """Calculate presentation-ready aggregate feedback metrics."""

    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError("反馈记录必须是列表")
    valid_records = [build_feedback(**dict(record)) for record in records]
    count = len(valid_records)
    if not count:
        return {
            "response_count": 0,
            "average_match_score": 0.0,
            "average_explanation_helpfulness": 0.0,
            "meet_again_rate": 0.0,
        }
    return {
        "response_count": count,
        "average_match_score": round(sum(item["match_score"] for item in valid_records) / count, 2),
        "average_explanation_helpfulness": round(
            sum(item["explanation_helpfulness"] for item in valid_records) / count, 2
        ),
        "meet_again_rate": round(
            sum(item["would_meet_again"] for item in valid_records) / count * 100, 1
        ),
    }


__all__ = ["FEEDBACK_FIELDS", "build_feedback", "summarize_feedback"]
