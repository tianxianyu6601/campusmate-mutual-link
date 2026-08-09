"""Versioned CampusMate user-profile schema and validation.

The public interchange format is a plain ``dict`` so Streamlit, NetworkX, and
LLM-authored modules can consume it without depending on a model framework.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from . import vocabulary as vocab


SCHEMA_VERSION = "1.0.0"

FIELD_ORDER: Tuple[str, ...] = (
    "schema_version",
    "user_id",
    "match_type",
    "activity",
    "available_times",
    "min_session_minutes",
    "acceptable_locations",
    "allow_off_campus",
    "group_size_preference",
    "self_level",
    "acceptable_partner_levels",
    "hard_restrictions",
    "goal",
    "intensity",
    "communication_style",
    "planning_style",
    "supervision_preference",
    "punctuality_importance",
    "cancellation_tolerance",
    "organization_role",
    "interests",
    "self_description",
    "partner_expectation",
    "preference_weights",
)

JSON_FIELDS = frozenset(
    {
        "available_times",
        "acceptable_locations",
        "acceptable_partner_levels",
        "hard_restrictions",
        "interests",
        "preference_weights",
    }
)
INTEGER_FIELDS = frozenset(
    {
        "min_session_minutes",
        "intensity",
        "supervision_preference",
        "punctuality_importance",
        "cancellation_tolerance",
    }
)
BOOLEAN_FIELDS = frozenset({"allow_off_campus"})

SENSITIVE_FIELDS = frozenset(
    {
        "name",
        "real_name",
        "phone",
        "phone_number",
        "wechat",
        "wechat_id",
        "dormitory",
        "dorm_room",
        "photo",
        "income",
        "family_background",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    code: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class ValidationResult:
    issues: Tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def as_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class ProfileValidationError(ValueError):
    """Raised when a profile does not satisfy schema v1."""

    def __init__(self, result: ValidationResult):
        self.result = result
        detail = "; ".join(
            f"{issue.field}: {issue.message}" for issue in result.issues
        )
        super().__init__(detail or "用户画像校验失败")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_string_list(
    profile: Mapping[str, Any],
    field: str,
    issues: List[ValidationIssue],
    *,
    allowed: Iterable[str] | None = None,
    required: bool = True,
    allow_custom: bool = False,
) -> None:
    value = profile.get(field)
    if not isinstance(value, list):
        issues.append(ValidationIssue(field, "invalid_type", "必须是列表"))
        return
    if required and not value:
        issues.append(ValidationIssue(field, "empty_list", "至少选择一项"))
        return
    if any(not isinstance(item, str) or not item for item in value):
        issues.append(ValidationIssue(field, "invalid_item", "列表项必须是非空字符串"))
    if len(value) != len(set(value)):
        issues.append(ValidationIssue(field, "duplicate_item", "列表中不能有重复项"))
    if allowed is not None:
        allowed_set = set(allowed)
        unknown = sorted(
            item
            for item in set(value)
            if item not in allowed_set
            and not (allow_custom and vocab.is_custom_value(item))
        )
        if unknown:
            issues.append(
                ValidationIssue(field, "unknown_value", f"包含未知值：{unknown}")
            )


def _validate_rating(
    profile: Mapping[str, Any], field: str, issues: List[ValidationIssue]
) -> None:
    value = profile.get(field)
    if not _is_int(value) or not 1 <= value <= 5:
        issues.append(ValidationIssue(field, "out_of_range", "必须是1—5的整数"))


def validate_profile(profile: Mapping[str, Any], *, strict: bool = True) -> ValidationResult:
    """Validate one profile against the stable v1 contract.

    ``strict=True`` rejects unknown fields, which is recommended for persisted
    datasets. Interactive callers may use ``strict=False`` during migration.
    """

    issues: List[ValidationIssue] = []
    if not isinstance(profile, Mapping):
        return ValidationResult(
            (ValidationIssue("profile", "invalid_type", "用户画像必须是映射对象"),)
        )

    missing = [field for field in FIELD_ORDER if field not in profile]
    for field in missing:
        issues.append(ValidationIssue(field, "missing", "缺少必填字段"))

    sensitive = sorted(set(profile) & SENSITIVE_FIELDS)
    for field in sensitive:
        issues.append(ValidationIssue(field, "sensitive_field", "不得保存敏感个人信息"))

    if strict:
        unknown = sorted(set(profile) - set(FIELD_ORDER))
        for field in unknown:
            issues.append(
                ValidationIssue(
                    field,
                    "unknown_field",
                    f"字段不属于Schema {SCHEMA_VERSION}",
                )
            )

    if profile.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                "schema_version",
                "unsupported_version",
                f"必须为{SCHEMA_VERSION}",
            )
        )

    user_id = profile.get("user_id")
    if not isinstance(user_id, str) or not re.fullmatch(r"U\d{4}", user_id):
        issues.append(
            ValidationIssue("user_id", "invalid_format", "必须符合U0001格式")
        )

    match_type = profile.get("match_type")
    if match_type not in vocab.MATCH_TYPES:
        issues.append(
            ValidationIssue("match_type", "unknown_value", "必须是study、sport或interest")
        )

    activity = profile.get("activity")
    if isinstance(match_type, str) and not vocab.activity_belongs_to(match_type, activity):
        issues.append(
            ValidationIssue("activity", "category_mismatch", "活动不属于所选匹配类型")
        )

    _validate_string_list(
        profile,
        "available_times",
        issues,
        allowed=vocab.TIME_SLOTS,
    )

    min_session = profile.get("min_session_minutes")
    if (
        not _is_int(min_session)
        or min_session < 30
        or min_session > 240
        or min_session % 30 != 0
    ):
        issues.append(
            ValidationIssue(
                "min_session_minutes",
                "invalid_duration",
                "必须是30—240之间且为30倍数的整数",
            )
        )

    _validate_string_list(
        profile,
        "acceptable_locations",
        issues,
        allowed=vocab.LOCATIONS,
        allow_custom=True,
    )
    allow_off_campus = profile.get("allow_off_campus")
    if not isinstance(allow_off_campus, bool):
        issues.append(
            ValidationIssue("allow_off_campus", "invalid_type", "必须是布尔值")
        )
    locations = profile.get("acceptable_locations")
    if isinstance(locations, list) and isinstance(allow_off_campus, bool):
        expected = any(vocab.is_off_campus_location(item) for item in locations)
        if allow_off_campus != expected:
            issues.append(
                ValidationIssue(
                    "allow_off_campus",
                    "derived_value_mismatch",
                    "必须与acceptable_locations中的校外地点保持一致",
                )
            )

    if profile.get("group_size_preference") not in vocab.GROUP_SIZES:
        issues.append(
            ValidationIssue("group_size_preference", "unknown_value", "未知人数偏好")
        )
    if profile.get("self_level") not in vocab.LEVELS:
        issues.append(ValidationIssue("self_level", "unknown_value", "未知活动水平"))
    _validate_string_list(
        profile,
        "acceptable_partner_levels",
        issues,
        allowed=vocab.LEVELS,
    )
    _validate_string_list(
        profile,
        "hard_restrictions",
        issues,
        allowed=vocab.HARD_RESTRICTIONS,
        required=False,
    )

    goal = profile.get("goal")
    if isinstance(match_type, str) and not vocab.goal_belongs_to(match_type, goal):
        issues.append(
            ValidationIssue("goal", "category_mismatch", "目标不属于所选匹配类型")
        )

    for field in (
        "intensity",
        "supervision_preference",
        "punctuality_importance",
        "cancellation_tolerance",
    ):
        _validate_rating(profile, field, issues)

    if profile.get("communication_style") not in vocab.COMMUNICATION_STYLES:
        issues.append(
            ValidationIssue("communication_style", "unknown_value", "未知交流方式")
        )
    if profile.get("planning_style") not in vocab.PLANNING_STYLES:
        issues.append(ValidationIssue("planning_style", "unknown_value", "未知规划方式"))
    if profile.get("organization_role") not in vocab.ORGANIZATION_ROLES:
        issues.append(ValidationIssue("organization_role", "unknown_value", "未知组织角色"))

    _validate_string_list(
        profile,
        "interests",
        issues,
        allowed=vocab.INTEREST_TAGS,
        allow_custom=True,
    )

    for field in ("self_description", "partner_expectation"):
        value = profile.get(field)
        if not isinstance(value, str):
            issues.append(ValidationIssue(field, "invalid_type", "必须是字符串"))
        elif len(value.strip()) < 5:
            issues.append(ValidationIssue(field, "too_short", "至少填写5个字符"))
        elif len(value) > 500:
            issues.append(ValidationIssue(field, "too_long", "不能超过500个字符"))

    weights = profile.get("preference_weights")
    if not isinstance(weights, dict):
        issues.append(
            ValidationIssue("preference_weights", "invalid_type", "必须是字典")
        )
    else:
        expected_keys = set(vocab.PREFERENCE_DIMENSIONS)
        if set(weights) != expected_keys:
            issues.append(
                ValidationIssue(
                    "preference_weights",
                    "invalid_keys",
                    f"必须且只能包含：{sorted(expected_keys)}",
                )
            )
        numeric_values: List[float] = []
        for key, value in weights.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                issues.append(
                    ValidationIssue(
                        "preference_weights", "invalid_weight", f"{key}的权重必须是数字"
                    )
                )
            elif not math.isfinite(float(value)) or value < 0:
                issues.append(
                    ValidationIssue(
                        "preference_weights", "invalid_weight", f"{key}的权重必须非负且有限"
                    )
                )
            else:
                numeric_values.append(float(value))
        if numeric_values and not math.isclose(sum(numeric_values), 1.0, abs_tol=1e-6):
            issues.append(
                ValidationIssue(
                    "preference_weights", "invalid_sum", "全部权重之和必须为1"
                )
            )

    return ValidationResult(tuple(issues))


def ensure_valid_profile(profile: Mapping[str, Any], *, strict: bool = True) -> None:
    result = validate_profile(profile, strict=strict)
    if not result.is_valid:
        raise ProfileValidationError(result)


def ordered_profile(profile: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a validated profile with canonical field order."""

    ensure_valid_profile(profile)
    return {field: profile[field] for field in FIELD_ORDER}
