"""Cycle matching entry and bridge to the existing matching workflow."""

from __future__ import annotations

import streamlit as st

from services.auth import require_login


MATCH_TYPES = (
    {"value": "study", "icon": "📚", "title": "学习搭子"},
    {"value": "sport", "icon": "🏃", "title": "运动搭子"},
    {"value": "interest", "icon": "🎨", "title": "兴趣活动搭子"},
)


def _clear_questionnaire_state() -> None:
    for key in list(st.session_state):
        if key.startswith("question_"):
            del st.session_state[key]
    st.session_state.questionnaire_answers = {}
    st.session_state.current_profile = None
    st.session_state.matching_run = None
    st.session_state.current_match = None


def _select_match_type(match_type: str) -> None:
    if st.session_state.get("selected_match_type") != match_type:
        _clear_questionnaire_state()
    st.session_state.selected_match_type = match_type
    st.switch_page("pages/questionnaire.py")


require_login()

st.caption("CAMPUSMATE · 周期搭子匹配")
st.title("选择你想认识的搭子")
st.write(
    "现有问卷和匹配算法继续可用。阶段 6–7 将把它升级为固定报名、统一截止、批量匹配和结果通知。"
)

columns = st.columns(3, gap="large")
for column, match_type in zip(columns, MATCH_TYPES):
    with column:
        with st.container(border=True, key=f"mate_card_{match_type['value']}"):
            st.markdown(f"# {match_type['icon']}")
            st.subheader(match_type["title"])
            if st.button(
                "填写行动卡",
                key=f"select_{match_type['value']}",
                type="primary",
                width="stretch",
            ):
                _select_match_type(match_type["value"])

st.divider()
result_col, insights_col = st.columns(2)
with result_col:
    st.page_link(
        "pages/result.py",
        label="查看最近匹配结果",
        icon="✨",
        width="stretch",
    )
with insights_col:
    st.page_link(
        "pages/ai_insights.py",
        label="查看 AI 匹配洞察",
        icon="💡",
        width="stretch",
    )
