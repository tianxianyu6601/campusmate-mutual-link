"""Transactional service layer for profiles, activities, and match rounds.

The Streamlit pages should call these functions instead of writing SQL directly.
This keeps authorization, capacity, idempotency, email-task, and audit rules in
one place for both local SQLite and hosted PostgreSQL.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

from services.auth import AuthError, normalize_email
from services.database import (
    DEFAULT_SQLITE_PATH,
    DatabaseConnection,
    is_integrity_error,
    transaction,
)
from services.migrations import ensure_migrations


DB_PATH = DEFAULT_SQLITE_PATH
PROFILE_COLUMNS = (
    "display_name",
    "avatar_data_url",
    "school",
    "department",
    "grade",
    "identity_label",
    "bio",
    "mbti",
    "introversion",
    "planning_style",
    "warm_up_level",
    "group_size_preference",
    "self_description",
    "partner_expectation",
    "contact_email",
    "contact_qq",
    "contact_wechat",
    "available_times_json",
    "preferred_locations_json",
    "max_distance_km",
    "allow_cross_school",
    "completion_percent",
)
INTEREST_CATEGORIES = {
    "study",
    "sport",
    "social",
    "entertainment",
    "travel",
    "share",
    "custom",
}
ALLOWED_VISIBILITIES = {"private", "matched", "activity_members", "public"}
PROFILE_PRIVACY_FIELDS = {
    "avatar_data_url",
    "school",
    "department",
    "grade",
    "identity_label",
    "bio",
    "interests",
    "personality",
    "available_times",
    "preferred_locations",
    "self_description",
    "partner_expectation",
    "contact_email",
    "contact_qq",
    "contact_wechat",
}
PROFILE_FIELD_PRIVACY_KEY = {
    "avatar_data_url": "avatar_data_url",
    "school": "school",
    "department": "department",
    "grade": "grade",
    "identity_label": "identity_label",
    "bio": "bio",
    "interests": "interests",
    "mbti": "personality",
    "introversion": "personality",
    "planning_style": "personality",
    "warm_up_level": "personality",
    "group_size_preference": "personality",
    "available_times": "available_times",
    "preferred_locations": "preferred_locations",
    "max_distance_km": "preferred_locations",
    "allow_cross_school": "preferred_locations",
    "self_description": "self_description",
    "partner_expectation": "partner_expectation",
    "contact_email": "contact_email",
    "contact_qq": "contact_qq",
    "contact_wechat": "contact_wechat",
}
MATCHING_REQUIRED_FIELDS = (
    ("display_name", "昵称"),
    ("school", "学校"),
    ("interests", "至少一个兴趣标签"),
    ("available_times", "至少一个空闲时间"),
    ("preferred_locations", "至少一个常用地点"),
    ("self_description", "我是什么样的人"),
    ("partner_expectation", "我想找什么样的人"),
)
MBTI_TYPES = {
    "",
    "INTJ",
    "INTP",
    "ENTJ",
    "ENTP",
    "INFJ",
    "INFP",
    "ENFJ",
    "ENFP",
    "ISTJ",
    "ISFJ",
    "ESTJ",
    "ESFJ",
    "ISTP",
    "ISFP",
    "ESTP",
    "ESFP",
}
AVATAR_DATA_URL_RE = re.compile(
    r"^data:image/(?P<subtype>png|jpeg|webp);base64,(?P<payload>[A-Za-z0-9+/=]+)$"
)
MAX_AVATAR_BYTES = 750_000
ACTIVITY_CATEGORIES = {
    "study",
    "sport",
    "social",
    "entertainment",
    "travel",
    "share",
    "custom",
}
ACTIVITY_VISIBILITIES = {"campus", "public", "invite"}
ACTIVITY_STATUSES = {"draft", "published", "full", "ended", "cancelled"}
ACTIVITY_IMAGE_DATA_URL_RE = re.compile(
    r"^data:image/(?P<subtype>png|jpeg|webp);base64,(?P<payload>[A-Za-z0-9+/=]+)$"
)
MAX_ACTIVITY_IMAGE_BYTES = 1_000_000


class ServiceError(RuntimeError):
    """Base class for expected business-rule failures."""


class ValidationError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class PermissionDenied(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


class CapacityError(ConflictError):
    pass


def _now() -> int:
    return int(time.time())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _clean_string_list(value: Any, *, maximum: int, field_label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValidationError(f"{field_label}必须是选项列表")
    cleaned: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if len(cleaned) > maximum:
        raise ValidationError(f"{field_label}最多选择 {maximum} 项")
    if any(len(item) > 40 for item in cleaned):
        raise ValidationError(f"{field_label}的单项长度不能超过 40 个字符")
    return cleaned


def _normalize_interests(
    interests: Iterable[tuple[str, str]],
) -> set[tuple[str, str]]:
    normalized: set[tuple[str, str]] = set()
    for category, tag in interests:
        clean_category = str(category).strip()
        clean_tag = str(tag).strip()
        if clean_category not in INTEREST_CATEGORIES:
            raise ValidationError("兴趣分类无效")
        if not 1 <= len(clean_tag) <= 40:
            raise ValidationError("兴趣标签长度必须为 1 到 40 个字符")
        normalized.add((clean_category, clean_tag))
    if len(normalized) > 50:
        raise ValidationError("兴趣标签最多保存 50 个")
    return normalized


def _validate_avatar_data_url(value: str) -> str:
    avatar = value.strip()
    if not avatar:
        return ""
    match = AVATAR_DATA_URL_RE.fullmatch(avatar)
    if match is None:
        raise ValidationError("头像仅支持 PNG、JPEG 或 WebP 图片")
    try:
        decoded = base64.b64decode(match.group("payload"), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValidationError("头像数据无效") from error
    if not decoded or len(decoded) > MAX_AVATAR_BYTES:
        raise ValidationError("头像文件不能超过 750 KB")
    subtype = match.group("subtype")
    valid_signature = (
        subtype == "png" and decoded.startswith(b"\x89PNG\r\n\x1a\n")
    ) or (
        subtype == "jpeg" and decoded.startswith(b"\xff\xd8\xff")
    ) or (
        subtype == "webp"
        and len(decoded) >= 12
        and decoded.startswith(b"RIFF")
        and decoded[8:12] == b"WEBP"
    )
    if not valid_signature:
        raise ValidationError("头像文件内容与图片格式不一致")
    return avatar


def _validate_activity_image(value: str) -> str:
    image = value.strip()
    if not image:
        return ""
    match = ACTIVITY_IMAGE_DATA_URL_RE.fullmatch(image)
    if match is None:
        raise ValidationError("活动图片仅支持 PNG、JPEG 或 WebP")
    try:
        decoded = base64.b64decode(match.group("payload"), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValidationError("活动图片数据无效") from error
    if not decoded or len(decoded) > MAX_ACTIVITY_IMAGE_BYTES:
        raise ValidationError("活动图片不能超过 1 MB")
    subtype = match.group("subtype")
    valid_signature = (
        subtype == "png" and decoded.startswith(b"\x89PNG\r\n\x1a\n")
    ) or (
        subtype == "jpeg" and decoded.startswith(b"\xff\xd8\xff")
    ) or (
        subtype == "webp"
        and len(decoded) >= 12
        and decoded.startswith(b"RIFF")
        and decoded[8:12] == b"WEBP"
    )
    if not valid_signature:
        raise ValidationError("活动图片内容与文件格式不一致")
    return image


def _validate_activity_fields(
    *,
    category: str,
    custom_category: str,
    title: str,
    description: str,
    image_url: str,
    starts_at: int,
    ends_at: int | None,
    location_text: str,
    capacity: int,
    visibility: str,
    status: str,
) -> dict[str, Any]:
    clean_category = str(category).strip()
    clean_custom = str(custom_category).strip()
    clean_title = str(title).strip()
    clean_description = str(description).strip()
    clean_location = str(location_text).strip()
    clean_visibility = str(visibility).strip()
    clean_status = str(status).strip()
    start = int(starts_at)
    end = int(ends_at) if ends_at is not None else None
    clean_capacity = int(capacity)

    if clean_category not in ACTIVITY_CATEGORIES:
        raise ValidationError("活动分类无效")
    if clean_category == "custom" and not 1 <= len(clean_custom) <= 40:
        raise ValidationError("自定义分类长度必须为 1 到 40 个字符")
    if clean_category != "custom":
        clean_custom = ""
    if not 1 <= len(clean_title) <= 60:
        raise ValidationError("活动标题长度必须为 1 到 60 个字符")
    if len(clean_description) > 3000:
        raise ValidationError("活动描述不能超过 3000 个字符")
    if not 1 <= len(clean_location) <= 200:
        raise ValidationError("活动地点长度必须为 1 到 200 个字符")
    if not 2 <= clean_capacity <= 100:
        raise ValidationError("活动人数必须在 2 到 100 人之间（含发起人）")
    if end is not None and end <= start:
        raise ValidationError("活动结束时间必须晚于开始时间")
    if clean_visibility not in ACTIVITY_VISIBILITIES:
        raise ValidationError("活动可见范围无效")
    if clean_status not in {"draft", "published"}:
        raise ValidationError("新建或编辑活动只能保存为草稿或发布状态")
    if clean_status == "published" and start < _now() - 60:
        raise ValidationError("发布活动的开始时间不能早于当前时间")

    return {
        "category": clean_category,
        "custom_category": clean_custom,
        "title": clean_title,
        "description": clean_description,
        "image_url": _validate_activity_image(str(image_url)),
        "starts_at": start,
        "ends_at": end,
        "location_text": clean_location,
        "capacity": clean_capacity,
        "visibility": clean_visibility,
        "status": clean_status,
    }


def matching_profile_missing_fields(
    profile: Mapping[str, Any] | None,
    interests: Iterable[Mapping[str, Any] | tuple[str, str]] = (),
) -> list[str]:
    """Return user-facing missing fields required before periodic matching."""

    if profile is None:
        return [label for _, label in MATCHING_REQUIRED_FIELDS]
    interest_list = list(interests)
    missing: list[str] = []
    for field_name, label in MATCHING_REQUIRED_FIELDS:
        if field_name == "interests":
            present = bool(interest_list)
        else:
            present = bool(profile.get(field_name))
        if not present:
            missing.append(label)
    return missing


def calculate_profile_completion(
    profile: Mapping[str, Any],
    interests: Iterable[Mapping[str, Any] | tuple[str, str]] = (),
) -> int:
    """Calculate completion server-side; clients cannot submit their own score."""

    checks = (
        bool(profile.get("display_name")),
        bool(profile.get("school")),
        bool(profile.get("department")),
        bool(profile.get("identity_label")),
        bool(profile.get("bio")),
        bool(list(interests)),
        bool(profile.get("available_times")),
        bool(profile.get("preferred_locations")),
        bool(profile.get("self_description")),
        bool(profile.get("partner_expectation")),
    )
    return round(100 * sum(checks) / len(checks))


def _prepare_database(path: Path | None = None) -> Path:
    selected_path = Path(path or DB_PATH)
    ensure_migrations(selected_path)
    return selected_path


def _require_user(connection: DatabaseConnection, email: str) -> str:
    normalized = normalize_email(email)
    row = connection.execute(
        "SELECT 1 FROM users WHERE email = ? AND verified = 1", (normalized,)
    ).fetchone()
    if row is None:
        raise NotFoundError("账号不存在或尚未验证")
    return normalized


def _audit(
    connection: DatabaseConnection,
    *,
    actor_email: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_log(
            audit_id, actor_email, action, entity_type, entity_id,
            details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id("audit"),
            actor_email,
            action,
            entity_type,
            entity_id,
            _json(dict(details or {})),
            _now(),
        ),
    )


def _enqueue_email_task(
    connection: DatabaseConnection,
    *,
    recipient_email: str,
    template_key: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
) -> str:
    existing = connection.execute(
        "SELECT task_id FROM email_tasks WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return str(existing["task_id"])
    task_id = _new_id("mail")
    now = _now()
    connection.execute(
        """
        INSERT INTO email_tasks(
            task_id, recipient_email, template_key, payload_json, status,
            idempotency_key, attempts, max_attempts, last_error,
            next_attempt_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'queued', ?, 0, 5, '', ?, ?, ?)
        """,
        (
            task_id,
            normalize_email(recipient_email),
            template_key,
            _json(dict(payload)),
            idempotency_key,
            now,
            now,
            now,
        ),
    )
    return task_id


def _display_name(connection: DatabaseConnection, email: str) -> str:
    row = connection.execute(
        "SELECT display_name FROM profiles WHERE email = ?", (email,)
    ).fetchone()
    if row and str(row["display_name"]).strip():
        return str(row["display_name"]).strip()
    return "校园用户"


def _enqueue_notification(
    connection: DatabaseConnection,
    *,
    recipient_email: str,
    notification_type: str,
    title: str,
    message: str,
    entity_type: str,
    entity_id: str,
    idempotency_key: str,
) -> str:
    existing = connection.execute(
        "SELECT notification_id FROM user_notifications WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return str(existing["notification_id"])
    notification_id = _new_id("notification")
    connection.execute(
        """
        INSERT INTO user_notifications(
            notification_id, recipient_email, notification_type, title,
            message, entity_type, entity_id, is_read, idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            notification_id,
            normalize_email(recipient_email),
            str(notification_type),
            str(title)[:120],
            str(message)[:1000],
            str(entity_type),
            str(entity_id),
            str(idempotency_key),
            _now(),
        ),
    )
    return notification_id


