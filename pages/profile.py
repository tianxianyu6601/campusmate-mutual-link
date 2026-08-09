"""Editable, privacy-aware CampusMate profile page."""

from __future__ import annotations

import base64
from typing import Any

import streamlit as st

from services.auth import require_login
from services.platform_service import (
    MAX_AVATAR_BYTES,
    ServiceError,
    get_profile,
    matching_profile_missing_fields,
    upsert_profile,
)
from services.ui import render_page_intro


INTEREST_OPTIONS = {
    "study": ("Python", "人工智能", "英语", "数学", "阅读", "考研", "论文", "自习"),
    "sport": ("羽毛球", "跑步", "健身", "篮球", "足球", "乒乓球", "游泳", "徒步", "骑行", "飞盘"),
    "entertainment": ("电影", "观展", "摄影", "桌游", "剧本杀", "唱歌", "City Walk", "旅行", "咖啡", "约饭"),
    "share": ("拼车", "拼单", "拼谷", "拼票", "拼团"),
}
INTEREST_LABELS = {
    "study": "学习",
    "sport": "运动",
    "entertainment": "娱乐",
    "share": "拼一切",
    "custom": "自定义",
}
TIME_OPTIONS = (
    "工作日上午",
    "工作日下午",
    "工作日晚上",
    "周六上午",
    "周六下午",
    "周六晚上",
    "周日上午",
    "周日下午",
    "周日晚上",
)
LOCATION_OPTIONS = (
    "燕园校区",
    "畅春新园",
    "新太阳学生中心",
    "邱德拔体育馆",
    "百周年纪念讲堂",
    "图书馆",
    "未名湖",
    "校外",
)
GRADE_OPTIONS = (
    "",
    "本科一年级",
    "本科二年级",
    "本科三年级",
    "本科四年级",
    "硕士研究生",
    "博士研究生",
    "教师",
    "校友",
    "其他",
)
IDENTITY_OPTIONS = ("", "本科生", "硕士生", "博士生", "教师", "校友", "其他")
MBTI_OPTIONS = (
    "",
    "INTJ",
    "INTP",
    "ENTJ",
    "ENTP",
    "INFJ",
    "INFP",
    "ENFJ",
    "ENFP",
    "ISTJ",
    "ISFJ",
    "ESTJ",
    "ESFJ",
    "ISTP",
    "ISFP",
    "ESTP",
    "ESFP",
)
PLANNING_OPTIONS = {
    "flexible": "随性灵活",
    "balanced": "大致有计划",
    "planned": "喜欢提前规划",
}
GROUP_SIZE_OPTIONS = {
    "one_to_one": "一对一",
    "small_group": "3–5 人小组",
    "large_group": "多人活动",
    "any": "都可以",
}
PRIVACY_OPTIONS = {
    "private": "仅自己",
    "matched": "匹配成功后",
    "activity_members": "同活动成员",
    "public": "所有登录用户",
}
PRIVACY_LABELS = {
    "avatar_data_url": "头像",
    "school": "学校",
    "department": "院系",
    "grade": "年级",
    "identity_label": "身份",
    "bio": "个人介绍",
    "interests": "兴趣标签",
    "personality": "性格与社交方式",
    "available_times": "空闲时间",
    "preferred_locations": "地点与距离偏好",
    "self_description": "我是什么样的人",
    "partner_expectation": "我想找什么样的人",
    "contact_email": "联系邮箱",
    "contact_qq": "QQ号",
    "contact_wechat": "微信号",
}
DEFAULT_PRIVACY = {
    "avatar_data_url": "public",
    "school": "public",
    "department": "public",
    "grade": "public",
    "identity_label": "public",
    "bio": "public",
    "interests": "public",
    "personality": "matched",
    "available_times": "matched",
    "preferred_locations": "activity_members",
    "self_description": "matched",
    "partner_expectation": "matched",
    "contact_email": "activity_members",
    "contact_qq": "activity_members",
    "contact_wechat": "activity_members",
}


def _option_index(options: tuple[str, ...], value: Any) -> int:
    text = str(value or "")
    return options.index(text) if text in options else 0


