"""Durable weekly match result for the authenticated user."""

from __future__ import annotations

import streamlit as st

from ai.icebreaker import generate_icebreakers
from data import vocabulary as vocab
from services.auth import require_login
from services.platform_service import ServiceError, get_match_result_for_user


def _labels(values: list[str], mapping: dict[str, str]) -> str:
    if not values:
        return "暂无"
    return "、".join(vocab.display_value(value, mapping) for value in values)


auth_user = require_login()
email = str(auth_user["email"])
round_id = str(st.query_params.get("round") or "").strip() or None

st.caption("CAMPUSMATE · 周期匹配结果")
st.title("你的本轮搭子")

try:
    result = get_match_result_for_user(email, round_id=round_id)
except ServiceError as error:
    st.error(str(error))
    st.stop()

if not result:
    st.info("还没有已经公布的周期匹配结果。")
    st.page_link(
        "pages/cycle_match.py",
        label="返回本轮报名",
        icon=":material/calendar_month:",
    )
    st.stop()

st.caption(str(result["name"]))
if str(result.get("enrollment_status")) != "matched" or not result.get("result_id"):
    reason = str(result.get("unmatched_reason") or "本轮暂未形成合适配对")
    st.warning(reason)
    st.write("系统不会为了凑数而忽略时间、地点或其他不可妥协条件。下一轮已经开放，可以沿用资料继续报名。")
    st.page_link(
        "pages/cycle_match.py",
        label="参加下一轮",
        icon=":material/refresh:",
        width="stretch",
    )
    st.stop()

explanation = dict(result.get("explanation") or {})
partner_card = dict(result.get("partner_action_card") or {})
own_card = dict(result.get("own_action_card") or {})

score_col, partner_col = st.columns([1, 2])
with score_col:
    st.metric("综合匹配度", f"{float(result['score']):.1f}/100")
with partner_col:
    st.subheader(str(result.get("partner_name") or "你的搭子"))
    match_type = str(partner_card.get("match_type", ""))
    activity = str(partner_card.get("activity", ""))
    match_type_label = vocab.MATCH_TYPES.get(match_type, match_type)
    activity_label = vocab.display_value(
        activity, vocab.ACTIVITIES.get(match_type, {})
    )
    if match_type_label or activity_label:
        st.write(" · ".join(value for value in (match_type_label, activity_label) if value))
    if partner_card.get("self_description"):
        st.caption(str(partner_card["self_description"]))

with st.container(border=True):
    st.subheader("联系你的搭子")
    partner_contact = str(result.get("partner_contact") or "").strip()
    if partner_contact:
        st.success(partner_contact)
    else:
        st.warning("对方本轮联系方式暂不可用，请通过站内消息联系。")
    st.caption("该联系方式只对本轮成功匹配的双方展示，请勿转发或公开。")

left, right = st.columns(2)
with left:
    with st.container(border=True):
        st.subheader("共同安排")
        st.write(
            "**共同时间：** "
            + _labels(list(explanation.get("common_times", [])), vocab.TIME_SLOTS)
        )
        st.write(
            "**共同地点：** "
            + _labels(list(explanation.get("common_locations", [])), vocab.LOCATIONS)
        )
with right:
    with st.container(border=True):
        st.subheader("推荐理由")
        reasons = list(explanation.get("reasons", []))
        if reasons:
            for reason in reasons:
                st.write(f"- {reason}")
        else:
            st.write("双方通过了不可妥协条件，并在核心偏好上较为接近。")

dimension_scores = dict(explanation.get("dimension_scores", {}))
if dimension_scores:
    st.subheader("各维度得分")
    for dimension, score in dimension_scores.items():
        label = vocab.PREFERENCE_DIMENSIONS.get(str(dimension), str(dimension))
        numeric = float(score)
        st.progress(numeric / 100, text=f"{label}：{numeric:.1f}/100")

if own_card and partner_card:
    st.subheader("第一次沟通可以这样开始")
    for index, prompt in enumerate(
        generate_icebreakers(own_card, partner_card), start=1
    ):
        st.info(f"{index}. {prompt}")

st.page_link(
    "pages/cycle_match.py",
    label="返回周期匹配",
    icon=":material/arrow_back:",
)
