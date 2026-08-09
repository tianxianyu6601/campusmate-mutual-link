"""Generate privacy-conscious icebreaker prompts from common profile fields."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from data import vocabulary as vocab


def generate_icebreakers(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any], *, limit: int = 3
) -> list[str]:
    """Return safe first-message prompts without exposing personal information."""

    if limit < 1:
        raise ValueError("问题数量至少为 1")
    prompts: list[str] = []
    activity_value = str(user_a.get("activity"))
    activity = vocab.display_value(
        activity_value,
        vocab.ACTIVITIES.get(str(user_a.get("match_type")), {}),
    )
    activity = activity or "这项活动"
    prompts.append(f"这周做“{activity}”时，你最希望先完成哪一个小目标？")

    common_interests = sorted(set(user_a.get("interests", [])) & set(user_b.get("interests", [])))
    if common_interests:
        interest = vocab.display_value(common_interests[0], vocab.INTEREST_TAGS)
        prompts.append(f"我们都对“{interest}”感兴趣，你最近有没有想分享的内容？")

    planning = user_a.get("planning_style")
    if planning == user_b.get("planning_style"):
        label = vocab.PLANNING_STYLES.get(str(planning), "安排方式")
        prompts.append(f"我们都偏好“{label}”，要不要先把本周的时间简单定下来？")
    else:
        prompts.append("为了让这次活动更轻松，你希望提前确定哪些细节？")

    prompts.append("第一次一起行动时，怎样的节奏会让你最舒服？")
    return prompts[:limit]


__all__ = ["generate_icebreakers"]