def _selected_interest_tags(profile: dict[str, Any], category: str) -> list[str]:
    return [
        str(item["tag"])
        for item in profile.get("interests", [])
        if str(item.get("category")) == category
    ]


def _avatar_bytes(data_url: str) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except ValueError:
        return None


user = require_login()
email = str(user["email"])
stored_profile = get_profile(email)
profile: dict[str, Any] = {
    "display_name": email.split("@", 1)[0],
    "avatar_data_url": "",
    "school": "北京大学",
    "department": "",
    "grade": "",
    "identity_label": "",
    "bio": "",
    "mbti": "",
    "introversion": 3,
    "planning_style": "balanced",
    "warm_up_level": 3,
    "group_size_preference": "any",
    "self_description": "",
    "partner_expectation": "",
    "contact_email": email,
    "contact_qq": "",
    "contact_wechat": "",
    "available_times": [],
    "preferred_locations": [],
    "max_distance_km": 5,
    "allow_cross_school": 0,
    "completion_percent": 0,
    "interests": [],
    "privacy": DEFAULT_PRIVACY,
}
if stored_profile:
    profile.update(stored_profile)

if st.session_state.pop("profile_saved_notice", False):
    st.toast("个人资料已保存", icon=":material/check_circle:")

render_page_intro(
    eyebrow="CAMPUSMATE · 个人资料",
    title="让别人更好地认识你",
    description="这些资料同时服务自由组局和周期搭子匹配；敏感信息由你决定谁能看到。",
)

completion = int(profile.get("completion_percent", 0))
missing_for_matching = matching_profile_missing_fields(
    profile if stored_profile else None,
    profile.get("interests", []),
)

with st.container(border=True):
    summary_left, summary_right = st.columns([1, 4], vertical_alignment="center")
    with summary_left:
        avatar = _avatar_bytes(str(profile.get("avatar_data_url", "")))
        if avatar:
            st.image(avatar, width=112)
        else:
            st.markdown("# :material/account_circle:")
            st.caption("尚未上传头像")
    with summary_right:
        st.subheader(str(profile["display_name"]))
        summary_bits = [
            str(profile.get("school", "")),
            str(profile.get("department", "")),
            str(profile.get("identity_label", "")),
        ]
        st.caption(" · ".join(item for item in summary_bits if item) or "资料尚待完善")
        st.progress(completion, text=f"资料完整度 {completion}%")
        if stored_profile and not missing_for_matching:
            st.badge("已满足周期匹配资料要求", icon=":material/check:", color="green")
        else:
            st.badge("资料仍需完善", icon=":material/edit:", color="orange")

if missing_for_matching:
    st.info(
        "参加周期匹配前还需要补充：" + "、".join(missing_for_matching),
        icon=":material/info:",
    )

