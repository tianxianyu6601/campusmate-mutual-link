"""Deterministic, scenario-aware mock user generation for CampusMate."""

from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from questionnaire.profile_builder import build_profile
from . import vocabulary as vocab
from .data_loader import save_users, validate_dataset, write_quality_report
from .schema import SCHEMA_VERSION


DEFAULT_SEED = 20260802
DEFAULT_SIZES = (50, 100, 200)

# This ten-user cycle yields a stable 40% study / 40% sport / 20% interest mix.
MATCH_TYPE_CYCLE = (
    "study",
    "study",
    "sport",
    "sport",
    "interest",
    "interest",
    "study",
    "study",
    "sport",
    "sport",
)

GROUP_SIZE_PATTERN = (
    "one_to_one",
    "one_to_one",
    "either",
    "one_to_one",
    "small_group",
    "either",
)

TIME_BLOCKS: Dict[str, Tuple[Tuple[str, int, int, int], ...]] = {
    "study": (
        ("mon", 19, 0, 4),
        ("tue", 19, 0, 4),
        ("wed", 19, 0, 4),
        ("thu", 19, 0, 4),
        ("fri", 19, 0, 4),
        ("sat", 14, 0, 5),
        ("sun", 14, 0, 5),
    ),
    "sport": (
        ("mon", 18, 30, 4),
        ("tue", 18, 30, 4),
        ("wed", 18, 30, 4),
        ("thu", 18, 30, 4),
        ("fri", 18, 30, 4),
        ("sat", 9, 0, 4),
        ("sun", 9, 0, 4),
    ),
    "interest": (
        ("fri", 19, 0, 5),
        ("sat", 10, 0, 5),
        ("sat", 14, 0, 6),
        ("sat", 18, 0, 5),
        ("sun", 10, 0, 5),
        ("sun", 14, 0, 6),
    ),
}

ACTIVITY_INTERESTS: Dict[str, Tuple[str, ...]] = {
    "python": ("programming", "ai"),
    "higher_mathematics": ("mathematics", "research"),
    "linear_algebra": ("mathematics", "ai"),
    "english_cet": ("languages", "reading"),
    "ielts_toefl": ("languages", "reading"),
    "algorithms": ("programming", "mathematics"),
    "course_project": ("programming", "research"),
    "general_study": ("reading", "research"),
    "running": ("running", "outdoors"),
    "badminton": ("ball_sports", "fitness"),
    "swimming": ("fitness", "outdoors"),
    "fitness": ("fitness", "outdoors"),
    "cycling": ("outdoors", "fitness"),
    "basketball": ("ball_sports", "fitness"),
    "table_tennis": ("ball_sports", "fitness"),
    "movie": ("movies", "art"),
    "exhibition": ("art", "city_exploration"),
    "lecture": ("lectures", "research"),
    "photography": ("photography", "art"),
    "board_games": ("board_games", "city_exploration"),
    "live_music": ("music", "art"),
    "food_exploration": ("food", "city_exploration"),
    "city_walk": ("city_exploration", "photography"),
}

ACTIVITY_LOCATIONS: Dict[str, Tuple[str, ...]] = {
    "study": ("pku_library", "teaching_building", "online"),
    "sport": ("sports_field", "gymnasium"),
    "interest": ("campus_common_area", "off_campus_haidian"),
}

DESCRIPTION_TEMPLATES: Dict[str, Tuple[str, ...]] = {
    "study": (
        "我习惯按计划完成本周学习任务，希望保持稳定节奏。",
        "我想通过固定结伴提高执行力，也愿意适度交流问题。",
        "我更关注实际学习效果，希望每次活动都能完成明确目标。",
    ),
    "sport": (
        "我希望保持规律运动，重视安全和彼此节奏合适。",
        "我想通过结伴提高运动积极性，同时享受活动过程。",
        "我会按约定时间参加，希望一起逐步提升运动状态。",
    ),
    "interest": (
        "我喜欢探索校园及周边活动，希望安排轻松但不随意。",
        "我愿意认识兴趣相近的同学，一起完成具体活动计划。",
        "我重视活动体验，也希望提前沟通时间、地点和大致安排。",
    ),
}

