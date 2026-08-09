"""Authenticated activity plaza, detail view, and two-step publisher."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from services.auth import require_login
from services.email_tasks import process_email_tasks
from services.platform_service import (
    ConflictError,
    NotFoundError,
    PermissionDenied,
    ServiceError,
    apply_to_activity,
    cancel_activity,
    create_activity,
    end_activity,
    get_activity,
    get_visible_profile,
    leave_activity,
    list_activities,
    list_activity_applications,
    list_activity_members,
    publish_activity,
    remove_activity_member,
    review_activity_application,
    update_activity,
    withdraw_activity_application,
)


BEIJING = ZoneInfo("Asia/Shanghai")
CATEGORY_LABELS = {
    "study": "学习交流",
    "sport": "运动",
    "social": "社交",
    "entertainment": "娱乐",
    "travel": "出行",
    "share": "拼一切",
    "custom": "自定义",
}
CATEGORY_ICONS = {
    "study": "menu_book",
    "sport": "sports_basketball",
    "social": "forum",
    "entertainment": "movie",
    "travel": "hiking",
    "share": "group_add",
    "custom": "interests",
}
STATUS_LABELS = {
    "draft": "草稿",
    "published": "报名中",
    "full": "已满员",
    "ended": "已结束",
    "cancelled": "已取消",
}
STATUS_COLORS = {
    "draft": "gray",
    "published": "green",
    "full": "orange",
    "ended": "blue",
    "cancelled": "red",
}
VISIBILITY_LABELS = {
    "campus": "所有已登录用户",
    "public": "所有已登录用户（公开标记）",
    "invite": "仅受邀成员",
}
LOCATION_OPTIONS = (
    "燕园校区",
    "邱德拔体育馆",
    "理科教学楼",
    "新太阳学生中心",
    "未名湖",
    "畅春新园",
    "中关新园",
)


def _beijing_now_naive() -> datetime:
    return datetime.now(BEIJING).replace(tzinfo=None, second=0, microsecond=0)


def _to_timestamp(value: datetime) -> int:
    return int(value.replace(tzinfo=BEIJING).timestamp())


def _from_timestamp(value: int | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    return datetime.fromtimestamp(int(value), BEIJING).replace(tzinfo=None)


def _format_time(value: int) -> str:
    return datetime.fromtimestamp(int(value), BEIJING).strftime("%m月%d日 %H:%M")


def _format_period(activity: dict[str, Any]) -> str:
    text = _format_time(int(activity["starts_at"]))
    if activity.get("ends_at"):
        text += f" – {_format_time(int(activity['ends_at']))}"
    return text


def _category_name(activity: dict[str, Any]) -> str:
    if activity["category"] == "custom":
        return str(activity.get("custom_category") or "自定义")
    return CATEGORY_LABELS.get(str(activity["category"]), str(activity["category"]))


def _open_plaza() -> None:
    st.switch_page("pages/activities.py")


def _open_detail(activity_id: str) -> None:
    st.switch_page(
        "pages/activities.py",
        query_params={"activity": activity_id},
    )


def _open_publisher(activity_id: str | None = None) -> None:
    if activity_id:
        st.session_state["activity_publish_step"] = 2
        query_params = {"mode": "edit", "activity": activity_id}
    else:
        st.session_state["activity_publish_step"] = 1
        st.session_state.pop("activity_publish_category", None)
        st.session_state.pop("activity_publish_custom_category", None)
        query_params = {"mode": "publish"}
    st.switch_page("pages/activities.py", query_params=query_params)


def _uploaded_image_data_url(uploaded_file: Any) -> str:
    raw = uploaded_file.getvalue()
    mime_type = str(uploaded_file.type or "").lower()
    suffix = str(uploaded_file.name).lower().rsplit(".", 1)[-1]
    if mime_type in {"image/jpeg", "image/jpg"} or suffix in {"jpg", "jpeg"}:
        mime_type = "image/jpeg"
    elif mime_type == "image/png" or suffix == "png":
        mime_type = "image/png"
    elif mime_type == "image/webp" or suffix == "webp":
        mime_type = "image/webp"
    else:
        raise ValueError("活动图片仅支持 PNG、JPG 或 WebP")
    return f"data:{mime_type};base64," + base64.b64encode(raw).decode("ascii")


def _deliver_email_tasks() -> None:
    """Best-effort delivery after the business transaction has committed."""

    try:
        process_email_tasks(limit=5)
    except Exception:
        # The durable outbox keeps the task for the scheduled worker/retry.
        pass


def _render_activity_card(activity: dict[str, Any]) -> None:
    with st.container(border=True):
        image_column, content_column = st.columns([1, 2.4], vertical_alignment="center")
        with image_column:
            if activity.get("image_url"):
                st.image(str(activity["image_url"]), width="stretch")
            else:
                with st.container(horizontal_alignment="center"):
                    icon = CATEGORY_ICONS.get(str(activity["category"]), "event")
                    st.markdown(f"# :material/{icon}:")
                    st.caption(_category_name(activity))
        with content_column:
            with st.container(horizontal=True, vertical_alignment="center"):
                st.subheader(str(activity["title"]))
                status = str(activity["status"])
                st.badge(
                    STATUS_LABELS.get(status, status),
                    color=STATUS_COLORS.get(status, "gray"),
                )
            st.caption(
                f"{_category_name(activity)} · {_format_period(activity)} · "
                f"{activity['location_text']}"
            )
            description = str(activity.get("description") or "暂无详细描述")
            st.write(description[:130] + ("…" if len(description) > 130 else ""))
            organizer = str(activity.get("organizer_name") or "校园用户")
            st.caption(
                f"发起人：{organizer}　{activity['member_count']}/{activity['capacity']} 人"
            )
            if st.button(
                "查看详情",
                key=f"activity_detail_{activity['activity_id']}",
                icon=":material/arrow_forward:",
            ):
                _open_detail(str(activity["activity_id"]))


@st.dialog("确认取消活动", icon=":material/warning:")
def _confirm_cancel(activity_id: str, title: str, email: str) -> None:
    st.write(f"取消后活动 **{title}** 将不再对其他用户展示，且不能恢复。")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("暂不取消", key=f"keep_{activity_id}"):
            st.rerun()
        if st.button(
            "确认取消",
            key=f"cancel_{activity_id}",
            type="primary",
            icon=":material/cancel:",
        ):
            try:
                cancel_activity(activity_id, email)
            except ServiceError as error:
                st.error(str(error))
                return
            _deliver_email_tasks()
            st.query_params["activity"] = activity_id
            st.toast("活动已取消", icon=":material/check_circle:")
            st.rerun()


@st.dialog("确认退出活动", icon=":material/logout:")
def _confirm_leave(activity_id: str, title: str, email: str) -> None:
    st.write(f"退出后将释放 **{title}** 的一个名额。")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("暂不退出", key=f"keep_membership_{activity_id}"):
            st.rerun()
        if st.button(
            "确认退出",
            key=f"leave_{activity_id}",
            type="primary",
            icon=":material/logout:",
        ):
            try:
                leave_activity(activity_id, email)
            except ServiceError as error:
                st.error(str(error))
                return
            _deliver_email_tasks()
            st.toast("已退出活动", icon=":material/check_circle:")
            st.rerun()


@st.dialog("确认移除成员", icon=":material/person_remove:")
def _confirm_remove_member(
    activity_id: str,
    title: str,
    member_email: str,
    member_name: str,
    organizer_email: str,
) -> None:
    st.write(f"确认将 **{member_name}** 移出 **{title}** 吗？该名额会重新开放。")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("暂不移除", key=f"keep_member_{activity_id}_{member_email}"):
            st.rerun()
        if st.button(
            "确认移除",
            key=f"remove_member_{activity_id}_{member_email}",
            type="primary",
            icon=":material/person_remove:",
        ):
            try:
                remove_activity_member(
                    activity_id,
                    member_email,
                    organizer_email,
                )
            except ServiceError as error:
                st.error(str(error))
                return
            _deliver_email_tasks()
            st.toast("成员已移除", icon=":material/check_circle:")
            st.rerun()


APPLICATION_STATUS_LABELS = {
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "未通过",
    "withdrawn": "已撤回",
}


@st.dialog("同学资料", icon=":material/account_circle:", width="large")
def _show_visible_profile(viewer_email: str, subject_email: str) -> None:
    """Show only the fields the profile owner has permitted this viewer to see."""

    try:
        profile = get_visible_profile(viewer_email, subject_email)
    except ServiceError as error:
        st.error(str(error))
        return
    if profile is None:
        st.info("这位同学还没有填写个人资料。")
        return

    avatar = str(profile.get("avatar_data_url") or "")
    header_left, header_right = st.columns([1, 4], vertical_alignment="center")
    with header_left:
        if avatar:
            st.image(avatar, width=96)
        else:
            st.markdown("### 👤")
    with header_right:
        st.subheader(str(profile.get("display_name") or "校园用户"))
        identity_parts = [
            str(profile.get(field_name) or "")
            for field_name in ("school", "department", "grade", "identity_label")
        ]
        identity_text = " · ".join(part for part in identity_parts if part)
        if identity_text:
            st.caption(identity_text)
        if profile.get("bio"):
            st.write(str(profile["bio"]))

    interests = profile.get("interests") or []
    if interests:
        st.markdown("**兴趣标签**")
        st.write(" · ".join(str(item.get("tag", "")) for item in interests if item.get("tag")))

    descriptions = (
        ("我是什么样的人", "self_description"),
        ("我想找什么样的人", "partner_expectation"),
    )
    for label, field_name in descriptions:
        if profile.get(field_name):
            st.markdown(f"**{label}**")
            st.write(str(profile[field_name]))

    contacts = [
        ("邮箱", str(profile.get("contact_email") or "")),
        ("QQ", str(profile.get("contact_qq") or "")),
        ("微信", str(profile.get("contact_wechat") or "")),
    ]
    visible_contacts = [(label, value) for label, value in contacts if value]
    if visible_contacts:
        st.markdown("**联系方式**")
        for label, value in visible_contacts:
            st.write(f"{label}：{value}")
    else:
        st.caption("对方没有向你公开联系方式。")


def _render_organizer_workflow(activity: dict[str, Any], email: str) -> None:
    activity_id = str(activity["activity_id"])
    st.subheader("申请管理")
    try:
        applications = list_activity_applications(activity_id, email)
    except ServiceError as error:
        st.error(str(error))
        return
    pending = [item for item in applications if item["status"] == "pending"]
    if not pending:
        st.caption("目前没有待审核申请。")
    for application in pending:
        application_id = str(application["application_id"])
        name = str(application.get("applicant_name") or "校园用户")
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"**{name}**")
                st.badge("待审核", color="orange")
            st.write(str(application.get("reason") or "未填写申请说明"))
            with st.container(horizontal=True):
                if st.button(
                    "查看资料",
                    key=f"profile_{application_id}",
                    icon=":material/person_search:",
                ):
                    _show_visible_profile(email, str(application["applicant_email"]))
                if st.button(
                    "同意加入",
                    key=f"approve_{application_id}",
                    type="primary",
                    icon=":material/person_add:",
                ):
                    try:
                        review_activity_application(
                            activity_id,
                            application_id,
                            email,
                            approve=True,
                        )
                    except ServiceError as error:
                        st.error(str(error))
                    else:
                        _deliver_email_tasks()
                        st.toast("已同意申请", icon=":material/check_circle:")
                        st.rerun()
                if st.button(
                    "拒绝",
                    key=f"reject_{application_id}",
                    icon=":material/close:",
                ):
                    try:
                        review_activity_application(
                            activity_id,
                            application_id,
                            email,
                            approve=False,
                        )
                    except ServiceError as error:
                        st.error(str(error))
                    else:
                        _deliver_email_tasks()
                        st.toast("已拒绝申请", icon=":material/check_circle:")
                        st.rerun()
    processed = [item for item in applications if item["status"] != "pending"]
    if processed:
        with st.expander(f"已处理申请（{len(processed)}）"):
            for application in processed:
                name = str(application.get("applicant_name") or "校园用户")
                status_label = APPLICATION_STATUS_LABELS.get(
                    str(application["status"]), str(application["status"])
                )
                st.write(f"{name} · {status_label}")


def _render_participation(activity: dict[str, Any], email: str) -> None:
    activity_id = str(activity["activity_id"])
    title = str(activity["title"])
    status = str(activity["status"])
    application = activity.get("viewer_application")
    if activity["is_member"]:
        st.success("你已加入这个活动。", icon=":material/check_circle:")
        if not activity["is_organizer"] and status in {"published", "full"}:
            if st.button("退出活动", icon=":material/logout:"):
                _confirm_leave(activity_id, title, email)
        return
    if status == "full":
        st.warning("活动人数已满，暂时不能继续申请。", icon=":material/group:")
        return
    if status != "published":
        return
    application_status = str(application["status"]) if application else ""
    if application_status == "pending":
        st.info("申请已提交，正在等待发起人审核。", icon=":material/schedule:")
        if st.button("撤回申请", icon=":material/undo:"):
            try:
                withdraw_activity_application(activity_id, email)
            except ServiceError as error:
                st.error(str(error))
            else:
                st.toast("申请已撤回", icon=":material/check_circle:")
                st.rerun()
        return
    if application_status == "rejected":
        st.info("这次申请未通过。", icon=":material/info:")
        return
    if application_status == "withdrawn":
        st.caption("你已撤回此前的申请，可以重新提交。")
    with st.form(f"activity_application_{activity_id}"):
        reason = st.text_area(
            "申请说明",
            max_chars=500,
            placeholder="简单介绍自己，或说明你为什么想参加（可选）",
        )
        submitted = st.form_submit_button(
            "申请加入" if activity["approval_required"] else "直接加入",
            type="primary",
            icon=":material/send:",
        )
    if submitted:
        try:
            apply_to_activity(activity_id, email, reason=reason)
        except ServiceError as error:
            st.error(str(error))
        else:
            _deliver_email_tasks()
            message = "申请已提交" if activity["approval_required"] else "已加入活动"
            st.toast(message, icon=":material/check_circle:")
            st.rerun()


def _render_member_roster(activity: dict[str, Any], email: str) -> None:
    if not activity["is_member"]:
        return
    activity_id = str(activity["activity_id"])
    try:
        members = list_activity_members(activity_id, email)
    except ServiceError as error:
        st.error(str(error))
        return
    st.subheader(f"活动成员（{len(members)}）")
    for member in members:
        member_email = str(member["member_email"])
        member_name = str(member.get("member_name") or "校园用户")
        role = str(member["role"])
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            st.write(f"**{member_name}**" + (" · 发起人" if role == "organizer" else ""))
            if st.button(
                "查看资料",
                key=f"member_profile_{activity_id}_{member_email}",
                icon=":material/person_search:",
            ):
                _show_visible_profile(email, member_email)
            if (
                activity["is_organizer"]
                and role != "organizer"
                and str(activity["status"]) in {"published", "full"}
            ):
                if st.button(
                    "移除",
                    key=f"remove_{activity_id}_{member_email}",
                    icon=":material/person_remove:",
                ):
                    _confirm_remove_member(
                        activity_id,
                        str(activity["title"]),
                        member_email,
                        member_name,
                        email,
                    )


def _render_detail(activity_id: str, email: str) -> None:
    try:
        activity = get_activity(activity_id, email)
    except (NotFoundError, PermissionDenied) as error:
        st.error(str(error), icon=":material/error:")
        if st.button("返回组局广场", icon=":material/arrow_back:"):
            _open_plaza()
        return

    if st.button("返回组局广场", icon=":material/arrow_back:"):
        _open_plaza()

    if activity.get("image_url"):
        st.image(str(activity["image_url"]), width="stretch")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.title(str(activity["title"]))
        status = str(activity["status"])
        st.badge(
            STATUS_LABELS.get(status, status),
            color=STATUS_COLORS.get(status, "gray"),
        )
    st.caption(f"{_category_name(activity)} · 由 {activity.get('organizer_name') or '校园用户'} 发起")

    info_columns = st.columns(3)
    info_columns[0].metric("活动时间", _format_time(int(activity["starts_at"])))
    info_columns[1].metric("活动地点", str(activity["location_text"]))
    info_columns[2].metric(
        "活动人数", f"{activity['member_count']} / {activity['capacity']}"
    )
    if activity.get("ends_at"):
        st.caption(f"预计结束：{_format_time(int(activity['ends_at']))}")

    with st.container(border=True):
        st.subheader("活动介绍")
        st.write(str(activity.get("description") or "发起人暂未填写详细介绍。"))
        st.caption(
            f"可见范围：{VISIBILITY_LABELS.get(str(activity['visibility']), activity['visibility'])} · "
            f"{'需要发起人审核' if activity['approval_required'] else '无需发起人审核'}"
        )

    if activity["is_organizer"]:
        st.subheader("发起人操作")
        with st.container(horizontal=True):
            can_edit = status == "draft" or (
                status == "published"
                and int(activity["starts_at"])
                >= int(datetime.now(BEIJING).timestamp()) - 60
            )
            if can_edit and st.button(
                "编辑活动", icon=":material/edit:"
            ):
                _open_publisher(activity_id)
            if status == "draft" and st.button(
                "发布草稿", type="primary", icon=":material/publish:"
            ):
                try:
                    publish_activity(activity_id, email)
                except ServiceError as error:
                    st.error(str(error))
                else:
                    st.toast("活动已发布", icon=":material/check_circle:")
                    st.rerun()
            if status in {"published", "full"} and st.button(
                "结束活动", icon=":material/event_available:"
            ):
                try:
                    end_activity(activity_id, email)
                except ServiceError as error:
                    st.error(str(error))
                else:
                    st.toast("活动已结束", icon=":material/check_circle:")
                    st.rerun()
            if status not in {"ended", "cancelled"} and st.button(
                "取消活动", icon=":material/cancel:"
            ):
                _confirm_cancel(activity_id, str(activity["title"]), email)
        if status in {"published", "full"}:
            _render_organizer_workflow(activity, email)
    else:
        _render_participation(activity, email)
    _render_member_roster(activity, email)


def _render_category_step(existing: dict[str, Any] | None = None) -> None:
    st.caption("发布活动 · 第 1/2 步")
    st.progress(0.5)
    st.subheader("先选择活动分类")
    st.write("分类会用于组局广场筛选，选择最贴近活动内容的一项。")
    default_category = str(
        st.session_state.get(
            "activity_publish_category",
            existing.get("category", "sport") if existing else "sport",
        )
    )
    category = st.pills(
        "活动分类",
        list(CATEGORY_LABELS),
        default=default_category,
        required=True,
        format_func=lambda value: CATEGORY_LABELS[value],
        key="activity_category_choice",
        width="stretch",
    )
    custom_default = str(
        st.session_state.get(
            "activity_publish_custom_category",
            existing.get("custom_category", "") if existing else "",
        )
    )
    custom_category = ""
    if category == "custom":
        custom_category = st.text_input(
            "自定义分类名称*",
            value=custom_default,
            max_chars=40,
            placeholder="例如：校园观鸟",
        )
    with st.container(horizontal=True):
        if st.button("返回广场", icon=":material/arrow_back:"):
            _open_plaza()
        if st.button(
            "下一步",
            type="primary",
            icon=":material/arrow_forward:",
        ):
            if category == "custom" and not custom_category.strip():
                st.error("请填写自定义分类名称")
                return
            st.session_state["activity_publish_category"] = str(category)
            st.session_state["activity_publish_custom_category"] = custom_category.strip()
            st.session_state["activity_publish_step"] = 2
            st.rerun()


def _render_activity_form(email: str, existing: dict[str, Any] | None = None) -> None:
    is_editing = existing is not None
    st.caption(f"{'编辑活动' if is_editing else '发布活动'} · 第 2/2 步")
    st.progress(1.0)
    category = str(
        st.session_state.get(
            "activity_publish_category",
            existing.get("category", "sport") if existing else "sport",
        )
    )
    custom_category = str(
        st.session_state.get(
            "activity_publish_custom_category",
            existing.get("custom_category", "") if existing else "",
        )
    )
    st.badge(
        f"分类：{custom_category if category == 'custom' else CATEGORY_LABELS[category]}",
        icon=":material/category:",
        color="blue",
    )
    with st.container(horizontal=True):
        if st.button(
            "返回活动详情" if existing else "返回组局广场",
            icon=":material/close:",
        ):
            if existing:
                _open_detail(str(existing["activity_id"]))
            else:
                _open_plaza()
        if st.button("重选分类", icon=":material/arrow_back:"):
            st.session_state["activity_publish_step"] = 1
            st.rerun()

    now = _beijing_now_naive()
    default_start = now + timedelta(days=1)
    default_end = default_start + timedelta(hours=2)
    start_value = _from_timestamp(
        int(existing["starts_at"]) if existing else None, default_start
    )
    end_value = _from_timestamp(
        int(existing["ends_at"]) if existing and existing.get("ends_at") else None,
        default_end,
    )
    existing_location = str(existing.get("location_text", "")) if existing else ""
    location_options = list(LOCATION_OPTIONS)
    location_index = (
        location_options.index(existing_location)
        if existing_location in location_options
        else None
    )
    custom_location_value = (
        existing_location if existing_location and existing_location not in location_options else ""
    )

    with st.form("activity_editor"):
        st.subheader("活动内容")
        title = st.text_input(
            "活动标题*",
            value=str(existing.get("title", "")) if existing else "",
            max_chars=60,
            placeholder="一句话说清楚这是什么活动",
        )
        description = st.text_area(
            "详细描述",
            value=str(existing.get("description", "")) if existing else "",
            max_chars=3000,
            height=180,
            placeholder="建议写清活动安排、费用、对参与者的要求和需要准备的物品。",
        )
        image_file = st.file_uploader(
            "活动封面（可选）",
            type=["png", "jpg", "jpeg", "webp"],
            max_upload_size=1,
            help="最多 1 MB；未上传时使用分类图标。",
        )
        remove_image = st.checkbox(
            "移除当前封面",
            value=False,
            disabled=not bool(existing and existing.get("image_url")),
        )

        st.subheader("时间和地点")
        start_time = st.datetime_input(
            "开始时间*",
            value=start_value,
            min_value=now - timedelta(minutes=1) if not is_editing else None,
            format="YYYY-MM-DD",
            step=timedelta(minutes=15),
        )
        has_end_time = st.checkbox(
            "设置结束时间",
            value=bool(existing and existing.get("ends_at")),
        )
        end_time = None
        if has_end_time:
            end_time = st.datetime_input(
                "结束时间*",
                value=end_value,
                format="YYYY-MM-DD",
                step=timedelta(minutes=15),
            )
        location = st.selectbox(
            "常用活动地点",
            options=location_options,
            index=location_index,
            placeholder="请选择常用地点",
        )
        custom_location = st.text_input(
            "自定义活动地点",
            value=custom_location_value,
            max_chars=160,
            placeholder="例如：北京市海淀区某咖啡馆（填写后优先使用）",
        )

        st.subheader("参与设置")
        capacity = st.number_input(
            "活动总人数（含发起人）*",
            min_value=2,
            max_value=100,
            value=int(existing.get("capacity", 4)) if existing else 4,
            step=1,
        )
        visibility = st.selectbox(
            "可见范围*",
            options=list(VISIBILITY_LABELS),
            index=list(VISIBILITY_LABELS).index(
                str(existing.get("visibility", "campus")) if existing else "campus"
            ),
            format_func=lambda value: VISIBILITY_LABELS[value],
        )
        approval_required = st.checkbox(
            "参与活动需要发起人审核",
            value=bool(existing.get("approval_required", True)) if existing else True,
        )
        st.caption("勾选后由你逐一审核；不勾选时，未满员用户可直接加入。")

        with st.container(horizontal=True, horizontal_alignment="right"):
            save_draft = st.form_submit_button(
                "保存草稿",
                icon=":material/draft:",
                disabled=bool(existing and existing.get("status") == "published"),
                width="content",
            )
            publish = st.form_submit_button(
                "保存并发布" if is_editing else "发布活动",
                type="primary",
                icon=":material/publish:",
                width="content",
            )

    if not (save_draft or publish):
        return
    if start_time is None:
        st.error("请选择开始时间")
        return
    if has_end_time and end_time is None:
        st.error("请选择结束时间")
        return
    final_location = custom_location.strip() or str(location or "").strip()
    if not final_location:
        st.error("请选择常用活动地点或填写自定义活动地点")
        return
    image_url = str(existing.get("image_url", "")) if existing else ""
    if remove_image:
        image_url = ""
    if image_file is not None:
        try:
            image_url = _uploaded_image_data_url(image_file)
        except ValueError as error:
            st.error(str(error))
            return
    requested_status = "draft" if save_draft else "published"
    try:
        if existing:
            update_activity(
                str(existing["activity_id"]),
                email,
                category=category,
                custom_category=custom_category,
                title=title,
                description=description,
                image_url=image_url,
                starts_at=_to_timestamp(start_time),
                ends_at=_to_timestamp(end_time) if end_time else None,
                location_text=final_location,
                capacity=int(capacity),
                visibility=visibility,
                approval_required=approval_required,
                status=requested_status,
                expected_version=int(existing["version"]),
            )
            activity_id = str(existing["activity_id"])
        else:
            activity_id = create_activity(
                email,
                category=category,
                custom_category=custom_category,
                title=title,
                description=description,
                image_url=image_url,
                starts_at=_to_timestamp(start_time),
                ends_at=_to_timestamp(end_time) if end_time else None,
                location_text=final_location,
                capacity=int(capacity),
                visibility=visibility,
                approval_required=approval_required,
                status=requested_status,
            )
    except ServiceError as error:
        st.error(str(error))
        return
    st.session_state.pop("activity_publish_step", None)
    st.session_state.pop("activity_publish_category", None)
    st.session_state.pop("activity_publish_custom_category", None)
    st.toast(
        "活动已发布" if requested_status == "published" else "草稿已保存",
        icon=":material/check_circle:",
    )
    _open_detail(activity_id)


def _render_publisher(email: str, activity_id: str | None) -> None:
    existing = None
    if activity_id:
        try:
            existing = get_activity(activity_id, email)
        except ServiceError as error:
            st.error(str(error), icon=":material/error:")
            return
        if not existing["is_organizer"]:
            st.error("只有活动发起人可以编辑活动")
            return
    if st.session_state.get("activity_publish_step", 1) == 1:
        _render_category_step(existing)
    else:
        _render_activity_form(email, existing)


def _render_plaza(email: str) -> None:
    st.caption("CAMPUSMATE · 自由组局")
    st.title("组局广场")
    st.write("发现想参加的校园活动，或者发起一场属于你的组局。")
    if st.button(
        "发布活动",
        type="primary",
        icon=":material/add_circle:",
    ):
        _open_publisher()

    scope_label = st.segmented_control(
        "活动视图",
        ["发现活动", "我的活动"],
        default="发现活动",
        key="activity_scope",
    )
    scope = "mine" if scope_label == "我的活动" else "discover"

    with st.container(border=True):
        keyword = st.text_input(
            "搜索活动",
            placeholder="搜索标题、描述、地点或自定义分类",
            icon=":material/search:",
            key="activity_keyword",
        )
        selected_labels = st.pills(
            "活动分类",
            list(CATEGORY_LABELS.values()),
            selection_mode="multi",
            key="activity_categories",
            width="stretch",
        ) or []
        filter_columns = st.columns(3)
        with filter_columns[0]:
            time_filter = st.selectbox(
                "时间",
                ["全部时间", "今天", "未来 7 天", "未来活动", "已结束"],
            )
        with filter_columns[1]:
            location = st.text_input("地点", placeholder="例如：燕园")
        with filter_columns[2]:
            sort_label = st.selectbox("排序", ["最近开始", "最新发布", "人气优先"])
        status_options = (
            ["草稿", "报名中", "已满员", "已结束", "已取消"]
            if scope == "mine"
            else ["报名中", "已满员", "已结束"]
        )
        selected_status_labels = st.pills(
            "活动状态",
            status_options,
            selection_mode="multi",
        ) or []

    reverse_categories = {label: key for key, label in CATEGORY_LABELS.items()}
    reverse_statuses = {label: key for key, label in STATUS_LABELS.items()}
    now = int(datetime.now(BEIJING).timestamp())
    starts_after = None
    starts_before = None
    statuses = [reverse_statuses[label] for label in selected_status_labels]
    if time_filter == "今天":
        today = datetime.now(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)
        starts_after = int(today.timestamp())
        starts_before = int((today + timedelta(days=1)).timestamp())
    elif time_filter == "未来 7 天":
        starts_after = now
        starts_before = now + 7 * 24 * 3600
    elif time_filter == "未来活动":
        starts_after = now
    elif time_filter == "已结束":
        statuses = ["ended"]
    sort_by = {
        "最近开始": "soonest",
        "最新发布": "newest",
        "人气优先": "popular",
    }[sort_label]

    try:
        activities = list_activities(
            email,
            scope=scope,
            keyword=keyword,
            categories=[reverse_categories[label] for label in selected_labels],
            location=location,
            statuses=statuses,
            starts_after=starts_after,
            starts_before=starts_before,
            sort_by=sort_by,
        )
    except ServiceError as error:
        st.error(str(error), icon=":material/error:")
        return

    st.caption(f"找到 {len(activities)} 场活动")
    if not activities:
        with st.container(border=True, horizontal_alignment="center"):
            st.markdown("# :material/event_busy:")
            st.subheader("暂时没有符合条件的活动")
            st.write("换一组筛选条件，或者发布第一场活动。")
            if st.button("发布活动", icon=":material/add_circle:"):
                _open_publisher()
        return
    for activity in activities:
        _render_activity_card(activity)


user = require_login()
email = str(user["email"])
activity_query = str(st.query_params.get("activity", "") or "")
mode_query = str(st.query_params.get("mode", "") or "")

if mode_query in {"publish", "edit"}:
    _render_publisher(email, activity_query or None)
elif activity_query:
    _render_detail(activity_query, email)
else:
    _render_plaza(email)