with st.form("profile_editor"):
    basic_tab, interests_tab, availability_tab, privacy_tab = st.tabs(
        ["基础资料", "兴趣与性格", "时间与期待", "隐私设置"]
    )

    with basic_tab:
        st.subheader("基础资料")
        st.caption("昵称会固定显示；其他字段均可在隐私设置中控制可见范围。")
        avatar_file = st.file_uploader(
            "上传头像",
            type=["png", "jpg", "jpeg", "webp"],
            max_upload_size=1,
            help="支持 PNG、JPEG、WebP，文件不超过 750 KB。",
        )
        remove_avatar = st.checkbox(
            "移除当前头像",
            value=False,
            disabled=not bool(profile.get("avatar_data_url")),
        )
        basic_left, basic_right = st.columns(2)
        with basic_left:
            display_name = st.text_input(
                "昵称*", value=str(profile["display_name"]), max_chars=30
            )
            school = st.text_input(
                "学校*", value=str(profile.get("school", "北京大学")), max_chars=80
            )
            department = st.text_input(
                "院系", value=str(profile.get("department", "")), max_chars=80
            )
        with basic_right:
            grade = st.selectbox(
                "年级",
                GRADE_OPTIONS,
                index=_option_index(GRADE_OPTIONS, profile.get("grade")),
                format_func=lambda value: value or "请选择",
            )
            identity_label = st.selectbox(
                "身份",
                IDENTITY_OPTIONS,
                index=_option_index(IDENTITY_OPTIONS, profile.get("identity_label")),
                format_func=lambda value: value or "请选择",
            )
            contact_email = st.text_input(
                "联系邮箱", value=str(profile.get("contact_email", email)), max_chars=120
            )
        bio = st.text_area(
            "个人介绍",
            value=str(profile.get("bio", "")),
            max_chars=300,
            placeholder="用一两句话介绍现在的你。",
        )
        st.caption("发布或参加活动前，邮箱、QQ号、微信号至少填写一项。")
        contact_left, contact_right = st.columns(2)
        with contact_left:
            contact_qq = st.text_input(
                "QQ号（可选）",
                value=str(profile.get("contact_qq", "")),
                max_chars=12,
                placeholder="5 至 12 位数字",
            )
        with contact_right:
            contact_wechat = st.text_input(
                "微信号（可选）",
                value=str(profile.get("contact_wechat", "")),
                max_chars=80,
            )

    with interests_tab:
        st.subheader("兴趣标签")
        st.caption("选择你真正愿意一起做的事；可以跨分类多选。")
        selected_interests: dict[str, list[str]] = {}
        for category in ("study", "sport", "entertainment", "share"):
            existing_tags = _selected_interest_tags(profile, category)
            category_options = tuple(
                dict.fromkeys((*INTEREST_OPTIONS[category], *existing_tags))
            )
            selected_interests[category] = st.pills(
                INTEREST_LABELS[category],
                category_options,
                default=existing_tags,
                selection_mode="multi",
                key=f"profile_interests_{category}",
            ) or []
        existing_custom = _selected_interest_tags(profile, "custom")
        selected_interests["custom"] = st.multiselect(
            "自定义兴趣",
            options=existing_custom,
            default=existing_custom,
            accept_new_options=True,
            placeholder="输入标签后按 Enter",
            max_selections=12,
        )

        st.subheader("性格与社交方式")
        personality_left, personality_right = st.columns(2)
        with personality_left:
            mbti = st.selectbox(
                "MBTI（可选）",
                MBTI_OPTIONS,
                index=_option_index(MBTI_OPTIONS, profile.get("mbti")),
                format_func=lambda value: value or "暂不确定",
            )
            introversion = st.select_slider(
                "社交能量",
                options=[1, 2, 3, 4, 5],
                value=int(profile.get("introversion", 3)),
                format_func=lambda value: {
                    1: "偏安静",
                    2: "慢慢熟悉",
                    3: "看场合",
                    4: "比较主动",
                    5: "很有活力",
                }[value],
            )
            warm_up_level = st.select_slider(
                "熟悉速度",
                options=[1, 2, 3, 4, 5],
                value=int(profile.get("warm_up_level", 3)),
                format_func=lambda value: {
                    1: "很快熟",
                    2: "较快",
                    3: "自然相处",
                    4: "需要时间",
                    5: "比较慢热",
                }[value],
            )
        with personality_right:
            planning_values = tuple(PLANNING_OPTIONS)
            planning_style = st.segmented_control(
                "计划方式",
                planning_values,
                default=str(profile.get("planning_style", "balanced")),
                format_func=PLANNING_OPTIONS.get,
                selection_mode="single",
            )
            group_values = tuple(GROUP_SIZE_OPTIONS)
            group_size_preference = st.segmented_control(
                "更舒服的活动规模",
                group_values,
                default=str(profile.get("group_size_preference", "any")),
                format_func=GROUP_SIZE_OPTIONS.get,
                selection_mode="single",
            )

    with availability_tab:
        st.subheader("时间与地点")
        available_times = st.pills(
            "通常有空的时间*",
            TIME_OPTIONS,
            default=list(profile.get("available_times", [])),
            selection_mode="multi",
        ) or []
        preferred_locations = st.multiselect(
            "常用地点*",
            LOCATION_OPTIONS,
            default=list(profile.get("preferred_locations", [])),
            accept_new_options=True,
            placeholder="选择或输入常去地点",
            max_selections=12,
        )
        preference_left, preference_right = st.columns(2)
        with preference_left:
            max_distance_km = st.slider(
                "可接受的活动距离（公里）",
                min_value=0,
                max_value=30,
                value=min(30, int(profile.get("max_distance_km", 5))),
            )
        with preference_right:
            allow_cross_school = st.toggle(
                "接受跨校活动",
                value=bool(profile.get("allow_cross_school", False)),
            )

        st.subheader("关于我和理想搭子")
        self_description = st.text_area(
            "我是什么样的人*",
            value=str(profile.get("self_description", "")),
            max_chars=1000,
            placeholder="例如：慢热但熟悉后很健谈，喜欢提前约好时间。",
        )
        partner_expectation = st.text_area(
            "我想找什么样的人*",
            value=str(profile.get("partner_expectation", "")),
            max_chars=1000,
            placeholder="例如：守时、沟通直接，愿意一起长期坚持运动。",
        )

    with privacy_tab:
        st.subheader("字段级隐私设置")
        st.caption(
            "“匹配成功后”仅对同一匹配结果中的搭子开放；“同活动成员”仅对已经加入同一活动的人开放。"
        )
        privacy_values: dict[str, str] = {}
        privacy_left, privacy_right = st.columns(2)
        privacy_columns = (privacy_left, privacy_right)
        stored_privacy = {**DEFAULT_PRIVACY, **dict(profile.get("privacy", {}))}
        for index, (field_name, field_label) in enumerate(PRIVACY_LABELS.items()):
            with privacy_columns[index % 2]:
                visibility_values = tuple(PRIVACY_OPTIONS)
                current_visibility = stored_privacy.get(field_name, "private")
                privacy_values[field_name] = st.selectbox(
                    f"{field_label}可见范围",
                    visibility_values,
                    index=visibility_values.index(current_visibility),
                    format_func=PRIVACY_OPTIONS.get,
                    key=f"profile_privacy_{field_name}",
                )

    with st.container(key="profile_save_action"):
        submitted = st.form_submit_button(
            "保存个人资料",
            type="primary",
            icon=":material/save:",
            width="content",
        )

