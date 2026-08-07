"""CampusMate landing page and match-type selection."""

from __future__ import annotations

import streamlit as st

from services.i18n import CHINESE, MATCH_TYPES_EN, tr


MATCH_TYPES = (
    {
        "value": "study",
        "icon": "📚",
        "title": "学习搭子",
    },
    {
        "value": "sport",
        "icon": "🏃",
        "title": "运动搭子",
    },
    {
        "value": "interest",
        "icon": "🎨",
        "title": "兴趣活动搭子",
    },
)


def _clear_questionnaire_state() -> None:
    """Discard answers that would be invalid after changing scenario."""

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


language = st.session_state.get("language", CHINESE)

st.title("CampusMate")
st.markdown(
    f"""
    <p class="campusmate-muted" style="font-size:1.15rem; max-width:760px; line-height:1.75;">
      {tr(language, "让每一次匹配，都能变成一次真实行动", "Turn every match into real action")}
    </p>
    """,
    unsafe_allow_html=True,
)

st.markdown(f"### {tr(language, '你正在寻找：', 'You are looking for:')}")
columns = st.columns(3, gap="large")

for column, match_type in zip(columns, MATCH_TYPES):
    with column:
        with st.container(border=True, key=f"mate_card_{match_type['value']}"):
            st.markdown(
                f"""
                <div class="mate-card-icon">{match_type['icon']}</div>
                """,
                unsafe_allow_html=True,
            )
            title = (
                MATCH_TYPES_EN[match_type["value"]]
                if language != CHINESE
                else match_type["title"]
            )
            if st.button(
                title,
                key=f"select_{match_type['value']}",
                use_container_width=True,
                type="secondary",
            ):
                _select_match_type(match_type["value"])
