"""Canonical codes and Chinese labels shared by all CampusMate modules.

Program logic must use the stable English codes in this file. Chinese labels are
display-only and may be changed without changing the data contract.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Mapping, Tuple


CUSTOM_VALUE_PREFIX = "custom:"
MAX_CUSTOM_VALUE_LENGTH = 60


MATCH_TYPES: Dict[str, str] = {
    "study": "学习搭子",
    "sport": "运动搭子",
    "interest": "兴趣活动搭子",
}

ACTIVITIES: Dict[str, Dict[str, str]] = {
    "study": {
        "python": "Python学习",
        "physics": "物理",
        "chemistry": "化学",
        "biology": "生物",
        "higher_mathematics": "高等数学",
        "linear_algebra": "线性代数",
        "statistics": "概率与统计",
        "economics": "经济学",
        "law": "法学",
        "history": "历史",
        "academic_writing": "论文与学术写作",
        "english_cet": "四六级英语",
        "ielts_toefl": "雅思/托福",
        "other_languages": "其他语言学习",
        "algorithms": "算法题练习",
        "data_science": "数据科学/机器学习",
        "course_project": "课程项目",
        "general_study": "综合自习",
    },
    "sport": {
        "running": "跑步",
        "badminton": "羽毛球",
        "swimming": "游泳",
        "fitness": "健身",
        "cycling": "骑行",
        "basketball": "篮球",
        "table_tennis": "乒乓球",
        "football": "足球",
        "volleyball": "排球",
        "tennis": "网球",
        "frisbee": "飞盘",
        "hiking": "徒步",
        "yoga": "瑜伽",
        "dance": "舞蹈",
        "climbing": "攀岩",
    },
    "interest": {
        "movie": "看电影",
        "exhibition": "逛展览",
        "lecture": "听讲座",
        "photography": "摄影",
        "board_games": "桌游",
        "live_music": "音乐演出",
        "food_exploration": "探店",
        "city_walk": "城市探索",
        "reading": "读书交流",
        "karaoke": "唱歌/KTV",
        "theatre": "戏剧/演出",
        "museum": "博物馆",
        "gaming": "电子游戏",
        "travel": "旅行",
        "cooking": "烹饪",
        "volunteering": "志愿活动",
        "coffee_chat": "Coffee Chat",
    },
}

GOALS: Dict[str, Dict[str, str]] = {
    "study": {
        "exam_prep": "考试复习",
        "skill_improvement": "提升技能",
        "mutual_accountability": "互相监督",
        "homework_project": "完成作业或项目",
        "habit_building": "养成学习习惯",
    },
    "sport": {
        "fitness": "增强体能",
        "habit_building": "养成运动习惯",
        "skill_improvement": "提升技术",
        "recreation": "休闲放松",
        "competition": "竞技训练",
    },
    "interest": {
        "experience": "体验活动",
        "social_connection": "认识同好",
        "skill_improvement": "提升相关技能",
        "relaxation": "休闲放松",
        "exploration": "探索新事物",
    },
}

# Common places improve discoverability; custom entries cover the open world.
LOCATIONS: Dict[str, str] = {
    "pku_library": "北京大学图书馆",
    "teaching_building": "校内教学楼",
    "science_teaching_building": "理科教学楼",
    "second_teaching_building": "第二教学楼",
    "sports_field": "校内操场",
    "may_fourth_sports_field": "五四体育场",
    "gymnasium": "校内体育馆",
    "choi_kai_yau_gymnasium": "邱德拔体育馆",
    "campus_common_area": "校内公共区域",
    "new_sun_student_center": "新太阳学生中心",
    "pku_hall": "百周年纪念讲堂",
    "yingjie_exchange_center": "英杰交流中心",
    "weiming_lake": "未名湖",
    "campus_canteen": "校内食堂",
    "haidian_park": "海淀公园",
    "zhongguancun": "中关村",
    "wudaokou": "五道口",
    "off_campus_haidian": "海淀校外区域",
    "online": "线上",
}

OFF_CAMPUS_LOCATION_CODES = frozenset(
    {"haidian_park", "zhongguancun", "wudaokou", "off_campus_haidian"}
)

LEVELS: Dict[str, str] = {
    "novice": "零基础/新手",
    "basic": "入门",
    "intermediate": "中等",
    "advanced": "熟练/进阶",
}

GROUP_SIZES: Dict[str, str] = {
    "one_to_one": "一对一",
    "small_group": "3—5人小组",
    "either": "均可",
}

COMMUNICATION_STYLES: Dict[str, str] = {
    "quiet": "以安静陪伴为主",
    "balanced": "安静与交流各半",
    "interactive": "希望经常交流",
}

PLANNING_STYLES: Dict[str, str] = {
    "planned": "喜欢提前安排",
    "flexible": "有基本计划但可调整",
    "spontaneous": "偏好临时决定",
}

ORGANIZATION_ROLES: Dict[str, str] = {
    "organizer": "愿意主动组织",
    "balanced": "组织和配合均可",
    "participant": "更愿意配合安排",
}

HARD_RESTRICTIONS: Dict[str, str] = {
    "no_off_campus": "不接受校外活动",
    "no_evening": "不接受晚间活动",
    "no_early_morning": "不接受早间活动",
    "no_high_intensity": "不接受高强度活动",
    "no_group_activity": "只接受一对一",
    "no_last_minute_cancel": "不接受临时取消",
}

INTEREST_TAGS: Dict[str, str] = {
    "ai": "人工智能",
    "programming": "编程",
    "mathematics": "数学",
    "languages": "语言学习",
    "reading": "阅读",
    "research": "科研",
    "running": "跑步",
    "ball_sports": "球类运动",
    "fitness": "健身",
    "outdoors": "户外",
    "movies": "电影",
    "art": "艺术",
    "music": "音乐",
    "photography": "摄影",
    "board_games": "桌游",
    "food": "美食",
    "city_exploration": "城市探索",
    "lectures": "讲座",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "economics": "经济学",
    "law": "法学",
    "history": "历史",
    "writing": "写作",
    "volunteering": "志愿服务",
    "travel": "旅行",
    "dance": "舞蹈",
    "gaming": "电子游戏",
}

PREFERENCE_DIMENSIONS: Dict[str, str] = {
    "time": "时间重合",
    "goal": "活动目标",
    "level": "活动水平",
    "planning": "行动节奏",
    "interest": "兴趣标签",
    "communication": "交流方式",
    "text": "文本语义",
}

RATING_LABELS: Dict[int, str] = {
    1: "很低",
    2: "较低",
    3: "中等",
    4: "较高",
    5: "很高",
}

WEEKDAYS: Tuple[Tuple[str, str], ...] = (
    ("mon", "周一"),
    ("tue", "周二"),
    ("wed", "周三"),
    ("thu", "周四"),
    ("fri", "周五"),
    ("sat", "周六"),
    ("sun", "周日"),
)


def _build_time_slots() -> Dict[str, str]:
    slots: Dict[str, str] = {}
    for day_code, day_label in WEEKDAYS:
        start_hour = 7 if day_code not in {"sat", "sun"} else 8
        for hour in range(start_hour, 23):
            for minute in (0, 30):
                next_hour = hour + (1 if minute == 30 else 0)
                next_minute = 0 if minute == 30 else 30
                code = f"{day_code}_{hour:02d}_{minute:02d}"
                label = (
                    f"{day_label} {hour:02d}:{minute:02d}—"
                    f"{next_hour:02d}:{next_minute:02d}"
                )
                slots[code] = label
    return slots


TIME_SLOTS: Dict[str, str] = _build_time_slots()


def options(mapping: Mapping[object, str]) -> List[Dict[str, object]]:
    """Convert a code-to-label mapping into UI-ready option dictionaries."""

    return [{"value": value, "label": label} for value, label in mapping.items()]


def flatten_activity_codes() -> Iterable[str]:
    for category_activities in ACTIVITIES.values():
        yield from category_activities


def normalize_free_text(value: object) -> str:
    """Normalize harmless text differences while preserving readable content."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.strip().split())


