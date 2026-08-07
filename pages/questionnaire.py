"""Dynamic CampusMate questionnaire backed by the Part 1 metadata API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import streamlit as st

from data import vocabulary as vocab
from data.data_loader import load_users
from data.schema import ProfileValidationError
from questionnaire.profile_builder import build_profile
from questionnaire.questions import get_questions
from services.i18n import (
    CHINESE,
    field_label,
    issue_message,
    localize_questions,
    tr,
    weekday_label,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TYPE_PRESENTATION = {
    "study": (
        "📚",
        "学习搭子",
        "Study Partner",
        "一起推进本周的学习目标",
        "Work together toward this week's study goal",
    ),
    "sport": (
        "🏃",
        "运动搭子",
        "Sports Partner",
        "找到项目、水平和强度合适的伙伴",
        "Find a partner with a compatible activity, level, and intensity",
    ),
    "interest": (
        "🎨",
        "兴趣活动搭子",
        "Interest Activity Partner",
        "把共同兴趣变成一次真实行动",
        "Turn a shared interest into a real activity",
    ),
}

QUESTION_GROUPS = (
    (
        ("① 本周行动", "① This Week's Activity"),
        ("先确认活动、连续时间和地点等硬条件。", "Confirm the activity, continuous availability, location, and other hard constraints."),
        {
            "activity",
            "available_times",
            "acceptable_locations",
            "group_size_preference",
            "self_level",
        },
    ),
    (
        ("② 搭子要求", "② Partner Requirements"),
        ("说明你能接受的搭子水平与明确限制。", "Specify acceptable partner levels and explicit restrictions."),
        {"acceptable_partner_levels", "hard_restrictions", "goal"},
    ),
    (
        ("③ 相处方式", "③ Interaction Style"),
        ("这些软性偏好将参与双向匹配评分。", "These soft preferences contribute to the reciprocal matching score."),
        {
            "intensity",
            "communication_style",
            "planning_style",
            "supervision_preference",
            "punctuality_importance",
            "cancellation_tolerance",
            "organization_role",
        },
    ),
    (
        ("④ 个性化偏好", "④ Personal Preferences"),
        ("用兴趣、文字描述和优先因素完善你的画像。", "Complete your profile with interests, descriptions, and priorities."),
        {"interests", "self_description", "partner_expectation", "preference_priorities"},
    ),
)

language = st.session_state.get("language", CHINESE)


def _option_labels(question: Mapping[str, Any]) -> dict[Any, str]:
    return {
        option["value"]: str(option["label"])
        for option in question.get("options", [])
    }


def _widget_label(question: Mapping[str, Any]) -> str:
    marker = " *" if question.get("required") else ""
    return f"{question['label']}{marker}"


def _render_time_question(question: Mapping[str, Any]) -> list[str]:
    """Render the large time vocabulary as seven manageable selectors."""

    st.markdown(f"**{_widget_label(question)}**")
    if question.get("help_text"):
        st.caption(str(question["help_text"]))

    labels = _option_labels(question)
    selected: list[str] = []
    weekday_tabs = st.tabs(
        [weekday_label(code, label, language) for code, label in vocab.WEEKDAYS]
    )
    for tab, (day_code, day_label) in zip(weekday_tabs, vocab.WEEKDAYS):
        localized_day = weekday_label(day_code, day_label, language)
        day_values = [
            value for value in labels if isinstance(value, str) and value.startswith(f"{day_code}_")
        ]
        with tab:
            values = st.multiselect(
                tr(
                    language,
                    f"选择{localized_day}可用时间",
                    f"Select available times on {localized_day}",
                ),
                options=day_values,
                format_func=labels.get,
                key=f"question_available_times_{day_code}",
                label_visibility="collapsed",
                placeholder=tr(
                    language,
                    f"选择{localized_day}的半小时时间片",
                    f"Select 30-minute slots on {localized_day}",
                ),
            )
            selected.extend(values)
    if selected:
        st.caption(
            tr(
                language,
                f"已选择 {len(selected)} 个半小时时间片，共 {len(selected) * 30} 分钟（不一定连续）。",
                f"Selected {len(selected)} half-hour slots, totaling {len(selected) * 30} minutes (not necessarily continuous).",
            )
        )
    return selected


def _render_question(question: Mapping[str, Any]) -> Any:
    question_id = str(question["id"])
    input_type = question["input_type"]
    key = f"question_{question_id}"
    label = _widget_label(question)
    help_text = question.get("help_text")
    labels = _option_labels(question)
    values = list(labels)

    if question_id == "available_times":
        return _render_time_question(question)
    if input_type == "single_select":
        return st.selectbox(
            label,
            options=values,
            format_func=labels.get,
            index=None,
            key=key,
            help=help_text,
            placeholder=tr(language, "请选择一项", "Select one option"),
        )
    if input_type == "multi_select":
        return st.multiselect(
            label,
            options=values,
            format_func=labels.get,
            key=key,
            help=help_text,
            placeholder=tr(language, "请选择一项或多项", "Select one or more options"),
        )
    if input_type == "rating":
        return st.slider(
            label,
            min_value=1,
            max_value=5,
            value=3,
            step=1,
            key=key,
            help=help_text,
        )
    if input_type == "long_text":
        validation = question.get("validation", {})
        return st.text_area(
            label,
            key=key,
            help=help_text,
            max_chars=validation.get("max_length"),
            height=110,
            placeholder=tr(
                language,
                "请至少填写5个字符",
                "Enter at least 5 characters",
            ),
        )
    raise ValueError(
        tr(
            language,
            f"不支持的问卷控件类型：{input_type}",
            f"Unsupported questionnaire input type: {input_type}",
        )
    )


def _validate_metadata_rules(
    answers: Mapping[str, Any], questions: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Validate UI-only cardinality rules before building the canonical profile."""

    errors: list[str] = []
    for question in questions:
        question_id = str(question["id"])
        value = answers.get(question_id)
        label = str(question["label"])
        empty = value is None or value == "" or value == []
        if question.get("required") and empty:
            errors.append(
                tr(language, f"“{label}”为必填项", f'"{label}" is required.')
            )
            continue

        validation = question.get("validation", {})
        if isinstance(value, list):
            minimum = validation.get("min_items")
            maximum = validation.get("max_items")
            if minimum is not None and len(value) < minimum:
                errors.append(
                    tr(
                        language,
                        f"“{label}”至少选择 {minimum} 项",
                        f'Select at least {minimum} items for "{label}".',
                    )
                )
            if maximum is not None and len(value) > maximum:
                errors.append(
                    tr(
                        language,
                        f"“{label}”最多选择 {maximum} 项",
                        f'Select no more than {maximum} items for "{label}".',
                    )
                )
        if isinstance(value, str) and value:
            minimum_length = validation.get("min_length")
            maximum_length = validation.get("max_length")
            if minimum_length is not None and len(value.strip()) < minimum_length:
                errors.append(
                    tr(
                        language,
                        f"“{label}”至少填写 {minimum_length} 个字符",
                        f'Enter at least {minimum_length} characters for "{label}".',
                    )
                )
            if maximum_length is not None and len(value) > maximum_length:
                errors.append(
                    tr(
                        language,
                        f"“{label}”不能超过 {maximum_length} 个字符",
                        f'Enter no more than {maximum_length} characters for "{label}".',
                    )
                )
    return errors


