"""Display one selected CampusMate matching result."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ai.icebreaker import generate_icebreakers
from data import vocabulary as vocab
from data.data_loader import load_users


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "users.csv"


def _label(mapping: dict[str, str], value: object) -> str:
    return mapping.get(str(value), str(value))


def _partner_id(match: dict[str, object], current_user_id: str) -> str:
    user_a = str(match["user_a"])
    user_b = str(match["user_b"])
    return user_b if user_a == current_user_id else user_a


def _labels(values: list[str], mapping: dict[str, str]) -> str:
    if not values:
        return "暂无"
    return "、".join(mapping.get(value, value) for value in values)


st.markdown('<div class="campusmate-kicker">匹配结果</div>', unsafe_allow_html=True)
st.title("你的推荐搭子")

current_profile = st.session_state.get("current_profile")
match = st.session_state.get("current_match")
if not current_profile:
    st.warning("请先填写行动卡。")
    if st.button("去填写行动卡", type="primary"):
        st.switch_page("pages/questionnaire.py")
    st.stop()
if not match:
    st.warning("还没有选中的匹配结果。")
    if st.button("去运行匹配", type="primary"):
        st.switch_page("pages/matching.py")
    st.stop()

current_id = str(current_profile["user_id"])
partner_id = _partner_id(match, current_id)
users = load_users(DATASET)
partner = next((user for user in users if user["user_id"] == partner_id), None)

score_col, partner_col = st.columns([1, 2])
with score_col:
    st.metric("综合匹配度", f"{float(match['score']):.1f}/100")
with partner_col:
    st.subheader(f"候选人 {partner_id}")
    if partner:
        match_type = str(partner["match_type"])
        st.write(
            f"{_label(vocab.MATCH_TYPES, match_type)} · "
            f"{_label(vocab.ACTIVITIES[match_type], partner['activity'])}"
        )
        st.caption(partner["self_description"])
    else:
        st.write("候选人来自当前匹配结果。")

left, right = st.columns(2)
with left:
    with st.container(border=True):
        st.subheader("共同安排")
        st.write(f"共同时间：{_labels(list(match.get('common_times', [])), vocab.TIME_SLOTS)}")
        st.write(
            f"共同地点：{_labels(list(match.get('common_locations', [])), vocab.LOCATIONS)}"
        )
with right:
    with st.container(border=True):
        st.subheader("推荐理由")
        for reason in match["reasons"]:
            st.write(f"- {reason}")

st.subheader("各维度得分")
for dimension, score in match["dimension_scores"].items():
    label = vocab.PREFERENCE_DIMENSIONS.get(str(dimension), str(dimension))
    numeric = float(score)
    st.progress(numeric / 100, text=f"{label}：{numeric:.1f}/100")

if partner:
    st.subheader("第一次沟通可以这样开始")
    for index, prompt in enumerate(generate_icebreakers(current_profile, partner), start=1):
        st.info(f"{index}. {prompt}")

with st.container():
    if st.button("返回匹配列表"):
        st.switch_page("pages/matching.py")
    if st.button("重新填写行动卡"):
        st.switch_page("pages/questionnaire.py")
