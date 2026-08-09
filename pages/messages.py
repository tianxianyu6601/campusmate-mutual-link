"""Authenticated in-app notifications for the activity workflow."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.auth import require_login
from services.platform_service import (
    ServiceError,
    list_user_notifications,
    mark_notification_read,
)
from services.ui import render_empty_state, render_page_intro


BEIJING = ZoneInfo("Asia/Shanghai")


def _format_time(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), BEIJING).strftime("%m月%d日 %H:%M")


user = require_login()
email = str(user["email"])

render_page_intro(
    eyebrow="CAMPUSMATE · 我的消息",
    title="消息中心",
    description="活动申请、审核结果和成员变更会保存在这里，并同步进入邮件通知队列。",
)

unread_only = st.toggle("只看未读", value=False)
try:
    notifications = list_user_notifications(email, unread_only=unread_only)
except ServiceError as error:
    st.error(str(error), icon=":material/error:")
    st.stop()

unread_count = sum(not item["is_read"] for item in notifications)
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"当前列表 {len(notifications)} 条 · {unread_count} 条未读")
    if unread_count and st.button("全部标为已读", icon=":material/done_all:"):
        mark_notification_read(email)
        st.toast("已全部标为已读", icon=":material/check_circle:")
        st.rerun()

if not notifications:
    render_empty_state(
        icon="🔔",
        title="暂无活动消息",
        description="申请活动、审核申请或成员状态发生变化后，真实通知会出现在这里。",
        next_step="消息中心不会伪造提醒，也不会在打开页面时发送额外邮件。",
        action_label="去组局广场看看",
        action_path="pages/activities.py",
    )
else:
    for notification in notifications:
        notification_id = str(notification["notification_id"])
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.subheader(str(notification["title"]))
                if not notification["is_read"]:
                    st.badge("未读", color="blue")
            st.write(str(notification["message"]))
            st.caption(_format_time(int(notification["created_at"])))
            with st.container(horizontal=True):
                if not notification["is_read"] and st.button(
                    "标为已读",
                    key=f"read_{notification_id}",
                    icon=":material/done:",
                ):
                    mark_notification_read(email, notification_id)
                    st.rerun()
                if (
                    str(notification["entity_type"]) == "activity"
                    and notification.get("entity_id")
                    and st.button(
                        "查看活动",
                        key=f"open_{notification_id}",
                        icon=":material/arrow_forward:",
                    )
                ):
                    mark_notification_read(email, notification_id)
                    st.query_params["activity"] = str(notification["entity_id"])
                    st.switch_page("pages/activities.py")