def _next_user_id() -> str:
    users = load_users(PROJECT_ROOT / "data" / "users.csv")
    numeric_ids = [int(user["user_id"][1:]) for user in users]
    next_number = max(numeric_ids, default=0) + 1
    if next_number > 9999:
        raise ValueError(
            tr(
                language,
                "匿名用户编号已经达到上限",
                "The anonymous user ID limit has been reached.",
            )
        )
    return f"U{next_number:04d}"


selected_match_type = st.session_state.get("selected_match_type")
if selected_match_type not in TYPE_PRESENTATION:
    st.warning(
        tr(
            language,
            "请先在首页选择学习、运动或兴趣活动搭子。",
            "Choose a study, sports, or interest activity partner on the home page first.",
        )
    )
    if st.button(tr(language, "返回首页选择", "Return to Home"), type="primary"):
        st.switch_page("pages/home.py")
    st.stop()

icon, type_label_zh, type_label_en, subtitle_zh, subtitle_en = TYPE_PRESENTATION[
    selected_match_type
]
type_label = tr(language, type_label_zh, type_label_en)
type_subtitle = tr(language, subtitle_zh, subtitle_en)
st.markdown(
    f'<div class="campusmate-kicker">{tr(language, "本周行动卡", "This Week’s Action Card")}</div>',
    unsafe_allow_html=True,
)
st.title(
    tr(
        language,
        f"{icon} {type_label}问卷",
        f"{icon} {type_label} Questionnaire",
    )
)
st.caption(type_subtitle)

