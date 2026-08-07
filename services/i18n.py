"""Display-only Chinese/English localization for CampusMate.

Part 1's canonical profile codes remain unchanged. This module only translates
labels shown by Streamlit, so switching language never changes saved answers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


CHINESE = "zh"
ENGLISH = "en"


def tr(language: str, chinese: str, english: str) -> str:
    """Return one of two display strings for the active language."""

    return english if language == ENGLISH else chinese


QUESTION_LABELS_EN = {
    "match_type": "What kind of campus partner are you looking for?",
    "activity": "What activity would you like to do this week?",
    "available_times": "When are you available this week?",
    "acceptable_locations": "Which locations are acceptable to you?",
    "group_size_preference": "What group size do you prefer?",
    "self_level": "What is your current level in this activity?",
    "acceptable_partner_levels": "Which partner levels are acceptable to you?",
    "hard_restrictions": "Which situations are unacceptable to you?",
    "goal": "What is your main goal for this activity?",
    "intensity": "What activity intensity do you prefer?",
    "communication_style": "What communication style do you prefer?",
    "planning_style": "What planning style do you prefer?",
    "supervision_preference": "How much mutual supervision or reminding do you want?",
    "punctuality_importance": "How important is punctuality to you?",
    "cancellation_tolerance": "How tolerant are you of last-minute cancellations?",
    "organization_role": "What role would you prefer to take in the activity?",
    "interests": "Select your interest tags.",
    "self_description": "Briefly describe your activity habits.",
    "partner_expectation": "Describe the kind of partner you hope to find.",
    "preference_priorities": "Select your top matching priorities (up to three).",
}

QUESTION_HELP_EN = {
    "match_type": "The first version supports study, sports, and interest activities.",
    "activity": "Options change according to your selected partner type.",
    "available_times": "Each option is a 30-minute slot. A continuous overlap of at least 60 minutes is required by default.",
    "acceptable_locations": "Selecting an off-campus Haidian location means that off-campus activities are acceptable.",
    "goal": "Options change according to your selected partner type.",
    "cancellation_tolerance": "1 means very difficult to accept; 5 means relatively acceptable.",
}

MATCH_TYPES_EN = {
    "study": "Study Partner",
    "sport": "Sports Partner",
    "interest": "Interest Activity Partner",
}

ACTIVITIES_EN = {
    "python": "Python Study",
    "higher_mathematics": "Advanced Mathematics",
    "linear_algebra": "Linear Algebra",
    "english_cet": "CET English",
    "ielts_toefl": "IELTS / TOEFL",
    "algorithms": "Algorithm Practice",
    "course_project": "Course Project",
    "general_study": "General Study Session",
    "running": "Running",
    "badminton": "Badminton",
    "swimming": "Swimming",
    "fitness": "Fitness",
    "cycling": "Cycling",
    "basketball": "Basketball",
    "table_tennis": "Table Tennis",
    "movie": "Watching a Movie",
    "exhibition": "Visiting an Exhibition",
    "lecture": "Attending a Lecture",
    "photography": "Photography",
    "board_games": "Board Games",
    "live_music": "Live Music",
    "food_exploration": "Food Exploration",
    "city_walk": "City Exploration",
}

GOALS_EN = {
    "exam_prep": "Exam Preparation",
    "skill_improvement": "Skill Improvement",
    "mutual_accountability": "Mutual Accountability",
    "homework_project": "Complete Homework or a Project",
    "habit_building": "Build a Habit",
    "fitness": "Improve Fitness",
    "recreation": "Recreation",
    "competition": "Competition Training",
    "experience": "Experience the Activity",
    "social_connection": "Meet People with Shared Interests",
    "relaxation": "Relaxation",
    "exploration": "Explore Something New",
}

LOCATIONS_EN = {
    "pku_library": "Peking University Library",
    "teaching_building": "Campus Teaching Building",
    "sports_field": "Campus Sports Field",
    "gymnasium": "Campus Gymnasium",
    "campus_common_area": "Campus Common Area",
    "off_campus_haidian": "Off-campus Area in Haidian",
    "online": "Online",
}

LEVELS_EN = {
    "novice": "Beginner / No Experience",
    "basic": "Basic",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}

GROUP_SIZES_EN = {
    "one_to_one": "One-to-one",
    "small_group": "Small Group of 3–5",
    "either": "Either",
}

COMMUNICATION_STYLES_EN = {
    "quiet": "Mostly Quiet Company",
    "balanced": "A Balance of Quiet Time and Discussion",
    "interactive": "Frequent Interaction",
}

PLANNING_STYLES_EN = {
    "planned": "Plan in Advance",
    "flexible": "Basic Plan with Flexibility",
    "spontaneous": "Prefer Spontaneous Decisions",
}

ORGANIZATION_ROLES_EN = {
    "organizer": "Take the Initiative to Organize",
    "balanced": "Either Organize or Cooperate",
    "participant": "Prefer to Follow Arrangements",
}

HARD_RESTRICTIONS_EN = {
    "no_off_campus": "No Off-campus Activities",
    "no_evening": "No Evening Activities",
    "no_early_morning": "No Early-morning Activities",
    "no_high_intensity": "No High-intensity Activities",
    "no_group_activity": "One-to-one Only",
    "no_last_minute_cancel": "No Last-minute Cancellations",
}

INTEREST_TAGS_EN = {
    "ai": "Artificial Intelligence",
    "programming": "Programming",
    "mathematics": "Mathematics",
    "languages": "Language Learning",
    "reading": "Reading",
    "research": "Research",
    "running": "Running",
    "ball_sports": "Ball Sports",
    "fitness": "Fitness",
    "outdoors": "Outdoors",
    "movies": "Movies",
    "art": "Art",
    "music": "Music",
    "photography": "Photography",
    "board_games": "Board Games",
    "food": "Food",
    "city_exploration": "City Exploration",
    "lectures": "Lectures",
}

PREFERENCE_DIMENSIONS_EN = {
    "time": "Time Overlap",
    "goal": "Activity Goal",
    "level": "Activity Level",
    "planning": "Planning Style",
    "interest": "Interest Tags",
    "communication": "Communication Style",
    "text": "Text Meaning",
}

RATING_LABELS_EN = {
    1: "Very Low",
    2: "Low",
    3: "Medium",
    4: "High",
    5: "Very High",
}

WEEKDAYS_EN = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

OPTION_MAPS_EN = {
    "match_type": MATCH_TYPES_EN,
    "activity": ACTIVITIES_EN,
    "acceptable_locations": LOCATIONS_EN,
    "group_size_preference": GROUP_SIZES_EN,
    "self_level": LEVELS_EN,
    "acceptable_partner_levels": LEVELS_EN,
    "hard_restrictions": HARD_RESTRICTIONS_EN,
    "goal": GOALS_EN,
    "communication_style": COMMUNICATION_STYLES_EN,
    "planning_style": PLANNING_STYLES_EN,
    "organization_role": ORGANIZATION_ROLES_EN,
    "interests": INTEREST_TAGS_EN,
    "preference_priorities": PREFERENCE_DIMENSIONS_EN,
    "intensity": RATING_LABELS_EN,
    "supervision_preference": RATING_LABELS_EN,
    "punctuality_importance": RATING_LABELS_EN,
    "cancellation_tolerance": RATING_LABELS_EN,
}

FIELD_LABELS_EN = {
    **QUESTION_LABELS_EN,
    "schema_version": "Schema Version",
    "user_id": "Anonymous ID",
    "min_session_minutes": "Minimum Session Length",
    "allow_off_campus": "Off-campus Permission",
    "preference_weights": "Preference Weights",
}

ISSUE_MESSAGES_EN = {
    "missing": "This required field is missing.",
    "sensitive_field": "Sensitive personal information must not be stored.",
    "unknown_field": "This field is not part of the current profile schema.",
    "unsupported_version": "The profile schema version is not supported.",
    "invalid_format": "The value has an invalid format.",
    "unknown_value": "The value is not recognized.",
    "category_mismatch": "The value does not belong to the selected partner type.",
    "invalid_type": "The value has an invalid data type.",
    "empty_list": "Select at least one item.",
    "invalid_item": "One or more selected items are invalid.",
    "duplicate_item": "Duplicate selections are not allowed.",
    "invalid_duration": "The duration must be a multiple of 30 minutes between 30 and 240.",
    "derived_value_mismatch": "This derived value does not match the selected locations.",
    "out_of_range": "The value must be an integer from 1 to 5.",
    "too_short": "The text is too short.",
    "too_long": "The text is too long.",
    "invalid_keys": "The preference dimensions are incomplete or invalid.",
    "invalid_weight": "A preference weight is invalid.",
    "invalid_sum": "All preference weights must add up to 1.",
}


def _time_slot_label(value: str) -> str | None:
    parts = value.split("_")
    if len(parts) != 3 or parts[0] not in WEEKDAYS_EN:
        return None
    try:
        hour, minute = int(parts[1]), int(parts[2])
    except ValueError:
        return None
    end_hour = hour + (1 if minute == 30 else 0)
    end_minute = 0 if minute == 30 else 30
    return f"{WEEKDAYS_EN[parts[0]]} {hour:02d}:{minute:02d}–{end_hour:02d}:{end_minute:02d}"


def option_label(question_id: str, value: Any, original: str, language: str) -> str:
    """Translate one questionnaire option while preserving its canonical code."""

    if language != ENGLISH:
        return original
    if question_id == "available_times" and isinstance(value, str):
        return _time_slot_label(value) or original
    return str(OPTION_MAPS_EN.get(question_id, {}).get(value, original))


def localize_questions(
    questions: Sequence[Mapping[str, Any]], language: str
) -> list[dict[str, Any]]:
    """Return a display-only translated copy of Part 1 question metadata."""

    localized = deepcopy(list(questions))
    if language != ENGLISH:
        return localized
    for question in localized:
        question_id = str(question["id"])
        question["label"] = QUESTION_LABELS_EN.get(question_id, question["label"])
        if question.get("help_text"):
            question["help_text"] = QUESTION_HELP_EN.get(
                question_id, question["help_text"]
            )
        for option in question.get("options", []):
            option["label"] = option_label(
                question_id,
                option["value"],
                str(option["label"]),
                language,
            )
    return localized


def weekday_label(day_code: str, chinese_label: str, language: str) -> str:
    return WEEKDAYS_EN.get(day_code, chinese_label) if language == ENGLISH else chinese_label


def field_label(field: str, chinese_label: str, language: str) -> str:
    return FIELD_LABELS_EN.get(field, chinese_label) if language == ENGLISH else chinese_label


def issue_message(code: str, chinese_message: str, language: str) -> str:
    return ISSUE_MESSAGES_EN.get(code, "The value is invalid.") if language == ENGLISH else chinese_message
