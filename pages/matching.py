"""Run the real Part 2 matcher and choose a result to inspect."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from data import vocabulary as vocab
from services.auth import load_registered_profiles, require_login
from services.matching_adapter import (
    MatchingAdapterError,
    backend_status,
    load_candidate_pool,
    run_matching,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "users.csv"


def _label(mapping: dict[str, str], value: object) -> str:
    return mapping.get(str(value), str(value))


def _partner_id(match: dict[str, object], current_user_id: str) -> str:
    user_a = str(match["user_a"])
    user_b = str(match["user_b"])
    return user_b if user_a == current_user_id else user_a


def _run_current_matching(top_k: int) -> None:
    current_profile = st.session_state.get("current_profile")
    current_id = str(current_profile["user_id"])
    candidates = [
        candidate
        for candidate in [*load_candidate_pool(DATASET), *load_registered_profiles()]
        if str(candidate.get("user_id")) != current_id
    ]
    st.session_state.matching_run = run_matching(
        current_profile,
        candidates,
        top_k=top_k,
    )
    st.session_state.current_match = (
        st.session_state.matching_run["matches"][0]
        if st.session_state.matching_run["matches"]
        else None
    )


st.markdown('<div class="campusmate-kicker">真实匹配流程</div>', unsafe_allow_html=True)
st.title("开始匹配")
st.caption("调用第二板块的硬过滤、双向评分和全局匹配算法，结果不再使用演示数据。")
require_login()

current_profile = st.session_state.get("current_profile")
if not current_profile:
    st.warning("请先填写并提交行动卡，再开始匹配。")
    if st.button("去填写行动卡", type="primary"):
        st.switch_page("pages/questionnaire.py")
    st.stop()

status = backend_status()
if not status["available"]:
    st.error("真实匹配算法尚未接入，当前不能生成正式结果。")
    st.caption(status["message"])
    st.stop()

profile_left, profile_right = st.columns([2, 1])
with profile_left:
    st.subheader("你的行动卡")
    st.write(
        f"**{_label(vocab.MATCH_TYPES, current_profile['match_type'])}** · "
        f"{_label(vocab.ACTIVITIES[str(current_profile['match_type'])], current_profile['activity'])}"
    )
    st.write(f"目标：{_label(vocab.GOALS[str(current_profile['match_type'])], current_profile['goal'])}")
    st.write(f"匿名编号：{current_profile['user_id']}")
with profile_right:
    st.metric("算法状态", "已接入")
    st.metric("候选数据集", "50 人")

with st.container(border=True):
    top_k = st.slider("最多展示几位候选搭子", min_value=1, max_value=8, value=5)
    if st.button("运行真实匹配", type="primary"):
        try:
            with st.spinner("正在过滤硬条件并计算双向匹配分..."):
                _run_current_matching(top_k)
        except MatchingAdapterError as error:
            st.error(f"匹配运行失败：{error}")
        except FileNotFoundError as error:
            st.error(f"候选数据集不存在：{error}")

matching_run = st.session_state.get("matching_run")
if not matching_run:
    st.info("点击“运行真实匹配”后，这里会显示本次匹配结果。")
    st.stop()

matches = list(matching_run["matches"])
metrics = st.columns(4)
metrics[0].metric("运行模式", str(matching_run["mode"]))
metrics[1].metric("候选人数", int(matching_run["candidate_count"]))
metrics[2].metric("返回结果", len(matches))
metrics[3].metric("最高分", f"{matches[0]['score']:.1f}" if matches else "无")

if matching_run.get("warnings"):
    for warning in matching_run["warnings"]:
        st.warning(warning)

if not matches:
    st.warning("当前行动卡没有找到满足硬条件的候选人。可以回到问卷页调整时间、地点或活动条件。")
    if st.button("返回修改行动卡"):
        st.switch_page("pages/questionnaire.py")
    st.stop()

st.subheader("候选搭子")
current_id = str(current_profile["user_id"])
for index, match in enumerate(matches, start=1):
    partner = _partner_id(match, current_id)
    with st.container(border=True):
        col_a, col_b, col_c = st.columns([1, 2, 1])
        col_a.metric(f"第 {index} 位", f"{float(match['score']):.1f}/100")
        col_b.write(f"**候选人：{partner}**")
        col_b.write("；".join(str(reason) for reason in match["reasons"][:2]))
        if col_c.button("查看详情", key=f"open_match_{partner}"):
            st.session_state.current_match = match
            st.switch_page("pages/result.py")

if st.button("查看最高分结果", type="primary"):
    st.session_state.current_match = matches[0]
    st.switch_page("pages/result.py")
