"""Stable bridge between the Streamlit UI and the Part 2 matching module.

The UI should import this module instead of importing files from ``algorithm``
directly.  Until Part 2 is delivered, callers may explicitly enable demo mode
to develop the matching and result pages.  Demo output is clearly marked and
must not be presented as a real algorithm result.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Union

from data.data_loader import load_users
from data.schema import validate_profile


MATCH_CONTRACT_VERSION = "1.0.0"
DISPLAY_DIMENSIONS = (
    "time",
    "goal",
    "level",
    "planning",
    "interest",
    "communication",
    "text",
)
DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "data" / "users.csv"

# Part 2 only needs to expose one of these entry points.  If their final module
# uses another name, update this tuple rather than changing Streamlit pages.
BACKEND_ENTRY_POINTS = (
    ("algorithm.pipeline", "run_matching"),
    ("algorithm.matching", "run_matching"),
)

Backend = Callable[
    [Mapping[str, Any], Sequence[Mapping[str, Any]]],
    Union[Mapping[str, Any], Sequence[Mapping[str, Any]]],
]


class MatchingAdapterError(RuntimeError):
    """Base exception for invalid inputs or incompatible backend output."""


class MatchingBackendUnavailable(MatchingAdapterError):
    """Raised when Part 2 is not installed and demo mode was not enabled."""


class MatchingContractError(MatchingAdapterError):
    """Raised when a backend result does not satisfy the UI contract."""


def _profile_error(profile: Mapping[str, Any], role: str) -> str | None:
    result = validate_profile(profile)
    if result.is_valid:
        return None
    details = "；".join(
        f"{issue.field}：{issue.message}" for issue in result.issues
    )
    return f"{role}未通过 Part1 Schema 校验：{details}"


def _validated_profiles(
    current_profile: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(current_profile, Mapping):
        raise MatchingAdapterError("当前用户画像必须是字典类型")
    current = dict(current_profile)
    current_error = _profile_error(current, "当前用户画像")
    if current_error:
        raise MatchingAdapterError(current_error)

    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise MatchingAdapterError("候选用户必须是画像列表")

    query_id = current["user_id"]
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, Mapping):
            raise MatchingAdapterError(f"第 {index} 个候选用户不是字典类型")
        normalized = dict(candidate)
        candidate_error = _profile_error(normalized, f"第 {index} 个候选用户")
        if candidate_error:
            raise MatchingAdapterError(candidate_error)
        candidate_id = str(normalized["user_id"])
        if candidate_id == query_id:
            continue
        if candidate_id in seen_ids:
            raise MatchingAdapterError(f"候选用户编号重复：{candidate_id}")
        seen_ids.add(candidate_id)
        validated.append(normalized)
    return current, validated


def _discover_backend() -> tuple[Backend | None, str | None]:
    for module_name, function_name in BACKEND_ENTRY_POINTS:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            # Only ignore an absent expected module.  Missing dependencies from
            # inside a delivered backend are real integration errors.
            if module_name == error.name or module_name.startswith(f"{error.name}."):
                continue
            raise MatchingAdapterError(
                f"Part2 模块 {module_name} 缺少依赖：{error.name}"
            ) from error
        except Exception as error:  # pragma: no cover - defensive integration guard
            raise MatchingAdapterError(
                f"加载 Part2 模块 {module_name} 失败：{error}"
            ) from error

        function = getattr(module, function_name, None)
        if callable(function):
            return function, f"{module_name}.{function_name}"
    return None, None


def backend_status() -> dict[str, Any]:
    """Return a UI-friendly snapshot of the Part 2 integration state."""

    backend, entry_point = _discover_backend()
    return {
        "available": backend is not None,
        "entry_point": entry_point,
        "message": (
            f"已连接 Part2：{entry_point}"
            if entry_point
            else "Part2 匹配算法尚未接入，可暂时使用演示模式开发界面。"
        ),
    }


def load_candidate_pool(path: str | Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    """Load and validate a Part1 dataset for matching-page candidates."""

    return load_users(path)


def _score(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MatchingContractError(f"{field} 必须是 0—100 的数字")
    numeric = float(value)
    if not math.isfinite(numeric) or not 0 <= numeric <= 100:
        raise MatchingContractError(f"{field} 必须在 0—100 之间")
    return round(numeric, 1)


def _string_list(value: Any, field: str, *, required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise MatchingContractError(f"{field} 必须是字符串列表")
    normalized = [str(item).strip() for item in value]
    if any(not item for item in normalized):
        raise MatchingContractError(f"{field} 不能包含空文本")
    if required and not normalized:
        raise MatchingContractError(f"{field} 至少需要一项")
    return list(dict.fromkeys(normalized))


def normalize_match(
    raw_match: Mapping[str, Any],
    *,
    query_user_id: str,
) -> dict[str, Any]:
    """Validate one Part2 result and convert it to the UI contract."""

    if not isinstance(raw_match, Mapping):
        raise MatchingContractError("单条匹配结果必须是字典")

    user_a = str(raw_match.get("user_a", "")).strip()
    user_b = str(raw_match.get("user_b", "")).strip()
    if not user_a or not user_b or user_a == user_b:
        raise MatchingContractError("匹配结果必须包含两个不同的用户编号")
    if query_user_id not in {user_a, user_b}:
        raise MatchingContractError("匹配结果中必须包含当前用户")

    raw_dimensions = raw_match.get("dimension_scores")
    if not isinstance(raw_dimensions, Mapping) or not raw_dimensions:
        raise MatchingContractError("dimension_scores 必须是非空字典")
    unknown_dimensions = sorted(set(raw_dimensions) - set(DISPLAY_DIMENSIONS))
    if unknown_dimensions:
        raise MatchingContractError(
            f"包含前端无法识别的评分维度：{unknown_dimensions}"
        )
    dimension_scores = {
        dimension: _score(raw_dimensions[dimension], f"dimension_scores.{dimension}")
        for dimension in DISPLAY_DIMENSIONS
        if dimension in raw_dimensions
    }

    return {
        "user_a": user_a,
        "user_b": user_b,
        "score": _score(raw_match.get("score"), "score"),
        "dimension_scores": dimension_scores,
        "reasons": _string_list(raw_match.get("reasons"), "reasons", required=True),
        "common_times": _string_list(raw_match.get("common_times"), "common_times"),
        "common_locations": _string_list(
            raw_match.get("common_locations"), "common_locations"
        ),
    }


def _extract_matches(raw_output: Any) -> Sequence[Mapping[str, Any]]:
    if isinstance(raw_output, Mapping):
        if "matches" in raw_output:
            matches = raw_output["matches"]
            if isinstance(matches, (str, bytes)) or not isinstance(matches, Sequence):
                raise MatchingContractError("matches 必须是匹配结果列表")
            return matches
        return [raw_output]
    if isinstance(raw_output, (str, bytes)) or not isinstance(raw_output, Sequence):
        raise MatchingContractError("Part2 输出必须是字典或字典列表")
    return raw_output


def _ratio(left: Sequence[str], right: Sequence[str]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def _demo_matches(
    current: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Create deterministic UI fixtures; this is deliberately not Part2."""

    same_type = [
        candidate
        for candidate in candidates
        if candidate["match_type"] == current["match_type"]
    ]
    ordered = sorted(
        same_type,
        key=lambda candidate: (
            candidate["activity"] != current["activity"],
            candidate["user_id"],
        ),
    )
    matches: list[dict[str, Any]] = []
    for candidate in ordered[:top_k]:
        common_times = sorted(
            set(current["available_times"]) & set(candidate["available_times"])
        )
        common_locations = sorted(
            set(current["acceptable_locations"])
            & set(candidate["acceptable_locations"])
        )
        dimensions = {
            "time": 55 + 40 * _ratio(
                current["available_times"], candidate["available_times"]
            ),
            "goal": 90 if current["goal"] == candidate["goal"] else 65,
            "level": (
                86
                if candidate["self_level"] in current["acceptable_partner_levels"]
                and current["self_level"] in candidate["acceptable_partner_levels"]
                else 58
            ),
            "planning": (
                88
                if current["planning_style"] == candidate["planning_style"]
                else 68
            ),
            "interest": 55
            + 40 * _ratio(current["interests"], candidate["interests"]),
            "communication": (
                88
                if current["communication_style"]
                == candidate["communication_style"]
                else 68
            ),
            # Text semantics belong to Part4; this fixed display value makes
            # that absence visible rather than pretending an AI model ran.
            "text": 60,
        }
        total = sum(dimensions.values()) / len(dimensions)
        reasons = []
        if common_times:
            reasons.append("存在共同空闲时间（演示）")
        if common_locations:
            reasons.append("存在双方都能接受的地点（演示）")
        if current["goal"] == candidate["goal"]:
            reasons.append("活动目标相同（演示）")
        if not reasons:
            reasons.append("用于检查结果页面布局的演示候选人")

        matches.append(
            normalize_match(
                {
                    "user_a": current["user_id"],
                    "user_b": candidate["user_id"],
                    "score": total,
                    "dimension_scores": dimensions,
                    "reasons": reasons,
                    "common_times": common_times,
                    "common_locations": common_locations,
                },
                query_user_id=str(current["user_id"]),
            )
        )
    return matches