if submitted:
    avatar_data_url = str(profile.get("avatar_data_url", ""))
    if remove_avatar:
        avatar_data_url = ""
    elif avatar_file is not None:
        avatar_bytes = avatar_file.getvalue()
        if len(avatar_bytes) > MAX_AVATAR_BYTES:
            st.error("头像文件不能超过 750 KB。", icon=":material/error:")
            st.stop()
        mime_type = str(avatar_file.type).lower()
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            st.error("头像仅支持 PNG、JPEG 或 WebP。", icon=":material/error:")
            st.stop()
        avatar_data_url = (
            f"data:{mime_type};base64,"
            + base64.b64encode(avatar_bytes).decode("ascii")
        )

    interest_rows = [
        (category, tag)
        for category, tags in selected_interests.items()
        for tag in tags
    ]
    # Stage 3 does not expose the legacy social/travel categories in the editor,
    # so preserve any values that already exist instead of silently deleting them.
    interest_rows.extend(
        (str(item["category"]), str(item["tag"]))
        for item in profile.get("interests", [])
        if str(item.get("category")) in {"social", "travel"}
    )
    payload = {
        "display_name": display_name,
        "avatar_data_url": avatar_data_url,
        "school": school,
        "department": department,
        "grade": grade,
        "identity_label": identity_label,
        "bio": bio,
        "mbti": mbti,
        "introversion": introversion,
        "planning_style": planning_style or "balanced",
        "warm_up_level": warm_up_level,
        "group_size_preference": group_size_preference or "any",
        "self_description": self_description,
        "partner_expectation": partner_expectation,
        "contact_email": contact_email,
        "contact_qq": contact_qq,
        "contact_wechat": contact_wechat,
        "available_times": available_times,
        "preferred_locations": preferred_locations,
        "max_distance_km": max_distance_km,
        "allow_cross_school": allow_cross_school,
    }
    try:
        upsert_profile(
            email,
            payload,
            interests=interest_rows,
            privacy=privacy_values,
        )
    except ServiceError as error:
        st.error(str(error), icon=":material/error:")
    else:
        st.session_state["profile_saved_notice"] = True
        st.rerun()