EXPECTATION_TEMPLATES: Dict[str, Tuple[str, ...]] = {
    "study": (
        "希望对方时间稳定、目标相近，可以互相提醒但不过度施压。",
        "希望找到愿意按计划行动并能交流学习进度的搭子。",
        "期待对方认真守时，一起完成本周的具体学习目标。",
    ),
    "sport": (
        "希望对方水平和强度接近，守时并尊重彼此运动节奏。",
        "期待找到可以稳定参加、不会临时爽约的运动搭子。",
        "希望一起安全运动，以持续行动为主而不是盲目竞争。",
    ),
    "interest": (
        "希望对方兴趣相近、沟通自然，并愿意一起确定活动安排。",
        "期待找到守时友好、预算和行动节奏比较合适的同学。",
        "希望彼此尊重选择，把共同兴趣真正转化为一次行动。",
    ),
}


def _expand_block(day: str, hour: int, minute: int, length: int) -> List[str]:
    slots: List[str] = []
    current_hour = hour
    current_minute = minute
    for _ in range(length):
        code = f"{day}_{current_hour:02d}_{current_minute:02d}"
        if code not in vocab.TIME_SLOTS:
            raise ValueError(f"无效模拟时间片：{code}")
        slots.append(code)
        current_minute += 30
        if current_minute == 60:
            current_hour += 1
            current_minute = 0
    return slots


def _nearby_levels(level: str) -> List[str]:
    level_codes = list(vocab.LEVELS)
    index = level_codes.index(level)
    start = max(0, index - 1)
    end = min(len(level_codes), index + 2)
    return level_codes[start:end]


def _choose_interests(
    activity: str, match_type: str, rng: random.Random
) -> List[str]:
    category_pool = {
        "study": [
            "reading",
            "research",
            "programming",
            "mathematics",
            "languages",
            "physics",
            "writing",
        ],
        "sport": ["running", "ball_sports", "fitness", "outdoors"],
        "interest": [
            "movies",
            "art",
            "music",
            "photography",
            "board_games",
            "food",
            "city_exploration",
            "lectures",
            "travel",
            "volunteering",
        ],
    }[match_type]
    selected = list(ACTIVITY_INTERESTS.get(activity, tuple(category_pool[:2])))
    for candidate in rng.sample(category_pool, k=min(2, len(category_pool))):
        if candidate not in selected:
            selected.append(candidate)
    return selected[:4]


def _choose_locations(
    match_type: str, pair_index: int, member_in_pair: int, rng: random.Random
) -> List[str]:
    pool = list(ACTIVITY_LOCATIONS[match_type])
    primary = pool[pair_index % len(pool)]
    locations = [primary]
    # Pair members always share a primary location; a second location introduces
    # realistic flexibility without destroying the guaranteed compatible edge.
    if rng.random() < 0.65:
        secondary = pool[(pair_index + member_in_pair + 1) % len(pool)]
        if secondary not in locations:
            locations.append(secondary)
    return locations


def _choose_restrictions(
    locations: Sequence[str], group_size: str, planning_style: str, rng: random.Random
) -> List[str]:
    restrictions: List[str] = []
    if "off_campus_haidian" not in locations and rng.random() < 0.35:
        restrictions.append("no_off_campus")
    if group_size == "one_to_one" and rng.random() < 0.30:
        restrictions.append("no_group_activity")
    if planning_style == "planned" and rng.random() < 0.35:
        restrictions.append("no_last_minute_cancel")
    if rng.random() < 0.12:
        restrictions.append("no_high_intensity")
    return restrictions