def run_matching(
    current_profile: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    top_k: int = 3,
    allow_demo: bool = False,
    backend: Backend | None = None,
) -> dict[str, Any]:
    """Run Part2 through a stable contract and return a page-ready dictionary.

    A Part2 backend must accept ``(current_profile, candidates, top_k=...)`` and
    return either one match dictionary, a list of match dictionaries, or a
    dictionary containing a ``matches`` list.
    """

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise MatchingAdapterError("top_k 必须是大于 0 的整数")
    current, pool = _validated_profiles(current_profile, candidates)

    active_backend = backend
    entry_point = "传入的 Part2 函数" if backend is not None else None
    if active_backend is None:
        active_backend, entry_point = _discover_backend()

    warnings: list[str] = []
    if active_backend is None:
        if not allow_demo:
            raise MatchingBackendUnavailable(
                "Part2 匹配算法尚未接入。开发页面时可显式传入 allow_demo=True。"
            )
        mode = "demo"
        algorithm = "界面演示数据"
        warnings.append(
            "当前结果仅用于开发和检查页面，不是 Part2 算法的真实匹配结果。"
        )
        matches = _demo_matches(current, pool, top_k)
    else:
        mode = "part2"
        algorithm = str(entry_point)
        try:
            raw_output = active_backend(current, pool, top_k=top_k)
        except MatchingAdapterError:
            raise
        except Exception as error:
            raise MatchingAdapterError(f"Part2 匹配运行失败：{error}") from error
        matches = [
            normalize_match(item, query_user_id=str(current["user_id"]))
            for item in _extract_matches(raw_output)
        ]
        matches = sorted(matches, key=lambda item: item["score"], reverse=True)[:top_k]

    return {
        "contract_version": MATCH_CONTRACT_VERSION,
        "mode": mode,
        "algorithm": algorithm,
        "query_user_id": current["user_id"],
        "candidate_count": len(pool),
        "matches": matches,
        "warnings": warnings,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="检查 CampusMate 匹配适配层")
    parser.add_argument("--demo", action="store_true", help="运行明确标注的界面演示")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Part1 CSV 路径")
    parser.add_argument("--user-id", help="作为当前用户的匿名编号；默认使用第一行")
    parser.add_argument("--top-k", type=int, default=3, help="最多返回几条结果")
    args = parser.parse_args()

    users = load_candidate_pool(args.dataset)
    if not users:
        raise MatchingAdapterError("候选数据集为空")
    current = next(
        (user for user in users if user["user_id"] == args.user_id),
        users[0] if args.user_id is None else None,
    )
    if current is None:
        raise MatchingAdapterError(f"数据集中找不到用户：{args.user_id}")

    if not args.demo and not backend_status()["available"]:
        print(json.dumps(backend_status(), ensure_ascii=False, indent=2))
        print("如需检查界面数据，请追加 --demo。")
        return 0

    result = run_matching(
        current,
        users,
        top_k=args.top_k,
        allow_demo=args.demo,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "BACKEND_ENTRY_POINTS",
    "DEFAULT_DATASET",
    "DISPLAY_DIMENSIONS",
    "MATCH_CONTRACT_VERSION",
    "MatchingAdapterError",
    "MatchingBackendUnavailable",
    "MatchingContractError",
    "backend_status",
    "load_candidate_pool",
    "normalize_match",
    "run_matching",
]