def custom_value(value: object) -> str:
    """Encode one user-defined questionnaire value in the stable contract."""

    text = normalize_free_text(value)
    if text.startswith(CUSTOM_VALUE_PREFIX):
        text = normalize_free_text(text[len(CUSTOM_VALUE_PREFIX) :])
    return f"{CUSTOM_VALUE_PREFIX}{text}" if text else ""


def is_custom_value(value: object) -> bool:
    text = normalize_free_text(value)
    if not text.startswith(CUSTOM_VALUE_PREFIX):
        return False
    payload = text[len(CUSTOM_VALUE_PREFIX) :]
    return bool(payload) and len(payload) <= MAX_CUSTOM_VALUE_LENGTH and not re.search(
        r"[\r\n\t]", payload
    )


def display_value(value: object, mapping: Mapping[object, str] | None = None) -> str:
    """Return a readable label for built-in and user-defined values."""

    if mapping is not None:
        try:
            if value in mapping:
                return str(mapping[value])
        except TypeError:
            pass
    text = normalize_free_text(value)
    if text.startswith(CUSTOM_VALUE_PREFIX):
        return text[len(CUSTOM_VALUE_PREFIX) :]
    return text


def comparison_key(value: object) -> str:
    """Canonical key used only for conservative exact matching."""

    return display_value(value).casefold()


def is_off_campus_location(value: object) -> bool:
    """Treat unknown custom places conservatively as potentially off campus."""

    return value in OFF_CAMPUS_LOCATION_CODES or is_custom_value(value)


def activity_belongs_to(match_type: str, activity: str) -> bool:
    return activity in ACTIVITIES.get(match_type, {}) or is_custom_value(activity)


def goal_belongs_to(match_type: str, goal: str) -> bool:
    return goal in GOALS.get(match_type, {})
