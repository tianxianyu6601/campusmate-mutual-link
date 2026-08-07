"""CSV persistence and dataset-level validation for CampusMate profiles."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .schema import (
    BOOLEAN_FIELDS,
    FIELD_ORDER,
    INTEGER_FIELDS,
    JSON_FIELDS,
    ordered_profile,
    validate_profile,
)


class DataLoadError(ValueError):
    """Raised when a persisted dataset cannot be decoded or validated."""


def _serialize_value(field: str, value: Any) -> str:
    if field in JSON_FIELDS:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if field in BOOLEAN_FIELDS:
        return "true" if value else "false"
    return str(value)


def _deserialize_value(field: str, value: str, row_number: int) -> Any:
    try:
        if field in JSON_FIELDS:
            return json.loads(value)
        if field in INTEGER_FIELDS:
            return int(value)
        if field in BOOLEAN_FIELDS:
            lowered = value.strip().lower()
            if lowered not in {"true", "false"}:
                raise ValueError("布尔值必须是true或false")
            return lowered == "true"
        return value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DataLoadError(
            f"第{row_number}行字段{field}无法解析：{exc}"
        ) from exc


def save_users(users: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """Validate and save users in the stable CSV interchange format."""

    destination = Path(path)
    materialized = [ordered_profile(user) for user in users]
    dataset_report = validate_dataset(materialized)
    if dataset_report["duplicate_ids"]:
        raise DataLoadError(
            f"数据集中存在重复用户ID：{dataset_report['duplicate_ids']}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELD_ORDER))
        writer.writeheader()
        for user in materialized:
            writer.writerow(
                {field: _serialize_value(field, user[field]) for field in FIELD_ORDER}
            )
    return destination


def load_users(path: str | Path, *, validate: bool = True) -> List[Dict[str, Any]]:
    """Load users from CSV and restore JSON/list fields to Python values."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"找不到数据文件：{source}")

    users: List[Dict[str, Any]] = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataLoadError("CSV缺少表头")
        missing_columns = [field for field in FIELD_ORDER if field not in reader.fieldnames]
        extra_columns = [field for field in reader.fieldnames if field not in FIELD_ORDER]
        if missing_columns or extra_columns:
            raise DataLoadError(
                f"CSV列不符合Schema；缺少={missing_columns}，多余={extra_columns}"
            )

        for row_number, row in enumerate(reader, start=2):
            profile = {
                field: _deserialize_value(field, row[field], row_number)
                for field in FIELD_ORDER
            }
            if validate:
                result = validate_profile(profile)
                if not result.is_valid:
                    detail = "; ".join(
                        f"{issue.field}:{issue.message}" for issue in result.issues
                    )
                    raise DataLoadError(f"第{row_number}行校验失败：{detail}")
            users.append(profile)
    if validate:
        dataset_report = validate_dataset(users)
        if dataset_report["duplicate_ids"]:
            raise DataLoadError(
                f"数据集中存在重复用户ID：{dataset_report['duplicate_ids']}"
            )
    return users


def validate_dataset(users: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a machine-readable validation report for a whole dataset."""

    row_issues: List[Dict[str, Any]] = []
    ids: List[Any] = []
    for index, user in enumerate(users, start=1):
        ids.append(user.get("user_id"))
        result = validate_profile(user)
        if not result.is_valid:
            row_issues.append(
                {
                    "row": index,
                    "user_id": user.get("user_id"),
                    "issues": [issue.as_dict() for issue in result.issues],
                }
            )

    duplicate_ids = sorted(
        str(user_id) for user_id, count in Counter(ids).items() if count > 1
    )
    return {
        "is_valid": not row_issues and not duplicate_ids,
        "user_count": len(users),
        "invalid_row_count": len(row_issues),
        "duplicate_ids": duplicate_ids,
        "row_issues": row_issues,
    }


def summarize_dataset(users: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Summarize coverage and common distributions without personal data."""

    def counts(field: str) -> Dict[str, int]:
        return dict(sorted(Counter(str(user.get(field)) for user in users).items()))

    activity_counts = counts("activity")
    location_counts: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    time_counts: Counter[str] = Counter()
    for user in users:
        location_counts.update(user.get("acceptable_locations", []))
        level_counts.update([str(user.get("self_level"))])
        time_counts.update(user.get("available_times", []))

    validation = validate_dataset(users)
    return {
        "user_count": len(users),
        "schema_versions": counts("schema_version"),
        "match_type_counts": counts("match_type"),
        "activity_counts": activity_counts,
        "level_counts": dict(sorted(level_counts.items())),
        "location_counts": dict(sorted(location_counts.items())),
        "unique_time_slot_count": len(time_counts),
        "most_common_time_slots": [
            {"time_slot": slot, "count": count}
            for slot, count in time_counts.most_common(10)
        ],
        "validation": validation,
    }


def write_quality_report(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    path: str | Path,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "datasets": {
            name: summarize_dataset(users) for name, users in datasets.items()
        }
    }
    if metadata is not None:
        report["metadata"] = dict(metadata)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


__all__ = [
    "DataLoadError",
    "load_users",
    "save_users",
    "summarize_dataset",
    "validate_dataset",
    "write_quality_report",
]
