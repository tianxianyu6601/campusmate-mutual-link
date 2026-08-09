"""Shared rendering for the authenticated root and stable `/home` routes."""

from __future__ import annotations

import streamlit as st

from services.auth import require_login


PORTALS = (
    {
        "key": "profile",
        "icon": "👤",
        "title": "个人资料",
        "description": "设置你的兴趣、性格、空闲时间和社交偏好。",
        "path": "pages/profile.py",
        "status": "可编辑 · 已保存",
    },
    {
        "key": "activities",
        "icon": "🎉",
        "title": "自由组局",
        "description": "浏览校园活动，或发布一场你想发起的组局。",
        "path": "pages/activities.py",
        "status": "发布、申请与审核可用",
    },
    {
        "key": "cycle_match",
        "icon": "🔄",
        "title": "周期搭子匹配",
        "description": "提交搭子偏好，参加固定轮次的统一匹配。",
        "path": "pages/cycle_match.py",
        "status": "现有匹配可用",
    },
)


def render_home_page() -> None:
    """Render the same home content for both supported home URLs."""

    user = require_login()

    st.title("CampusMate")
    st.markdown("### 今天想从哪里开始？")
    st.caption(
        f"已登录为 {user['email']}。三个板块共享账号，但各自保留独立的业务流程。"
    )

    columns = st.columns(3, gap="large")
    for column, portal in zip(columns, PORTALS):
        with column:
            with st.container(border=True, key=f"portal_card_{portal['key']}"):
                st.markdown(f"# {portal['icon']}")
                st.subheader(portal["title"])
                st.write(portal["description"])
                st.caption(portal["status"])
                if st.button(
                    f"进入{portal['title']}",
                    key=f"open_{portal['key']}",
                    type="primary",
                    width="stretch",
                ):
                    st.switch_page(portal["path"])

    st.divider()
    st.info(
        "个人资料现已支持完整编辑和隐私设置；自由组局已支持浏览、发布、申请、审核和成员管理。"
        "原有问卷与搭子算法已归入“周期搭子匹配”，可以继续使用。",
        icon="ℹ️",
    )