def upsert_profile(
    email: str,
    profile: Mapping[str, Any],
    *,
    interests: Iterable[tuple[str, str]] = (),
    privacy: Mapping[str, str] | None = None,
    sqlite_path: Path | None = None,
) -> None:
    """Create or replace a user's normalized profile in one transaction."""

    path = _prepare_database(sqlite_path)
    display_name = str(profile.get("display_name", "")).strip()
    if not 1 <= len(display_name) <= 30:
        raise ValidationError("昵称长度必须为 1 到 30 个字符")

    available_times = _clean_string_list(
        profile.get("available_times", []), maximum=30, field_label="空闲时间"
    )
    preferred_locations = _clean_string_list(
        profile.get("preferred_locations", []), maximum=20, field_label="常用地点"
    )
    normalized_interests = _normalize_interests(interests)
    avatar_data_url = _validate_avatar_data_url(
        str(profile.get("avatar_data_url", ""))
    )
    contact_email = str(profile.get("contact_email", "")).strip()
    if contact_email:
        try:
            contact_email = normalize_email(contact_email)
        except AuthError as error:
            raise ValidationError("联系邮箱格式无效") from error

    values: dict[str, Any] = {
        "display_name": display_name,
        "avatar_data_url": avatar_data_url,
        "school": str(profile.get("school", "北京大学")).strip() or "北京大学",
        "department": str(profile.get("department", "")).strip(),
        "grade": str(profile.get("grade", "")).strip(),
        "identity_label": str(profile.get("identity_label", "")).strip(),
        "bio": str(profile.get("bio", "")).strip(),
        "mbti": str(profile.get("mbti", "")).strip().upper(),
        "introversion": int(profile.get("introversion", 3)),
        "planning_style": str(profile.get("planning_style", "flexible")).strip(),
        "warm_up_level": int(profile.get("warm_up_level", 3)),
        "group_size_preference": str(profile.get("group_size_preference", "any")),
        "self_description": str(profile.get("self_description", "")).strip(),
        "partner_expectation": str(profile.get("partner_expectation", "")).strip(),
        "contact_email": contact_email,
        "contact_qq": str(profile.get("contact_qq", "")).strip(),
        "contact_wechat": str(profile.get("contact_wechat", "")).strip(),
        "available_times_json": _json(available_times),
        "preferred_locations_json": _json(preferred_locations),
        "max_distance_km": int(profile.get("max_distance_km", 5)),
        "allow_cross_school": int(bool(profile.get("allow_cross_school", False))),
        "completion_percent": 0,
    }
    profile_for_completion = {
        **values,
        "available_times": available_times,
        "preferred_locations": preferred_locations,
    }
    values["completion_percent"] = calculate_profile_completion(
        profile_for_completion, normalized_interests
    )
    if not 1 <= values["introversion"] <= 5 or not 1 <= values["warm_up_level"] <= 5:
        raise ValidationError("性格量表必须在 1 到 5 之间")
    if values["mbti"] not in MBTI_TYPES:
        raise ValidationError("MBTI 类型无效")
    if values["planning_style"] not in {"flexible", "balanced", "planned"}:
        raise ValidationError("计划方式无效")
    if values["group_size_preference"] not in {
        "one_to_one",
        "small_group",
        "large_group",
        "any",
    }:
        raise ValidationError("群体规模偏好无效")
    if not 0 <= values["max_distance_km"] <= 100:
        raise ValidationError("活动距离必须在 0 到 100 公里之间")
    length_limits = {
        "school": 80,
        "department": 80,
        "grade": 30,
        "identity_label": 40,
        "bio": 300,
        "self_description": 1000,
        "partner_expectation": 1000,
        "contact_qq": 12,
        "contact_wechat": 80,
    }
    for field_name, maximum in length_limits.items():
        if len(str(values[field_name])) > maximum:
            raise ValidationError(f"{field_name} 长度不能超过 {maximum} 个字符")
    if values["contact_qq"] and not re.fullmatch(r"\d{5,12}", values["contact_qq"]):
        raise ValidationError("QQ号应为 5 至 12 位数字")

    normalized_privacy = dict(privacy or {})
    unknown_privacy_fields = set(normalized_privacy) - PROFILE_PRIVACY_FIELDS
    if unknown_privacy_fields:
        raise ValidationError("隐私设置包含未知字段")
    if any(value not in ALLOWED_VISIBILITIES for value in normalized_privacy.values()):
        raise ValidationError("隐私可见范围无效")

    now = _now()
    with transaction(path, immediate=True) as connection:
        normalized = _require_user(connection, email)
        placeholders = ", ".join("?" for _ in PROFILE_COLUMNS)
        updates = ", ".join(f"{column} = excluded.{column}" for column in PROFILE_COLUMNS)
        connection.execute(
            f"""
            INSERT INTO profiles(email, {', '.join(PROFILE_COLUMNS)}, created_at, updated_at)
            VALUES (?, {placeholders}, ?, ?)
            ON CONFLICT(email) DO UPDATE SET {updates}, updated_at = excluded.updated_at
            """,
            (normalized, *(values[column] for column in PROFILE_COLUMNS), now, now),
        )
        connection.execute("DELETE FROM profile_interests WHERE email = ?", (normalized,))
        for category, tag in sorted(normalized_interests):
            connection.execute(
                "INSERT INTO profile_interests(email, category, tag, created_at) VALUES (?, ?, ?, ?)",
                (normalized, category, tag, now),
            )
        if privacy is not None:
            connection.execute("DELETE FROM profile_privacy WHERE email = ?", (normalized,))
            for field_name, visibility in sorted(normalized_privacy.items()):
                connection.execute(
                    """
                    INSERT INTO profile_privacy(email, field_name, visibility, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (normalized, str(field_name), str(visibility), now),
                )
        _audit(
            connection,
            actor_email=normalized,
            action="profile.upsert",
            entity_type="profile",
            entity_id=normalized,
        )


def _load_profile(
    connection: DatabaseConnection, email: str
) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM profiles WHERE email = ?", (email,)).fetchone()
    if row is None:
        return None
    interests = connection.execute(
        "SELECT category, tag FROM profile_interests WHERE email = ? ORDER BY category, tag",
        (email,),
    ).fetchall()
    privacy_rows = connection.execute(
        "SELECT field_name, visibility FROM profile_privacy WHERE email = ? ORDER BY field_name",
        (email,),
    ).fetchall()
    result = dict(row)
    result["available_times"] = json.loads(str(result.pop("available_times_json")))
    result["preferred_locations"] = json.loads(
        str(result.pop("preferred_locations_json"))
    )
    result["interests"] = [dict(item) for item in interests]
    result["privacy"] = {
        str(item["field_name"]): str(item["visibility"]) for item in privacy_rows
    }
    return result


def get_profile(email: str, *, sqlite_path: Path | None = None) -> dict[str, Any] | None:
    path = _prepare_database(sqlite_path)
    normalized = normalize_email(email)
    with transaction(path) as connection:
        return _load_profile(connection, normalized)


def get_visible_profile(
    viewer_email: str,
    subject_email: str,
    *,
    sqlite_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return only fields visible to a verified viewer under stored privacy rules."""

    path = _prepare_database(sqlite_path)
    viewer = normalize_email(viewer_email)
    subject = normalize_email(subject_email)
    with transaction(path) as connection:
        _require_user(connection, viewer)
        profile = _load_profile(connection, subject)
        if profile is None:
            return None
        if viewer == subject:
            return profile

        shares_activity = connection.execute(
            """
            SELECT 1
            FROM activity_members AS viewer_membership
            JOIN activity_members AS subject_membership
              ON subject_membership.activity_id = viewer_membership.activity_id
            WHERE viewer_membership.member_email = ?
              AND subject_membership.member_email = ?
            LIMIT 1
            """,
            (viewer, subject),
        ).fetchone() is not None
        is_matched = connection.execute(
            """
            SELECT 1
            FROM match_result_members AS viewer_result
            JOIN match_result_members AS subject_result
              ON subject_result.result_id = viewer_result.result_id
            WHERE viewer_result.email = ? AND subject_result.email = ?
            LIMIT 1
            """,
            (viewer, subject),
        ).fetchone() is not None

    allowed_visibilities = {"public"}
    if shares_activity:
        allowed_visibilities.add("activity_members")
    if is_matched:
        allowed_visibilities.add("matched")

    privacy = dict(profile.get("privacy", {}))
    visible: dict[str, Any] = {
        "display_name": profile["display_name"],
        "completion_percent": profile["completion_percent"],
    }
    for field_name, privacy_key in PROFILE_FIELD_PRIVACY_KEY.items():
        if privacy.get(privacy_key, "private") in allowed_visibilities:
            visible[field_name] = profile.get(field_name)
    return visible


def validate_profile_for_matching(
    email: str, *, sqlite_path: Path | None = None
) -> list[str]:
    """Return matching prerequisites still missing for the given account."""

    profile = get_profile(email, sqlite_path=sqlite_path)
    interests = profile.get("interests", []) if profile else []
    return matching_profile_missing_fields(profile, interests)


def _profile_contact_suggestion(
    connection: DatabaseConnection, email: str
) -> str:
    """Return a labelled saved contact for backward-compatible service callers."""

    profile = _load_profile(connection, email)
    if profile is None:
        return ""
    for label, field_name in (
        ("邮箱", "contact_email"),
        ("QQ", "contact_qq"),
        ("微信", "contact_wechat"),
    ):
        value = str(profile.get(field_name, "")).strip()
        if value:
            return f"{label}：{value}"
    return ""


def _resolve_activity_contact(
    connection: DatabaseConnection,
    email: str,
    provided: str | None,
    *,
    field_label: str,
) -> str:
    """Validate the contact copied into an activity or application record."""

    clean_contact = (
        _profile_contact_suggestion(connection, email)
        if provided is None
        else str(provided).strip()
    )
    if not clean_contact:
        raise ValidationError(f"请填写{field_label}")
    if len(clean_contact) > 160:
        raise ValidationError(f"{field_label}不能超过 160 个字符")
    return clean_contact


def create_activity(
    organizer_email: str,
    *,
    category: str,
    title: str,
    description: str,
    starts_at: int,
    location_text: str,
    capacity: int,
    ends_at: int | None = None,
    custom_category: str = "",
    image_url: str = "",
    visibility: str = "campus",
    approval_required: bool = True,
    status: str = "published",
    organizer_contact: str | None = None,
    sqlite_path: Path | None = None,
) -> str:
    path = _prepare_database(sqlite_path)
    values = _validate_activity_fields(
        category=category,
        custom_category=custom_category,
        title=title,
        description=description,
        image_url=image_url,
        starts_at=starts_at,
        ends_at=ends_at,
        location_text=location_text,
        capacity=capacity,
        visibility=visibility,
        status=status,
    )

    activity_id = _new_id("act")
    now = _now()
    with transaction(path, immediate=True) as connection:
        organizer = _require_user(connection, organizer_email)
        clean_organizer_contact = ""
        if values["status"] == "published" or str(organizer_contact or "").strip():
            clean_organizer_contact = _resolve_activity_contact(
                connection,
                organizer,
                organizer_contact,
                field_label="本次活动公开联系方式",
            )
        connection.execute(
            """
            INSERT INTO activities(
                activity_id, organizer_email, category, custom_category, title,
                description, image_url, starts_at, ends_at, location_text,
                capacity, visibility, approval_required, status, version,
                created_at, updated_at, organizer_contact
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                activity_id,
                organizer,
                values["category"],
                values["custom_category"],
                values["title"],
                values["description"],
                values["image_url"],
                values["starts_at"],
                values["ends_at"],
                values["location_text"],
                values["capacity"],
                values["visibility"],
                int(bool(approval_required)),
                values["status"],
                now,
                now,
                clean_organizer_contact,
            ),
        )
        connection.execute(
            "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'organizer', ?)",
            (activity_id, organizer, now),
        )
        _audit(
            connection,
            actor_email=organizer,
            action="activity.create",
            entity_type="activity",
            entity_id=activity_id,
            details={"capacity": values["capacity"], "status": values["status"]},
        )
    return activity_id


def _refresh_ended_activities(connection: DatabaseConnection, now: int) -> None:
    connection.execute(
        """
        UPDATE activities
        SET status = 'ended', version = version + 1, updated_at = ?
        WHERE status IN ('published', 'full')
          AND ends_at IS NOT NULL
          AND ends_at <= ?
        """,
        (now, now),
    )


def _activity_select_sql() -> str:
    return """
        SELECT
            a.*,
            COALESCE(p.display_name, '') AS organizer_name,
            (SELECT COUNT(*) FROM activity_members AS member_count
             WHERE member_count.activity_id = a.activity_id) AS member_count,
            CASE WHEN a.organizer_email = ? THEN 1 ELSE 0 END AS is_organizer,
            CASE WHEN EXISTS(
                SELECT 1 FROM activity_members AS viewer_membership
                WHERE viewer_membership.activity_id = a.activity_id
                  AND viewer_membership.member_email = ?
            ) THEN 1 ELSE 0 END AS is_member
        FROM activities AS a
        LEFT JOIN profiles AS p ON p.email = a.organizer_email
    """


def _hydrate_activity(row: Mapping[str, Any]) -> dict[str, Any]:
    activity = dict(row)
    activity["member_count"] = int(activity.get("member_count", 0))
    activity["capacity"] = int(activity["capacity"])
    activity["approval_required"] = bool(activity["approval_required"])
    activity["is_organizer"] = bool(activity.get("is_organizer"))
    activity["is_member"] = bool(activity.get("is_member"))
    activity["ends_at"] = (
        int(activity["ends_at"]) if activity.get("ends_at") is not None else None
    )
    return activity


def list_activities(
    viewer_email: str,
    *,
    scope: str = "discover",
    keyword: str = "",
    categories: Iterable[str] = (),
    location: str = "",
    statuses: Iterable[str] = (),
    starts_after: int | None = None,
    starts_before: int | None = None,
    sort_by: str = "soonest",
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return activities visible to a verified user with server-side filters."""

    path = _prepare_database(sqlite_path)
    if scope not in {"discover", "mine"}:
        raise ValidationError("活动列表范围无效")
    clean_categories = {str(item).strip() for item in categories if str(item).strip()}
    if not clean_categories <= ACTIVITY_CATEGORIES:
        raise ValidationError("活动筛选分类无效")
    clean_statuses = {str(item).strip() for item in statuses if str(item).strip()}
    if not clean_statuses <= ACTIVITY_STATUSES:
        raise ValidationError("活动筛选状态无效")
    if sort_by not in {"soonest", "newest", "popular"}:
        raise ValidationError("活动排序方式无效")
    clean_keyword = str(keyword).strip().lower()
    clean_location = str(location).strip().lower()
    if len(clean_keyword) > 80 or len(clean_location) > 80:
        raise ValidationError("筛选关键词不能超过 80 个字符")

    now = _now()
    with transaction(path, immediate=True) as connection:
        viewer = _require_user(connection, viewer_email)
        _refresh_ended_activities(connection, now)
        sql = _activity_select_sql()
        parameters: list[Any] = [viewer, viewer]
        clauses = [
            "(a.visibility IN ('campus', 'public') OR a.organizer_email = ? OR EXISTS("
            "SELECT 1 FROM activity_members AS visible_member "
            "WHERE visible_member.activity_id = a.activity_id "
            "AND visible_member.member_email = ?))"
        ]
        parameters.extend([viewer, viewer])
        if scope == "discover":
            clauses.append("a.status IN ('published', 'full', 'ended')")
        else:
            clauses.append(
                "(a.organizer_email = ? OR EXISTS(SELECT 1 FROM activity_members AS mine_member "
                "WHERE mine_member.activity_id = a.activity_id AND mine_member.member_email = ?))"
            )
            parameters.extend([viewer, viewer])
        if clean_keyword:
            like = f"%{clean_keyword}%"
            clauses.append(
                "(LOWER(a.title) LIKE ? OR LOWER(a.description) LIKE ? "
                "OR LOWER(a.location_text) LIKE ? OR LOWER(a.custom_category) LIKE ?)"
            )
            parameters.extend([like, like, like, like])
        if clean_categories:
            placeholders = ", ".join("?" for _ in clean_categories)
            clauses.append(f"a.category IN ({placeholders})")
            parameters.extend(sorted(clean_categories))
        if clean_location:
            clauses.append("LOWER(a.location_text) LIKE ?")
            parameters.append(f"%{clean_location}%")
        if clean_statuses:
            placeholders = ", ".join("?" for _ in clean_statuses)
            clauses.append(f"a.status IN ({placeholders})")
            parameters.extend(sorted(clean_statuses))
        if starts_after is not None:
            clauses.append("a.starts_at >= ?")
            parameters.append(int(starts_after))
        if starts_before is not None:
            clauses.append("a.starts_at < ?")
            parameters.append(int(starts_before))
        order_by = {
            "soonest": "CASE WHEN a.status = 'ended' THEN 1 ELSE 0 END, a.starts_at ASC",
            "newest": "a.created_at DESC",
            "popular": "member_count DESC, a.starts_at ASC",
        }[sort_by]
        rows = connection.execute(
            f"{sql} WHERE {' AND '.join(clauses)} ORDER BY {order_by}",
            tuple(parameters),
        ).fetchall()
    return [_hydrate_activity(row) for row in rows]


def get_activity(
    activity_id: str,
    viewer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        viewer = _require_user(connection, viewer_email)
        _refresh_ended_activities(connection, now)
        row = connection.execute(
            _activity_select_sql() + " WHERE a.activity_id = ?",
            (viewer, viewer, activity_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("活动不存在")
        activity = _hydrate_activity(row)
        can_view = (
            activity["visibility"] in {"campus", "public"}
            or activity["is_organizer"]
            or activity["is_member"]
        )
        if not can_view:
            raise PermissionDenied("你无权查看该活动")
        if activity["status"] in {"draft", "cancelled"} and not activity["is_organizer"]:
            raise PermissionDenied("你无权查看该活动")
        application = connection.execute(
            """
            SELECT application_id, reason, status, attempt_count,
                   created_at, updated_at, reviewed_at
            FROM activity_applications
            WHERE activity_id = ? AND applicant_email = ?
            """,
            (activity_id, viewer),
        ).fetchone()
        activity["viewer_application"] = dict(application) if application else None
        return activity


def update_activity(
    activity_id: str,
    organizer_email: str,
    *,
    category: str,
    title: str,
    description: str,
    starts_at: int,
    location_text: str,
    capacity: int,
    expected_version: int,
    ends_at: int | None = None,
    custom_category: str = "",
    image_url: str = "",
    visibility: str = "campus",
    approval_required: bool = True,
    status: str | None = None,
    organizer_contact: str | None = None,
    sqlite_path: Path | None = None,
) -> None:
    """Edit a draft or future published activity with optimistic version checks."""

    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        organizer = _require_user(connection, organizer_email)
        row = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("活动不存在")
        if str(row["organizer_email"]) != organizer:
            raise PermissionDenied("只有活动发起人可以编辑活动")
        current_status = str(row["status"])
        if current_status not in {"draft", "published"}:
            raise ConflictError("当前状态的活动不能编辑")
        if int(row["version"]) != int(expected_version):
            raise ConflictError("活动已被更新，请刷新后重试")
        requested_status = str(status or current_status)
        if current_status == "published" and requested_status == "draft":
            raise ConflictError("已发布活动不能退回草稿")
        values = _validate_activity_fields(
            category=category,
            custom_category=custom_category,
            title=title,
            description=description,
            image_url=image_url,
            starts_at=starts_at,
            ends_at=ends_at,
            location_text=location_text,
            capacity=capacity,
            visibility=visibility,
            status=requested_status,
        )
        current_contact = str(row["organizer_contact"] or "").strip()
        requested_contact = current_contact if organizer_contact is None else organizer_contact
        clean_organizer_contact = ""
        if values["status"] == "published" or str(requested_contact or "").strip():
            clean_organizer_contact = _resolve_activity_contact(
                connection,
                organizer,
                requested_contact,
                field_label="本次活动公开联系方式",
            )
        member_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM activity_members WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()["count"]
        )
        if values["capacity"] < member_count:
            raise CapacityError("活动人数不能小于当前成员数")
        connection.execute(
            """
            UPDATE activities SET
                category = ?, custom_category = ?, title = ?, description = ?,
                image_url = ?, starts_at = ?, ends_at = ?, location_text = ?,
                capacity = ?, visibility = ?, approval_required = ?, status = ?,
                organizer_contact = ?, version = version + 1, updated_at = ?
            WHERE activity_id = ?
            """,
            (
                values["category"], values["custom_category"], values["title"],
                values["description"], values["image_url"], values["starts_at"],
                values["ends_at"], values["location_text"], values["capacity"],
                values["visibility"], int(bool(approval_required)),
                values["status"], clean_organizer_contact, now, activity_id,
            ),
        )
        _audit(
            connection,
            actor_email=organizer,
            action="activity.update",
            entity_type="activity",
            entity_id=activity_id,
            details={"status": values["status"]},
        )


def publish_activity(
    activity_id: str,
    organizer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        organizer = _require_user(connection, organizer_email)
        row = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("活动不存在")
        if str(row["organizer_email"]) != organizer:
            raise PermissionDenied("只有活动发起人可以发布活动")
        if str(row["status"]) != "draft":
            raise ConflictError("只有草稿可以发布")
        if int(row["starts_at"]) < now - 60:
            raise ValidationError("请先把活动开始时间调整到未来")
        _resolve_activity_contact(
            connection,
            organizer,
            str(row["organizer_contact"] or ""),
            field_label="本次活动公开联系方式",
        )
        connection.execute(
            "UPDATE activities SET status = 'published', version = version + 1, updated_at = ? WHERE activity_id = ?",
            (now, activity_id),
        )
        _audit(
            connection,
            actor_email=organizer,
            action="activity.publish",
            entity_type="activity",
            entity_id=activity_id,
        )


def end_activity(
    activity_id: str,
    organizer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        organizer = _require_user(connection, organizer_email)
        row = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("活动不存在")
        if str(row["organizer_email"]) != organizer:
            raise PermissionDenied("只有活动发起人可以结束活动")
        if str(row["status"]) not in {"published", "full"}:
            raise ConflictError("活动当前不能结束")
        connection.execute(
            "UPDATE activities SET status = 'ended', version = version + 1, updated_at = ? WHERE activity_id = ?",
            (now, activity_id),
        )
        _audit(
            connection,
            actor_email=organizer,
            action="activity.end",
            entity_type="activity",
            entity_id=activity_id,
        )


def apply_to_activity(
    activity_id: str,
    applicant_email: str,
    *,
    reason: str = "",
    applicant_contact: str | None = None,
    sqlite_path: Path | None = None,
) -> str:
    path = _prepare_database(sqlite_path)
    clean_reason = reason.strip()
    if len(clean_reason) > 500:
        raise ValidationError("申请说明不能超过 500 个字符")
    now = _now()
    with transaction(path, immediate=True) as connection:
        applicant = _require_user(connection, applicant_email)
        clean_applicant_contact = _resolve_activity_contact(
            connection,
            applicant,
            applicant_contact,
            field_label="本次申请联系方式",
        )
        activity = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        if str(activity["organizer_email"]) == applicant:
            raise ConflictError("发起人已经是活动成员")
        if str(activity["status"]) != "published":
            raise ConflictError("活动当前不可申请")
        member_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM activity_members WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()["count"]
        )
        if member_count >= int(activity["capacity"]):
            raise CapacityError("活动人数已满")
        existing = connection.execute(
            connection.select_for_update(
                "SELECT * FROM activity_applications WHERE activity_id = ? AND applicant_email = ?"
            ),
            (activity_id, applicant),
        ).fetchone()
        if existing and str(existing["status"]) != "withdrawn":
            raise ConflictError("你已经申请过该活动")

        if existing:
            application_id = str(existing["application_id"])
            attempt_count = int(existing["attempt_count"]) + 1
            connection.execute(
                """
                UPDATE activity_applications
                SET reason = ?, applicant_contact = ?, status = 'pending', attempt_count = ?,
                    reviewed_at = NULL, updated_at = ?
                WHERE application_id = ?
                """,
                (clean_reason, clean_applicant_contact, attempt_count, now, application_id),
            )
        else:
            application_id = _new_id("application")
            attempt_count = 1
            try:
                connection.execute(
                    """
                    INSERT INTO activity_applications(
                        application_id, activity_id, applicant_email, reason,
                        applicant_contact, status, attempt_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', 1, ?, ?)
                    """,
                    (
                        application_id,
                        activity_id,
                        applicant,
                        clean_reason,
                        clean_applicant_contact,
                        now,
                        now,
                    ),
                )
            except Exception as error:
                if is_integrity_error(error):
                    raise ConflictError("你已经申请过该活动") from error
                raise

        organizer = str(activity["organizer_email"])
        applicant_name = _display_name(connection, applicant)
        title = str(activity["title"])
        if not bool(activity["approval_required"]):
            connection.execute(
                "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'member', ?)",
                (activity_id, applicant, now),
            )
            connection.execute(
                """
                UPDATE activity_applications
                SET status = 'approved', reviewed_at = ?, updated_at = ?
                WHERE application_id = ?
                """,
                (now, now, application_id),
            )
            if member_count + 1 >= int(activity["capacity"]):
                connection.execute(
                    "UPDATE activities SET status = 'full', version = version + 1, updated_at = ? WHERE activity_id = ?",
                    (now, activity_id),
                )
            _enqueue_notification(
                connection,
                recipient_email=applicant,
                notification_type="activity_joined",
                title="已加入活动",
                message=f"你已加入“{title}”，无需等待发起人审核。",
                entity_type="activity",
                entity_id=activity_id,
                idempotency_key=f"activity-auto-joined:{application_id}:{attempt_count}",
            )
            _enqueue_email_task(
                connection,
                recipient_email=applicant,
                template_key="activity_application_approved",
                payload={"activity_id": activity_id, "activity_title": title},
                idempotency_key=f"activity-auto-joined-mail:{application_id}:{attempt_count}",
            )
            organizer_message = (
                f"{applicant_name} 已直接加入“{title}”。"
                f"联系方式：{clean_applicant_contact}"
            )
            organizer_type = "activity_member_joined"
        else:
            organizer_message = (
                f"{applicant_name} 申请加入“{title}”。"
                f"联系方式：{clean_applicant_contact}"
            )
            organizer_type = "activity_application_created"

        _enqueue_notification(
            connection,
            recipient_email=organizer,
            notification_type=organizer_type,
            title="收到新的活动申请" if bool(activity["approval_required"]) else "有新成员加入",
            message=organizer_message,
            entity_type="activity",
            entity_id=activity_id,
            idempotency_key=f"activity-application-owner:{application_id}:{attempt_count}",
        )
        _enqueue_email_task(
            connection,
            recipient_email=organizer,
            template_key="activity_application_created",
            payload={
                "activity_id": activity_id,
                "activity_title": title,
                "application_id": application_id,
                "applicant_name": applicant_name,
                "applicant_contact": clean_applicant_contact,
                "reason": clean_reason,
                "approval_required": bool(activity["approval_required"]),
            },
            idempotency_key=f"activity-application-created:{application_id}:{attempt_count}",
        )
        _audit(
            connection,
            actor_email=applicant,
            action="activity.apply",
            entity_type="activity_application",
            entity_id=application_id,
            details={"activity_id": activity_id, "attempt_count": attempt_count},
        )
    return application_id


def list_activity_applications(
    activity_id: str,
    organizer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return applications only to the activity organizer."""

    path = _prepare_database(sqlite_path)
    with transaction(path) as connection:
        organizer = _require_user(connection, organizer_email)
        activity = connection.execute(
            "SELECT organizer_email FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        if str(activity["organizer_email"]) != organizer:
            raise PermissionDenied("只有活动发起人可以查看申请")
        rows = connection.execute(
            """
            SELECT aa.application_id, aa.applicant_email, aa.reason, aa.status,
                   aa.applicant_contact, aa.attempt_count, aa.created_at,
                   aa.updated_at, aa.reviewed_at,
                   COALESCE(p.display_name, '') AS applicant_name
            FROM activity_applications AS aa
            LEFT JOIN profiles AS p ON p.email = aa.applicant_email
            WHERE aa.activity_id = ?
            ORDER BY CASE aa.status WHEN 'pending' THEN 0 ELSE 1 END,
                     aa.updated_at DESC
            """,
            (activity_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_activity_members(
    activity_id: str,
    viewer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return the roster only to an activity member or its organizer."""

    path = _prepare_database(sqlite_path)
    with transaction(path) as connection:
        viewer = _require_user(connection, viewer_email)
        activity = connection.execute(
            "SELECT organizer_email FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        membership = connection.execute(
            "SELECT 1 FROM activity_members WHERE activity_id = ? AND member_email = ?",
            (activity_id, viewer),
        ).fetchone()
        if str(activity["organizer_email"]) != viewer and membership is None:
            raise PermissionDenied("只有活动成员可以查看成员名单")
        rows = connection.execute(
            """
            SELECT am.member_email, am.role, am.joined_at,
                   COALESCE(p.display_name, '') AS member_name
            FROM activity_members AS am
            LEFT JOIN profiles AS p ON p.email = am.member_email
            WHERE am.activity_id = ?
            ORDER BY CASE am.role WHEN 'organizer' THEN 0 ELSE 1 END, am.joined_at
            """,
            (activity_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def review_activity_application(
    activity_id: str,
    application_id: str,
    organizer_email: str,
    *,
    approve: bool,
    sqlite_path: Path | None = None,
) -> str:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        actor = _require_user(connection, organizer_email)
        activity = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        if str(activity["organizer_email"]) != actor:
            raise PermissionDenied("只有活动发起人可以审批申请")
        if str(activity["status"]) not in {"published", "full"}:
            raise ConflictError("活动当前不能处理申请")
        application = connection.execute(
            connection.select_for_update(
                "SELECT * FROM activity_applications WHERE application_id = ? AND activity_id = ?"
            ),
            (application_id, activity_id),
        ).fetchone()
        if application is None:
            raise NotFoundError("申请不存在")
        if str(application["status"]) != "pending":
            raise ConflictError("该申请已经处理")

        applicant = str(application["applicant_email"])
        attempt_count = int(application["attempt_count"])
        status = "approved" if approve else "rejected"
        if approve:
            member_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM activity_members WHERE activity_id = ?",
                    (activity_id,),
                ).fetchone()["count"]
            )
            if member_count >= int(activity["capacity"]):
                raise CapacityError("活动人数已满，不能继续批准")
            try:
                connection.execute(
                    "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'member', ?)",
                    (activity_id, applicant, now),
                )
            except Exception as error:
                if is_integrity_error(error):
                    raise ConflictError("该用户已经是活动成员") from error
                raise
            if member_count + 1 >= int(activity["capacity"]):
                connection.execute(
                    "UPDATE activities SET status = 'full', version = version + 1, updated_at = ? WHERE activity_id = ?",
                    (now, activity_id),
                )

        connection.execute(
            """
            UPDATE activity_applications
            SET status = ?, reviewed_at = ?, updated_at = ?
            WHERE application_id = ?
            """,
            (status, now, now, application_id),
        )
        _enqueue_email_task(
            connection,
            recipient_email=applicant,
            template_key=f"activity_application_{status}",
            payload={
                "activity_id": activity_id,
                "activity_title": str(activity["title"]),
                "application_id": application_id,
            },
            idempotency_key=f"activity-application-{status}:{application_id}:{attempt_count}",
        )
        _enqueue_notification(
            connection,
            recipient_email=applicant,
            notification_type=f"activity_application_{status}",
            title="活动申请已通过" if approve else "活动申请未通过",
            message=(
                f"你已加入“{activity['title']}”。"
                if approve
                else f"你对“{activity['title']}”的申请未通过。"
            ),
            entity_type="activity",
            entity_id=activity_id,
            idempotency_key=f"activity-application-notice:{status}:{application_id}:{attempt_count}",
        )
        _audit(
            connection,
            actor_email=actor,
            action=f"activity.application.{status}",
            entity_type="activity_application",
            entity_id=application_id,
            details={"activity_id": activity_id},
        )
    return status


def withdraw_activity_application(
    activity_id: str,
    applicant_email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        applicant = _require_user(connection, applicant_email)
        activity = connection.execute(
            "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        application = connection.execute(
            connection.select_for_update(
                "SELECT * FROM activity_applications WHERE activity_id = ? AND applicant_email = ?"
            ),
            (activity_id, applicant),
        ).fetchone()
        if application is None or str(application["status"]) != "pending":
            raise ConflictError("当前没有可以撤回的待审核申请")
        connection.execute(
            "UPDATE activity_applications SET status = 'withdrawn', updated_at = ? WHERE application_id = ?",
            (now, str(application["application_id"])),
        )
        applicant_name = _display_name(connection, applicant)
        _enqueue_notification(
            connection,
            recipient_email=str(activity["organizer_email"]),
            notification_type="activity_application_withdrawn",
            title="活动申请已撤回",
            message=f"{applicant_name} 撤回了对“{activity['title']}”的申请。",
            entity_type="activity",
            entity_id=activity_id,
            idempotency_key=f"activity-application-withdrawn:{application['application_id']}:{application['attempt_count']}",
        )
        _audit(
            connection,
            actor_email=applicant,
            action="activity.application.withdrawn",
            entity_type="activity_application",
            entity_id=str(application["application_id"]),
            details={"activity_id": activity_id},
        )


def leave_activity(
    activity_id: str,
    member_email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        member = _require_user(connection, member_email)
        activity = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        if str(activity["organizer_email"]) == member:
            raise ConflictError("发起人不能退出自己的活动，可以取消活动")
        if str(activity["status"]) not in {"published", "full"}:
            raise ConflictError("活动当前不能退出")
        membership = connection.execute(
            "SELECT 1 FROM activity_members WHERE activity_id = ? AND member_email = ?",
            (activity_id, member),
        ).fetchone()
        if membership is None:
            raise ConflictError("你还不是该活动成员")
        connection.execute(
            "DELETE FROM activity_members WHERE activity_id = ? AND member_email = ?",
            (activity_id, member),
        )
        connection.execute(
            """
            UPDATE activity_applications
            SET status = 'withdrawn', updated_at = ?
            WHERE activity_id = ? AND applicant_email = ? AND status = 'approved'
            """,
            (now, activity_id, member),
        )
        if str(activity["status"]) == "full":
            connection.execute(
                "UPDATE activities SET status = 'published', version = version + 1, updated_at = ? WHERE activity_id = ?",
                (now, activity_id),
            )
        member_name = _display_name(connection, member)
        _enqueue_notification(
            connection,
            recipient_email=str(activity["organizer_email"]),
            notification_type="activity_member_left",
            title="成员退出活动",
            message=f"{member_name} 已退出“{activity['title']}”。",
            entity_type="activity",
            entity_id=activity_id,
            idempotency_key=f"activity-member-left:{activity_id}:{member}:{now}",
        )
        _audit(
            connection,
            actor_email=member,
            action="activity.member.leave",
            entity_type="activity",
            entity_id=activity_id,
        )


def remove_activity_member(
    activity_id: str,
    member_email: str,
    organizer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        organizer = _require_user(connection, organizer_email)
        member = normalize_email(member_email)
        activity = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        if str(activity["organizer_email"]) != organizer:
            raise PermissionDenied("只有活动发起人可以移除成员")
        if member == organizer:
            raise ConflictError("不能移除活动发起人")
        if str(activity["status"]) not in {"published", "full"}:
            raise ConflictError("活动当前不能移除成员")
        membership = connection.execute(
            "SELECT 1 FROM activity_members WHERE activity_id = ? AND member_email = ?",
            (activity_id, member),
        ).fetchone()
        if membership is None:
            raise NotFoundError("该用户不是活动成员")
        connection.execute(
            "DELETE FROM activity_members WHERE activity_id = ? AND member_email = ?",
            (activity_id, member),
        )
        connection.execute(
            """
            UPDATE activity_applications
            SET status = 'rejected', reviewed_at = ?, updated_at = ?
            WHERE activity_id = ? AND applicant_email = ? AND status = 'approved'
            """,
            (now, now, activity_id, member),
        )
        if str(activity["status"]) == "full":
            connection.execute(
                "UPDATE activities SET status = 'published', version = version + 1, updated_at = ? WHERE activity_id = ?",
                (now, activity_id),
            )
        _enqueue_notification(
            connection,
            recipient_email=member,
            notification_type="activity_member_removed",
            title="已离开活动",
            message=f"发起人已将你移出“{activity['title']}”。",
            entity_type="activity",
            entity_id=activity_id,
            idempotency_key=f"activity-member-removed:{activity_id}:{member}:{now}",
        )
        _enqueue_email_task(
            connection,
            recipient_email=member,
            template_key="activity_member_removed",
            payload={"activity_id": activity_id, "activity_title": str(activity["title"])},
            idempotency_key=f"activity-member-removed-mail:{activity_id}:{member}:{now}",
        )
        _audit(
            connection,
            actor_email=organizer,
            action="activity.member.remove",
            entity_type="activity",
            entity_id=activity_id,
            details={"member_email": member},
        )


def cancel_activity(
    activity_id: str,
    organizer_email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        actor = _require_user(connection, organizer_email)
        activity = connection.execute(
            connection.select_for_update("SELECT * FROM activities WHERE activity_id = ?"),
            (activity_id,),
        ).fetchone()
        if activity is None:
            raise NotFoundError("活动不存在")
        if str(activity["organizer_email"]) != actor:
            raise PermissionDenied("只有活动发起人可以取消活动")
        if str(activity["status"]) in {"ended", "cancelled"}:
            raise ConflictError("活动当前不能取消")
        recipients = connection.execute(
            """
            SELECT applicant_email AS email
            FROM activity_applications
            WHERE activity_id = ? AND status = 'pending'
            UNION
            SELECT member_email AS email
            FROM activity_members
            WHERE activity_id = ? AND member_email <> ?
            """,
            (activity_id, activity_id, actor),
        ).fetchall()
        connection.execute(
            """
            UPDATE activity_applications
            SET status = 'rejected', reviewed_at = ?, updated_at = ?
            WHERE activity_id = ? AND status = 'pending'
            """,
            (now, now, activity_id),
        )
        connection.execute(
            "UPDATE activities SET status = 'cancelled', version = version + 1, updated_at = ? WHERE activity_id = ?",
            (now, activity_id),
        )
        for recipient in recipients:
            recipient_email = str(recipient["email"])
            _enqueue_notification(
                connection,
                recipient_email=recipient_email,
                notification_type="activity_cancelled",
                title="活动已取消",
                message=f"“{activity['title']}”已由发起人取消。",
                entity_type="activity",
                entity_id=activity_id,
                idempotency_key=f"activity-cancelled:{activity_id}:{recipient_email}",
            )
            _enqueue_email_task(
                connection,
                recipient_email=recipient_email,
                template_key="activity_cancelled",
                payload={"activity_id": activity_id, "activity_title": str(activity["title"])},
                idempotency_key=f"activity-cancelled-mail:{activity_id}:{recipient_email}",
            )
        _audit(
            connection,
            actor_email=actor,
            action="activity.cancel",
            entity_type="activity",
            entity_id=activity_id,
        )


def list_user_notifications(
    recipient_email: str,
    *,
    unread_only: bool = False,
    limit: int = 50,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = _prepare_database(sqlite_path)
    clean_limit = max(1, min(int(limit), 100))
    with transaction(path) as connection:
        recipient = _require_user(connection, recipient_email)
        clauses = ["recipient_email = ?"]
        parameters: list[Any] = [recipient]
        if unread_only:
            clauses.append("is_read = 0")
        parameters.append(clean_limit)
        rows = connection.execute(
            f"""
            SELECT notification_id, notification_type, title, message,
                   entity_type, entity_id, is_read, created_at, read_at
            FROM user_notifications
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC, notification_id DESC
            LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
    notifications = [dict(row) for row in rows]
    for notification in notifications:
        notification["is_read"] = bool(notification["is_read"])
    return notifications


def mark_notification_read(
    recipient_email: str,
    notification_id: str | None = None,
    *,
    sqlite_path: Path | None = None,
) -> int:
    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        recipient = _require_user(connection, recipient_email)
        if notification_id:
            cursor = connection.execute(
                """
                UPDATE user_notifications SET is_read = 1, read_at = ?
                WHERE recipient_email = ? AND notification_id = ? AND is_read = 0
                """,
                (now, recipient, str(notification_id)),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE user_notifications SET is_read = 1, read_at = ?
                WHERE recipient_email = ? AND is_read = 0
                """,
                (now, recipient),
            )
        return int(cursor.rowcount or 0)


def create_match_round(
    creator_email: str,
    *,
    name: str,
    registration_opens_at: int,
    registration_closes_at: int,
    results_at: int,
    status: str = "planned",
    sqlite_path: Path | None = None,
) -> str:
    path = _prepare_database(sqlite_path)
    if not name.strip():
        raise ValidationError("匹配轮次名称不能为空")
    if not int(registration_opens_at) < int(registration_closes_at) <= int(results_at):
        raise ValidationError("报名和结果时间顺序不正确")
    round_id = _new_id("round")
    now = _now()
    with transaction(path, immediate=True) as connection:
        creator = _require_user(connection, creator_email)
        connection.execute(
            """
            INSERT INTO match_rounds(
                round_id, name, status, registration_opens_at,
                registration_closes_at, results_at, created_by_email,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_id, name.strip(), status, int(registration_opens_at),
                int(registration_closes_at), int(results_at), creator, now, now,
            ),
        )
        _audit(
            connection,
            actor_email=creator,
            action="match_round.create",
            entity_type="match_round",
            entity_id=round_id,
        )
    return round_id


def enroll_in_match_round(
    round_id: str,
    email: str,
    *,
    sqlite_path: Path | None = None,
) -> None:
    """Enroll once and freeze the current normalized profile as a snapshot."""

    path = _prepare_database(sqlite_path)
    now = _now()
    with transaction(path, immediate=True) as connection:
        normalized = _require_user(connection, email)
        round_row = connection.execute(
            connection.select_for_update("SELECT * FROM match_rounds WHERE round_id = ?"),
            (round_id,),
        ).fetchone()
        if round_row is None:
            raise NotFoundError("匹配轮次不存在")
        if str(round_row["status"]) != "open":
            raise ConflictError("当前轮次未开放报名")
        if not int(round_row["registration_opens_at"]) <= now <= int(round_row["registration_closes_at"]):
            raise ConflictError("当前不在报名时间内")
        profile = connection.execute("SELECT * FROM profiles WHERE email = ?", (normalized,)).fetchone()
        if profile is None:
            raise ValidationError("请先完善个人资料再参加周期匹配")
        interest_rows = connection.execute(
            "SELECT category, tag FROM profile_interests WHERE email = ? ORDER BY category, tag",
            (normalized,),
        ).fetchall()
        hydrated_profile = dict(profile)
        hydrated_profile["available_times"] = json.loads(
            str(hydrated_profile.get("available_times_json", "[]"))
        )
        hydrated_profile["preferred_locations"] = json.loads(
            str(hydrated_profile.get("preferred_locations_json", "[]"))
        )
        missing_fields = matching_profile_missing_fields(
            hydrated_profile, [dict(item) for item in interest_rows]
        )
        if missing_fields:
            raise ValidationError(
                "参加周期匹配前请补充：" + "、".join(missing_fields)
            )
        snapshot = {"profile": dict(profile), "interests": [dict(item) for item in interest_rows]}
        snapshot_json = _json(snapshot)
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        try:
            connection.execute(
                "INSERT INTO match_enrollments(round_id, email, status, enrolled_at, updated_at) VALUES (?, ?, 'enrolled', ?, ?)",
                (round_id, normalized, now, now),
            )
            connection.execute(
                "INSERT INTO match_profile_snapshots(round_id, email, profile_json, snapshot_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (round_id, normalized, snapshot_json, snapshot_hash, now),
            )
        except Exception as error:
            if is_integrity_error(error):
                raise ConflictError("你已经报名该轮匹配") from error
            raise
        _audit(
            connection,
            actor_email=normalized,
            action="match_round.enroll",
            entity_type="match_round",
            entity_id=round_id,
        )
