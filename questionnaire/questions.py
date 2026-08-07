"""Declarative questionnaire metadata for CampusMate.

The front end should render these definitions instead of duplicating question
text or options. Exactly twenty questions are exposed for each match type.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from data import vocabulary as vocab


ALL_MATCH_TYPES = list(vocab.MATCH_TYPES)


def _base_questions() -> List[Dict[str, Any]]:
    rating_options = vocab.options(vocab.RATING_LABELS)
    return [
        {
            "id": "match_type",
            "label": "你想寻找哪一类校园搭子？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "hard",
            "options": vocab.options(vocab.MATCH_TYPES),
            "help_text": "第一版支持学习、运动和兴趣活动三类场景。",
        },
        {
            "id": "activity",
            "label": "你本周想进行什么具体活动？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "hard",
            "options": [],
            "help_text": "选项会根据搭子类型变化。",
        },
        {
            "id": "available_times",
            "label": "你本周哪些时间有空？",
            "input_type": "multi_select",
            "required": True,
            "constraint_type": "hard",
            "options": vocab.options(vocab.TIME_SLOTS),
            "help_text": "每个选项代表连续30分钟；系统默认至少需要连续60分钟重合。",
        },
        {
            "id": "acceptable_locations",
            "label": "你可以接受哪些活动地点？",
            "input_type": "multi_select",
            "required": True,
            "constraint_type": "hard",
            "options": vocab.options(vocab.LOCATIONS),
            "help_text": "选择海淀校外区域即代表接受校外活动。",
        },
        {
            "id": "group_size_preference",
            "label": "你希望采用什么人数形式？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "hard",
            "options": vocab.options(vocab.GROUP_SIZES),
        },
        {
            "id": "self_level",
            "label": "你目前在这项活动中的水平如何？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "hard",
            "options": vocab.options(vocab.LEVELS),
        },
        {
            "id": "acceptable_partner_levels",
            "label": "你能接受搭子处于哪些水平？",
            "input_type": "multi_select",
            "required": True,
            "constraint_type": "hard",
            "options": vocab.options(vocab.LEVELS),
        },
        {
            "id": "hard_restrictions",
            "label": "你有哪些明确不能接受的情况？",
            "input_type": "multi_select",
            "required": False,
            "constraint_type": "hard",
            "options": vocab.options(vocab.HARD_RESTRICTIONS),
        },
        {
            "id": "goal",
            "label": "你参加这项活动的主要目标是什么？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "soft",
            "options": [],
            "help_text": "选项会根据搭子类型变化。",
        },
        {
            "id": "intensity",
            "label": "你期望的活动强度是多少？",
            "input_type": "rating",
            "required": True,
            "constraint_type": "soft",
            "options": rating_options,
        },
        {
            "id": "communication_style",
            "label": "你偏好的交流方式是什么？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "soft",
            "options": vocab.options(vocab.COMMUNICATION_STYLES),
        },
        {
            "id": "planning_style",
            "label": "你偏好的行动规划方式是什么？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "soft",
            "options": vocab.options(vocab.PLANNING_STYLES),
        },
        {
            "id": "supervision_preference",
            "label": "你希望彼此监督或提醒的程度是多少？",
            "input_type": "rating",
            "required": True,
            "constraint_type": "soft",
            "options": rating_options,
        },
        {
            "id": "punctuality_importance",
            "label": "你有多看重对方准时？",
            "input_type": "rating",
            "required": True,
            "constraint_type": "soft",
            "options": rating_options,
        },
        {
            "id": "cancellation_tolerance",
            "label": "你对临时取消活动的容忍度是多少？",
            "input_type": "rating",
            "required": True,
            "constraint_type": "soft",
            "options": rating_options,
            "help_text": "1代表很难接受，5代表较能接受。",
        },
        {
            "id": "organization_role",
            "label": "你在活动中更愿意承担什么角色？",
            "input_type": "single_select",
            "required": True,
            "constraint_type": "soft",
            "options": vocab.options(vocab.ORGANIZATION_ROLES),
        },
        {
            "id": "interests",
            "label": "请选择你的兴趣标签。",
            "input_type": "multi_select",
            "required": True,
            "constraint_type": "soft",
            "options": vocab.options(vocab.INTEREST_TAGS),
            "validation": {"min_items": 1, "max_items": 6},
        },
        {
            "id": "self_description",
            "label": "请简要描述你的活动习惯。",
            "input_type": "long_text",
            "required": True,
            "constraint_type": "soft",
            "validation": {"min_length": 5, "max_length": 500},
        },
        {
            "id": "partner_expectation",
            "label": "请描述你希望找到怎样的搭子。",
            "input_type": "long_text",
            "required": True,
            "constraint_type": "soft",
            "validation": {"min_length": 5, "max_length": 500},
        },
        {
            "id": "preference_priorities",
            "label": "请选择你最看重的匹配因素（最多三项）。",
            "input_type": "multi_select",
            "required": True,
            "constraint_type": "soft",
            "options": vocab.options(vocab.PREFERENCE_DIMENSIONS),
            "validation": {"min_items": 1, "max_items": 3},
        },
    ]


def get_questions(match_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return UI-ready question definitions.

    When ``match_type`` is provided, activity and goal options are narrowed to
    that scenario. Without it, those two option lists remain empty until the
    user selects a category.
    """

    if match_type is not None and match_type not in vocab.MATCH_TYPES:
        raise ValueError(f"未知匹配类型：{match_type}")

    questions = deepcopy(_base_questions())
    if match_type is None:
        return questions

    for question in questions:
        question["applies_to"] = ALL_MATCH_TYPES
        if question["id"] == "activity":
            question["options"] = vocab.options(vocab.ACTIVITIES[match_type])
        elif question["id"] == "goal":
            question["options"] = vocab.options(vocab.GOALS[match_type])
    return questions


QUESTIONS = get_questions()