top_left, top_right = st.columns([3, 1])
with top_left:
    st.info(
        tr(
            language,
            "问卷共20题。带 * 的题目为必填项；提交后会按照第一部分的数据结构1.0.0严格校验。",
            "The questionnaire has 20 questions. Fields marked * are required and will be validated against Part 1 profile schema 1.0.0.",
        )
    )
with top_right:
    if st.button(
        tr(language, "更换搭子类型", "Change Partner Type"),
        use_container_width=True,
    ):
        st.switch_page("pages/home.py")

questions = localize_questions(get_questions(selected_match_type), language)

with st.form(f"campusmate_questionnaire_{selected_match_type}", clear_on_submit=False):
    answers: dict[str, Any] = {"match_type": selected_match_type}
    rendered_count = 1

    for group_titles, group_descriptions, question_ids in QUESTION_GROUPS:
        group_title = tr(language, group_titles[0], group_titles[1])
        group_description = tr(
            language, group_descriptions[0], group_descriptions[1]
        )
        st.markdown(f"### {group_title}")
        st.caption(group_description)
        group_questions = [
            question for question in questions if str(question["id"]) in question_ids
        ]
        for question in group_questions:
            question_id = str(question["id"])
            answers[question_id] = _render_question(question)
            rendered_count += 1
        st.divider()

    submitted = st.form_submit_button(
        tr(language, "提交", "Submit"),
        type="secondary",
        use_container_width=True,
    )

if submitted:
    rule_errors = _validate_metadata_rules(answers, questions)
    if rule_errors:
        st.error(
            tr(
                language,
                "请先修正以下内容：",
                "Please correct the following items:",
            )
        )
        for message in rule_errors:
            st.write(f"- {message}")
    else:
        try:
            profile = build_profile(answers, user_id=_next_user_id())
        except ProfileValidationError as error:
            st.error(
                tr(
                    language,
                    "画像未通过第一部分的数据校验：",
                    "The profile did not pass Part 1 validation:",
                )
            )
            question_labels = {
                str(question["id"]): str(question["label"])
                for question in questions
            }
            derived_labels_zh = {
                "schema_version": "数据结构版本",
                "user_id": "匿名编号",
                "min_session_minutes": "最短活动时长",
                "allow_off_campus": "是否接受校外活动",
                "preference_weights": "偏好权重",
            }
            for issue in error.result.issues:
                chinese_field = question_labels.get(
                    issue.field, derived_labels_zh.get(issue.field, "相关字段")
                )
                displayed_field = field_label(
                    issue.field, chinese_field, language
                )
                displayed_message = issue_message(
                    issue.code, issue.message, language
                )
                st.write(f"- {displayed_field}：{displayed_message}")
        except (FileNotFoundError, ValueError) as error:
            st.error(
                tr(
                    language,
                    f"暂时无法生成匿名编号：{error}",
                    f"Unable to generate an anonymous ID: {error}",
                )
            )
        else:
            st.session_state.questionnaire_answers = dict(answers)
            st.session_state.current_profile = profile
            st.session_state.matching_run = None
            st.session_state.current_match = None
            st.warning(
                tr(
                    language,
                    "行动卡提交成功，标准用户画像已经生成。",
                    "The action card was submitted and a valid profile was created.",
                )
            )

if st.session_state.get("current_profile"):
    if not submitted:
        st.warning(
            tr(
                language,
                "当前会话中已有一份通过校验的行动卡。你可以修改并重新提交。",
                "This session already has a validated action card. You can edit and resubmit it.",
            )
        )
    matching_page = PROJECT_ROOT / "pages" / "matching.py"
    if matching_page.exists():
        if st.button(
            tr(language, "进入匹配页面", "Continue to Matching"),
            type="primary",
            use_container_width=True,
        ):
            st.switch_page("pages/matching.py")
    else:
        st.info(
            tr(
                language,
                "画像已准备好。第二部分的匹配模块接入后即可继续运行匹配。",
                "The profile is ready. Matching can continue after the Part 2 module is connected.",
            )
        )

st.caption(
    tr(
        language,
        f"当前页面已从第一部分动态读取 {len(questions)} 道题目；实际显示：{rendered_count} 道。",
        f"This page loaded {len(questions)} questions dynamically from Part 1; {rendered_count} are displayed.",
    )
)
