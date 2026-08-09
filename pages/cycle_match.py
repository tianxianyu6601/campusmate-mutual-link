"""Weekly real-user enrollment and automatic matching dashboard."""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.auth import require_login
from services.platform_service import (
    ServiceError,
    enroll_in_match_round,
    ensure_cycle_match_round,
    get_cycle_match_overview,
    withdraw_from_match_round,
)


BEIJING = ZoneInfo("Asia/Shanghai")
MATCH_TYPES = {
    "学习搭子": "study",
    "运动搭子": "sport",
    "兴趣活动搭子": "interest",
}


def _clear_questionnaire_state() -> None:
    for key in list(st.session_state):
        if key.startswith("question_"):
            del st.session_state[key]
    st.session_state.questionnaire_answers = {}
    st.session_state.current_profile = None
    st.session_state.matching_run = None
    st.session_state.current_match = None


def _open_questionnaire(match_type: str) -> None:
    if st.session_state.get("selected_match_type") != match_type:
        _clear_questionnaire_state()
    st.session_state.selected_match_type = match_type
    st.switch_page("pages/questionnaire.py")


def _remaining_text(closes_at: int) -> str:
    remaining = max(0, int(closes_at) - int(time.time()))
    days, remainder = divmod(remaining, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days}天 {hours}小时 {minutes}分钟"
    if hours:
        return f"{hours}小时 {minutes}分钟"
    return f"{minutes}分钟"


auth_user = require_login()
email = str(auth_user["email"])

st.caption("CAMPUSMATE · 周期搭子匹配")
st.title("每周一次，认真认识一个新搭子")
st.write(
    "每周日16:30（北京时间）统一截止并运行真实用户全局匹配；结果生成后立即公布，同时开放下一轮报名。"
)

try:
    cycle = ensure_cycle_match_round(email)
    overview = get_cycle_match_overview(email)
except ServiceError as error:
    st.error(str(error))
    st.stop()

current_round = overview.get("current_round") or cycle.get("current_round")
if not current_round:
    st.warning("当前轮次暂时不可用，请稍后刷新。")
    st.stop()

closes_at = int(current_round["registration_closes_at"])
cutoff = datetime.fromtimestamp(closes_at, BEIJING)
enrollment = overview.get("enrollment")
enrollment_status = str(enrollment.get("status")) if enrollment else ""

with st.container(border=True):
    title_col, count_col = st.columns([3, 1])
    with title_col:
        st.subheader(str(current_round["name"]))
        st.write(f"报名截止：{cutoff:%Y年%m月%d日（周日）16:30}")
        st.caption(f"距离截止还有 {_remaining_text(closes_at)}")
    with count_col:
        st.metric("已报名", f"{int(current_round.get('enrollment_count', 0))} 人")
        st.metric("我的状态", "已报名" if enrollment_status == "enrolled" else "未报名")

latest_round = overview.get("latest_result_round")
if latest_round:
    with st.container(border=True):
        if str(latest_round.get("enrollment_status")) == "matched":
            st.success(f"{latest_round['name']} 的匹配结果已经公布。")
        else:
            reason = str(latest_round.get("unmatched_reason") or "本轮暂未形成合适配对")
            st.info(f"上一轮结果：{reason}")
        if st.button("查看最近匹配结果", type="primary", icon=":material/groups:"):
            st.switch_page(
                "pages/result.py",
                query_params={"round": str(latest_round["round_id"])},
            )

st.subheader("本轮报名")
missing_profile_fields = list(overview.get("missing_profile_fields") or [])
has_action_card = bool(overview.get("has_action_card"))

if enrollment_status == "enrolled":
    st.success("本轮报名成功。截止前可以撤回；匹配时使用报名瞬间冻结的行动卡。")
    if st.button("撤回本轮报名", icon=":material/undo:"):
        try:
            withdraw_from_match_round(str(current_round["round_id"]), email)
        except ServiceError as error:
            st.error(str(error))
        else:
            st.toast("已撤回本轮报名")
            st.rerun()
else:
    if missing_profile_fields:
        st.warning("报名之前请先完善：" + "、".join(missing_profile_fields))
        st.page_link(
            "pages/profile.py",
            label="去完善个人资料",
            icon=":material/person_edit:",
        )

    if not has_action_card:
        st.info("还差一份本轮行动卡。选择搭子类型后填写本轮目标和不可妥协条件。")
    else:
        st.success("本轮行动卡已保存；重新填写会覆盖下一次报名所使用的内容。")

    selected_label = st.segmented_control(
        "本轮想匹配",
        list(MATCH_TYPES),
        default="学习搭子",
        key="cycle_match_type_selector",
    )
    action_col, enroll_col = st.columns(2)
    with action_col:
        if st.button("填写或更新本轮行动卡", icon=":material/edit_note:", width="stretch"):
            _open_questionnaire(MATCH_TYPES[str(selected_label)])
    with enroll_col:
        if st.button(
            "确认报名本轮匹配",
            type="primary",
            icon=":material/how_to_reg:",
            width="stretch",
            disabled=bool(missing_profile_fields or not has_action_card),
        ):
            try:
                enroll_in_match_round(str(current_round["round_id"]), email)
            except ServiceError as error:
                st.error(str(error))
            else:
                st.toast("报名成功，已冻结本轮行动卡")
                st.rerun()

st.divider()
st.caption(
    "匹配顺序：双向硬条件过滤 → 双向满意度评分 → 最大人数优先的全局配对 → 历史未匹配补偿与重复搭子降权。低于安全阈值不会强行凑对。"
)
