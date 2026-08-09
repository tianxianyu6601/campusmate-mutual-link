"""Hard-constraint filtering for one-to-one CampusMate matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from data import vocabulary as vocab


_SLOT_RE = re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)_(\d{2})_(\d{2})$")
_DAY_INDEX = {code: index for index, (code, _label) in enumerate(vocab.WEEKDAYS)}


@dataclass(frozen=True)
class HardFilterResult:
    """Result of checking whether two profiles can be considered further."""

    passed: bool
    reasons: tuple[str, ...] = ()
    common_times: tuple[str, ...] = ()
    common_locations: tuple[str, ...] = ()


def slot_start_minutes(slot: str) -> int:
    """Return an absolute minute offset within a week for a 30-minute slot."""

    match = _SLOT_RE.fullmatch(slot)
    if not match:
        raise ValueError(f"无效时间片编码：{slot}")
    day, hour, minute = match.groups()
    return _DAY_INDEX[day] * 24 * 60 + int(hour) * 60 + int(minute)


def _slot_hour(slot: str) -> int:
    match = _SLOT_RE.fullmatch(slot)
    if not match:
        raise ValueError(f"无效时间片编码：{slot}")
    return int(match.group(2))


def _restrictions(user_a: Mapping[str, Any], user_b: Mapping[str, Any]) -> set[str]:
    return set(user_a.get("hard_restrictions", [])) | set(
        user_b.get("hard_restrictions", [])
    )


def _filtered_common_slots(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> list[str]:
    common = set(user_a.get("available_times", [])) & set(
        user_b.get("available_times", [])
    )
    restrictions = _restrictions(user_a, user_b)
    if "no_evening" in restrictions:
        common = {slot for slot in common if _slot_hour(slot) < 18}
    if "no_early_morning" in restrictions:
        common = {slot for slot in common if _slot_hour(slot) >= 9}
    return sorted(common, key=slot_start_minutes)


def common_time_windows(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> list[tuple[str, ...]]:
    """Return continuous common 30-minute windows after time restrictions."""

    slots = _filtered_common_slots(user_a, user_b)
    if not slots:
        return []

    windows: list[list[str]] = [[slots[0]]]
    previous = slot_start_minutes(slots[0])
    for slot in slots[1:]:
        current = slot_start_minutes(slot)
        if current - previous == 30:
            windows[-1].append(slot)
        else:
            windows.append([slot])
        previous = current
    return [tuple(window) for window in windows]


def best_common_time_window(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> tuple[str, ...]:
    """Return the longest continuous common window."""

    windows = common_time_windows(user_a, user_b)
    if not windows:
        return ()
    return max(windows, key=lambda window: (len(window), -slot_start_minutes(window[0])))


def common_locations(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> tuple[str, ...]:
    """Return mutually acceptable locations after location restrictions."""

    left_locations = {
        vocab.comparison_key(value): str(value)
        for value in user_a.get("acceptable_locations", [])
        if vocab.comparison_key(value)
    }
    right_keys = {
        vocab.comparison_key(value)
        for value in user_b.get("acceptable_locations", [])
        if vocab.comparison_key(value)
    }
    locations = {
        value
        for key, value in left_locations.items()
        if key in right_keys
    }
    if "no_off_campus" in _restrictions(user_a, user_b):
        locations = {
            value
            for value in locations
            if not vocab.is_off_campus_location(value)
        }
    return tuple(sorted(locations, key=vocab.comparison_key))


def _level_compatible(user_a: Mapping[str, Any], user_b: Mapping[str, Any]) -> bool:
    return (
        user_b.get("self_level") in set(user_a.get("acceptable_partner_levels", []))
        and user_a.get("self_level")
        in set(user_b.get("acceptable_partner_levels", []))
    )


def _one_to_one_compatible(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> bool:
    preferences = {
        str(user_a.get("group_size_preference", "")),
        str(user_b.get("group_size_preference", "")),
    }
    if "small_group" in preferences:
        return False
    if "no_group_activity" in _restrictions(user_a, user_b):
        return True
    return preferences <= {"one_to_one", "either"}


def _hard_restrictions_compatible(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> tuple[bool, str | None]:
    restrictions = _restrictions(user_a, user_b)
    if "no_high_intensity" in restrictions and max(
        int(user_a.get("intensity", 0)), int(user_b.get("intensity", 0))
    ) >= 4:
        return False, "不接受高强度活动"
    if (
        "no_last_minute_cancel" in set(user_a.get("hard_restrictions", []))
        and int(user_b.get("cancellation_tolerance", 0)) >= 4
    ) or (
        "no_last_minute_cancel" in set(user_b.get("hard_restrictions", []))
        and int(user_a.get("cancellation_tolerance", 0)) >= 4
    ):
        return False, "不接受临时取消习惯冲突"
    return True, None


def pass_hard_constraints(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any]
) -> HardFilterResult:
    """Check all non-negotiable constraints before scoring a pair."""

    reasons: list[str] = []
    if user_a.get("user_id") == user_b.get("user_id"):
        reasons.append("不能与自己匹配")
    if user_a.get("match_type") != user_b.get("match_type"):
        reasons.append("搭子类型不同")
    if vocab.comparison_key(user_a.get("activity")) != vocab.comparison_key(
        user_b.get("activity")
    ):
        reasons.append("活动项目不同")

    required_minutes = max(
        int(user_a.get("min_session_minutes", 60)),
        int(user_b.get("min_session_minutes", 60)),
    )
    best_window = best_common_time_window(user_a, user_b)
    if len(best_window) * 30 < required_minutes:
        reasons.append("没有满足最短时长的连续共同时间")

    locations = common_locations(user_a, user_b)
    if not locations:
        reasons.append("没有双方都能接受的地点")

    if not _level_compatible(user_a, user_b):
        reasons.append("活动水平不在双方可接受范围内")
    if not _one_to_one_compatible(user_a, user_b):
        reasons.append("人数偏好不适合一对一匹配")

    restrictions_ok, restriction_reason = _hard_restrictions_compatible(user_a, user_b)
    if not restrictions_ok and restriction_reason:
        reasons.append(restriction_reason)

    return HardFilterResult(
        passed=not reasons,
        reasons=tuple(reasons),
        common_times=best_window if not reasons else (),
        common_locations=locations if not reasons else (),
    )


__all__ = [
    "HardFilterResult",
    "best_common_time_window",
    "common_locations",
    "common_time_windows",
    "pass_hard_constraints",
    "slot_start_minutes",
]
