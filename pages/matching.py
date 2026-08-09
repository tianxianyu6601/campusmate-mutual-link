"""Compatibility route for the retired self-service matcher."""

import streamlit as st

from services.auth import require_login


require_login()
st.caption("CAMPUSMATE · 周期搭子匹配")
st.title("匹配改为每周统一进行")
st.info("个人即时运行候选人匹配已经停用，避免混入演示数据或重复分配同一位用户。")
st.page_link(
    "pages/cycle_match.py",
    label="返回本轮报名与结果",
    icon=":material/calendar_month:",
    width="stretch",
)
