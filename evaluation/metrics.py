"""Metrics shared by CampusMate algorithm-comparison experiments."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def validate_pairing_integrity(matches: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return integrity violations without assuming a particular matcher."""

    if isinstance(matches, (str, bytes)) or not isinstance(matches, Sequence):
        raise TypeError("匹配结果必须是列表")
    problems: list[str] = []
    used_users: set[str] = set()
    for index, match in enumerate(matches, start=1):
        if not isinstance(match, Mapping):
            problems.append(f"第 {index} 条结果不是字典")
            continue
        user_a, user_b = str(match.get("user_a", "")), str(match.get("user_b", ""))
        if not user_a or not user_b or user_a == user_b:
            problems.append(f"第 {index} 条结果包含无效用户编号")
            continue
        repeated = {user_a, user_b} & used_users
        if repeated:
            problems.append(f"第 {index} 条结果重复匹配用户：{sorted(repeated)}")
        used_users.update({user_a, user_b})
        score = match.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
            problems.append(f"第 {index} 条结果的 score 不在 0—100 之间")
    return problems


def evaluate_matches(
    matches: Sequence[Mapping[str, Any]], *, participant_count: int
) -> dict[str, float | int]:
    """Summarize score, coverage and output-integrity metrics."""

    if isinstance(participant_count, bool) or not isinstance(participant_count, int) or participant_count < 0:
        raise ValueError("participant_count 必须是非负整数")
    problems = validate_pairing_integrity(matches)
    scores = [float(match["score"]) for match in matches if isinstance(match, Mapping) and isinstance(match.get("score"), (int, float)) and not isinstance(match.get("score"), bool) and 0 <= float(match["score"]) <= 100]
    pair_count = len(matches)
    return {
        "participant_count": participant_count,
        "pair_count": pair_count,
        "matched_users": min(participant_count, pair_count * 2),
        "match_rate": round(min(participant_count, pair_count * 2) / participant_count * 100, 1) if participant_count else 0.0,
        "average_match_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "lowest_match_score": round(min(scores), 2) if scores else 0.0,
        "integrity_violation_count": len(problems),
        "integrity_passed": int(not problems),
    }


__all__ = ["evaluate_matches", "validate_pairing_integrity"]