def _make_answers(
    match_type: str,
    local_index: int,
    rng: random.Random,
) -> Dict[str, Any]:
    pair_index = local_index // 2
    member_in_pair = local_index % 2
    activities = list(vocab.ACTIVITIES[match_type])
    activity = activities[pair_index % len(activities)]

    blocks = TIME_BLOCKS[match_type]
    primary_block = blocks[pair_index % len(blocks)]
    available_times = _expand_block(*primary_block)
    if rng.random() < 0.75:
        secondary_block = blocks[(pair_index + 2 + member_in_pair) % len(blocks)]
        available_times.extend(_expand_block(*secondary_block))
    time_order = {code: index for index, code in enumerate(vocab.TIME_SLOTS)}
    available_times = sorted(set(available_times), key=time_order.get)

    level_codes = list(vocab.LEVELS)
    self_level = level_codes[pair_index % len(level_codes)]
    acceptable_levels = _nearby_levels(self_level)
    locations = _choose_locations(
        match_type, pair_index, member_in_pair, rng
    )

    # Both members of a generated pair share this hard preference. Soft fields
    # still vary, so the algorithm has meaningful ranking work to do.
    group_size = GROUP_SIZE_PATTERN[pair_index % len(GROUP_SIZE_PATTERN)]
    communication_style = rng.choice(list(vocab.COMMUNICATION_STYLES))
    planning_style = rng.choices(
        list(vocab.PLANNING_STYLES), weights=(0.45, 0.40, 0.15), k=1
    )[0]
    organization_role = (
        "organizer" if member_in_pair == 0 else "participant"
    )
    if rng.random() < 0.30:
        organization_role = "balanced"

    goal_codes = list(vocab.GOALS[match_type])
    goal = goal_codes[(pair_index + member_in_pair) % len(goal_codes)]
    priorities = rng.sample(list(vocab.PREFERENCE_DIMENSIONS), k=3)

    return {
        "match_type": match_type,
        "activity": activity,
        "available_times": available_times,
        "min_session_minutes": rng.choice([60, 60, 60, 90]),
        "acceptable_locations": locations,
        "group_size_preference": group_size,
        "self_level": self_level,
        "acceptable_partner_levels": acceptable_levels,
        "hard_restrictions": _choose_restrictions(
            locations, group_size, planning_style, rng
        ),
        "goal": goal,
        "intensity": max(1, min(5, (pair_index % 5) + rng.choice([0, 1]))),
        "communication_style": communication_style,
        "planning_style": planning_style,
        "supervision_preference": rng.randint(1, 5),
        "punctuality_importance": rng.choices(
            [2, 3, 4, 5], weights=[0.05, 0.20, 0.45, 0.30], k=1
        )[0],
        "cancellation_tolerance": rng.choices(
            [1, 2, 3, 4, 5], weights=[0.10, 0.30, 0.35, 0.20, 0.05], k=1
        )[0],
        "organization_role": organization_role,
        "interests": _choose_interests(activity, match_type, rng),
        "self_description": rng.choice(DESCRIPTION_TEMPLATES[match_type]),
        "partner_expectation": rng.choice(EXPECTATION_TEMPLATES[match_type]),
        "preference_priorities": priorities,
    }


def generate_users(count: int, seed: int = DEFAULT_SEED) -> List[Dict[str, Any]]:
    """Generate ``count`` valid users with reproducible compatible clusters."""

    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("count必须是正整数")
    if count > 9999:
        raise ValueError("Schema v1最多支持9999个格式化用户ID")

    rng = random.Random(seed)
    local_counts: Counter[str] = Counter()
    users: List[Dict[str, Any]] = []
    for index in range(count):
        match_type = MATCH_TYPE_CYCLE[index % len(MATCH_TYPE_CYCLE)]
        local_index = local_counts[match_type]
        answers = _make_answers(match_type, local_index, rng)
        profile = build_profile(answers, user_id=f"U{index + 1:04d}")
        users.append(profile)
        local_counts[match_type] += 1

    report = validate_dataset(users)
    if not report["is_valid"]:
        raise RuntimeError(f"模拟数据生成后校验失败：{report}")
    return users


def generate_and_save(
    count: int,
    output_path: str | Path,
    seed: int = DEFAULT_SEED,
) -> List[Dict[str, Any]]:
    users = generate_users(count, seed=seed)
    save_users(users, output_path)
    return users


def generate_default_datasets(
    output_dir: str | Path = Path(__file__).resolve().parent / "generated",
    sizes: Iterable[int] = DEFAULT_SIZES,
    seed: int = DEFAULT_SEED,
) -> Dict[str, List[Dict[str, Any]]]:
    destination = Path(output_dir)
    datasets: Dict[str, List[Dict[str, Any]]] = {}
    requested_sizes = list(sizes)
    for size in requested_sizes:
        name = f"users_{size:03d}"
        users = generate_and_save(
            size,
            destination / f"{name}.csv",
            seed=seed,
        )
        datasets[name] = users

    baseline_alias = None
    if "users_050" in datasets and destination.name == "generated":
        baseline_alias = destination.parent / "users.csv"
        save_users(datasets["users_050"], baseline_alias)

    write_quality_report(
        datasets,
        destination / "quality_report.json",
        metadata={
            "schema_version": SCHEMA_VERSION,
            "seed": seed,
            "sizes": requested_sizes,
            "baseline_alias": str(baseline_alias) if baseline_alias else None,
        },
    )
    return datasets


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成CampusMate模拟用户数据")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--sizes", nargs="+", type=int, default=list(DEFAULT_SIZES))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    generated = generate_default_datasets(
        output_dir=arguments.output_dir,
        sizes=arguments.sizes,
        seed=arguments.seed,
    )
    for dataset_name, dataset_users in generated.items():
        print(f"{dataset_name}: {len(dataset_users)} users")
