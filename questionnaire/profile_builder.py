"""Convert questionnaire answers into validated CampusMate profiles."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

from data import vocabulary as vocab
from data.schema import SCHEMA_VERSION, ensure_valid_profile, ordered_profile, validate_profile
from .questions import get_questions


BASE_PREFERENCE_WEIGHTS: Dict[str, float] = {
    "time": 0.25,
    "goal": 0.20,
    "level": 0.15,
    "planning": 0.15,
    "interest": 0.10,
    "communication": 0.10,
    "text": 0.05,
}


def _reverse(mapping: Mapping[Any, str]) -> Dict[str, Any]:
    return {label: code for code, label in mapping.items()}


def _normalise_choice(value: Any, mapping: Mapping[Any, str]) -> Any:
    try:
        if value in mapping:
            return value
    except TypeError:
        # Leave malformed unhashable values untouched so schema validation can
        # report the field instead of leaking a low-level Python exception.
        return value
    if isinstance(value, str):
        return _reverse(mapping).get(value, value.strip())
    return value


def _normalise_list(value: Any, mapping: Mapping[Any, str]) -> Any:
    if not isinstance(value, (list, tuple, set)):
        return value
    result: List[Any] = []
    for item in value:
        normalised = _normalise_choice(item, mapping)
        if normalised not in result:
            result.append(normalised)
    return result


def _normalise_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return " ".join(value.strip().split())


def _normalise_rating(value: Any) -> Any:
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def build_preference_weights(
    priorities: Optional[Iterable[str]] = None,
    explicit_weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Build normalized weights from priorities or an explicit mapping.

    Explicit weights take precedence. Otherwise each selected priority receives
    a 50% boost over the project baseline before all dimensions are normalized.
    """

    if explicit_weights is not None:
        try:
            raw = {
                key: float(explicit_weights.get(key, 0.0))
                for key in BASE_PREFERENCE_WEIGHTS
            }
        except (TypeError, ValueError):
            return dict(explicit_weights)
        if any(value < 0 for value in raw.values()):
            return raw
    else:
        raw = dict(BASE_PREFERENCE_WEIGHTS)
        selected = list(priorities or [])
        unknown = [key for key in selected if key not in raw]
        if unknown:
            invalid = dict(raw)
            invalid.update({str(key): 0.0 for key in unknown})
            return invalid
        for key in selected:
            if key in raw:
                raw[key] *= 1.5

    total = sum(raw.values())
    if total <= 0:
        return raw

    normalized = {key: value / total for key, value in raw.items()}
    # Make the serialized values stable and force the final key to absorb any
    # floating-point rounding drift so schema validation sees an exact sum.
    rounded = {key: round(value, 8) for key, value in normalized.items()}
    last_key = next(reversed(rounded))
    rounded[last_key] = round(
        rounded[last_key] + (1.0 - sum(rounded.values())), 8
    )
    return rounded


def build_profile(
    answers: Mapping[str, Any],
    *,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create one canonical, validated profile from raw questionnaire answers.

    Answers may contain canonical English codes or the Chinese labels exposed by
    ``get_questions``. Invalid input raises ``ProfileValidationError`` with
    structured issues available on ``error.result``.
    """

    if not isinstance(answers, Mapping):
        raise TypeError("answers必须是映射对象")

    match_type = _normalise_choice(answers.get("match_type"), vocab.MATCH_TYPES)
    activity_mapping = vocab.ACTIVITIES.get(match_type, {})
    goal_mapping = vocab.GOALS.get(match_type, {})

    locations = _normalise_list(
        answers.get("acceptable_locations"), vocab.LOCATIONS
    )
    if not isinstance(locations, list):
        locations_for_derived_value: List[str] = []
    else:
        locations_for_derived_value = locations

    explicit_weights = answers.get("preference_weights")
    priorities = _normalise_list(
        answers.get("preference_priorities", []), vocab.PREFERENCE_DIMENSIONS
    )

    profile: MutableMapping[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id or answers.get("user_id"),
        "match_type": match_type,
        "activity": _normalise_choice(answers.get("activity"), activity_mapping),
        "available_times": _normalise_list(
            answers.get("available_times"), vocab.TIME_SLOTS
        ),
        "min_session_minutes": _normalise_rating(
            answers.get("min_session_minutes", 60)
        ),
        "acceptable_locations": locations,
        "allow_off_campus": "off_campus_haidian" in locations_for_derived_value,
        "group_size_preference": _normalise_choice(
            answers.get("group_size_preference"), vocab.GROUP_SIZES
        ),
        "self_level": _normalise_choice(answers.get("self_level"), vocab.LEVELS),
        "acceptable_partner_levels": _normalise_list(
            answers.get("acceptable_partner_levels"), vocab.LEVELS
        ),
        "hard_restrictions": _normalise_list(
            answers.get("hard_restrictions", []), vocab.HARD_RESTRICTIONS
        ),
        "goal": _normalise_choice(answers.get("goal"), goal_mapping),
        "intensity": _normalise_rating(answers.get("intensity")),
        "communication_style": _normalise_choice(
            answers.get("communication_style"), vocab.COMMUNICATION_STYLES
        ),
        "planning_style": _normalise_choice(
            answers.get("planning_style"), vocab.PLANNING_STYLES
        ),
        "supervision_preference": _normalise_rating(
            answers.get("supervision_preference")
        ),
        "punctuality_importance": _normalise_rating(
            answers.get("punctuality_importance")
        ),
        "cancellation_tolerance": _normalise_rating(
            answers.get("cancellation_tolerance")
        ),
        "organization_role": _normalise_choice(
            answers.get("organization_role"), vocab.ORGANIZATION_ROLES
        ),
        "interests": _normalise_list(answers.get("interests"), vocab.INTEREST_TAGS),
        "self_description": _normalise_text(answers.get("self_description")),
        "partner_expectation": _normalise_text(answers.get("partner_expectation")),
        "preference_weights": build_preference_weights(
            priorities=priorities if isinstance(priorities, list) else [],
            explicit_weights=(
                explicit_weights if isinstance(explicit_weights, Mapping) else None
            ),
        ),
    }

    ensure_valid_profile(profile)
    return ordered_profile(profile)


__all__ = [
    "BASE_PREFERENCE_WEIGHTS",
    "build_preference_weights",
    "build_profile",
    "get_questions",
    "validate_profile",
]
