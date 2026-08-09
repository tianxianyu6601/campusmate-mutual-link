"""CampusMate Streamlit application entrypoint.

Run this file from the project root with::

    streamlit run app.py

The entrypoint owns shared page configuration, navigation, and session state.
Individual pages consume the stable interfaces delivered by Part 1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from services.auth import (
    AuthError,
    clear_persistent_session,
    clear_session_cookie,
    delete_login_session,
    persist_current_session_state,
    read_session_cookie,
    reset_password,
    restore_persistent_session,
    send_password_reset_code,
    write_session_cookie,
)
from services.i18n import CHINESE


PROJECT_ROOT = Path(__file__).resolve().parent
AUTHENTICATED_ROUTE_PATHS = {
    "home": "pages/home.py",
    "profile": "pages/profile.py",
    "activities": "pages/activities.py",
    "cycle_match": "pages/cycle_match.py",
    "messages": "pages/messages.py",
    "questionnaire": "pages/questionnaire.py",
    "matching": "pages/matching.py",
    "result": "pages/result.py",
    "ai_insights": "pages/ai_insights.py",
}

DEFAULT_SESSION_STATE: dict[str, Any] = {
    "auth_user": None,
    "selected_match_type": None,
    "questionnaire_answers": {},
    "current_profile": None,
    "matching_run": None,
    "current_match": None,
    "feedback_records": [],
}


def _initialise_session_state() -> None:
    """Create the cross-page state used by the CampusMate workflow."""

    # The application is Chinese-only. Reset an old bilingual session so a
    # previously selected English value cannot leak into any page.
    st.session_state["language"] = CHINESE
    for key, default_value in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = default_value.copy() if isinstance(default_value, dict) else default_value


def _available_pages(is_authenticated: bool) -> list[st.Page]:
    """Build the public login route and authenticated CampusMate page map."""

    if not is_authenticated:
        return [
            st.Page(
                "pages/login.py",
                title="登录",
                icon="🔐",
                default=True,
            ),
            # Registered only as a hidden post-login transition target. Direct
            # unauthenticated access is still rejected by require_login().
            st.Page(
                "pages/home.py",
                title="首页",
                icon="🏠",
                url_path="home",
            ),
        ]

    pages = [
        st.Page(
            "pages/home.py",
            title="首页",
            icon="🏠",
            url_path="home",
            default=True,
        ),
        st.Page("pages/profile.py", title="个人资料", icon="👤"),
        st.Page("pages/activities.py", title="组局广场", icon="🎉"),
        st.Page("pages/cycle_match.py", title="周期匹配", icon="🔄"),
        st.Page("pages/messages.py", title="我的消息", icon="🔔"),
        st.Page("pages/questionnaire.py", title="填写行动卡", icon="📝"),
    ]

    optional_pages = (
        ("pages/matching.py", "开始匹配", "🔎"),
        ("pages/result.py", "匹配结果", "✨"),
        ("pages/ai_insights.py", "AI 洞察", "💡"),
    )
    for relative_path, title, icon in optional_pages:
        if (PROJECT_ROOT / relative_path).exists():
            pages.append(st.Page(relative_path, title=title, icon=icon))
    return pages


def _inject_login_shell_css() -> None:
    """Keep the unauthenticated shell focused on the login card."""

    st.markdown(
        """
        <style>
          [data-testid="stSidebar"],
          [data-testid="stSidebarCollapseButton"],
          button[data-testid="stExpandSidebarButton"],
          header [data-testid="stToolbar"],
          header [data-testid="stActionButton"] {
            display: none !important;
          }
          .block-container {
            max-width: 100% !important;
            padding: 0 !important;
          }
          [data-testid="stAppViewContainer"] > .main {
            padding-left: 0 !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _logout() -> None:
    token_to_revoke = clear_persistent_session(revoke=False)
    for key, default_value in DEFAULT_SESSION_STATE.items():
        st.session_state[key] = (
            default_value.copy()
            if isinstance(default_value, dict)
            else default_value
        )
    # The server token is already revoked. Delete the browser cookie only
    # after the login page has rendered so Cloud latency cannot leave the old
    # authenticated page visible while the component is mounting.
    st.session_state["session_cookie_delete_pending"] = True
    if token_to_revoke:
        st.session_state["session_token_revoke_pending"] = token_to_revoke


def _request_logout() -> None:
    st.session_state["logout_requested"] = True


@st.dialog("重置密码")
def _reset_password_dialog(current_email: str) -> None:
    st.caption(f"验证码会发送到当前登录邮箱：{current_email}")
    if st.button("发送重置验证码", key="dialog_send_reset_code"):
        try:
            debug_code = send_password_reset_code(current_email)
            if debug_code:
                st.warning(f"课程演示验证码：{debug_code}")
            else:
                st.success("重置验证码已发送，请检查邮箱和垃圾箱。")
        except AuthError as error:
            st.error(str(error))

    with st.form("dialog_reset_password_form"):
        reset_code = st.text_input("验证码", max_chars=6)
        new_password = st.text_input("新密码", type="password")
        confirm_password = st.text_input("确认新密码", type="password")
        submitted = st.form_submit_button("确认重置")

    if submitted:
        if new_password != confirm_password:
            st.error("两次输入的密码不一致。")
        else:
            try:
                reset_password(current_email, reset_code, new_password)
            except AuthError as error:
                st.error(str(error))
            else:
                st.success("密码已重置。")


st.set_page_config(
    page_title="CampusMate",
    page_icon="🤝",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root {
        --campusmate-navy: #111111;
        --campusmate-blue: #2f6fed;
        --campusmate-mint: #2bb7a9;
        --campusmate-paper: #f6f8fc;
      }
      .stApp {
        background:
          radial-gradient(circle at 90% 8%, rgba(47, 111, 237, 0.10), transparent 28rem),
          linear-gradient(180deg, #ffffff 0%, var(--campusmate-paper) 100%);
      }
      .block-container {
        max-width: 1120px;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
      }
      [data-testid="stDecoration"],
      .stDeployButton,
      [data-testid="stAppDeployButton"],
      #MainMenu {
        display: none !important;
      }
      [data-testid="stDialog"] {
        align-items: center !important;
        background: rgba(15, 23, 42, 0.22) !important;
        display: flex !important;
        inset: 0 !important;
        justify-content: center !important;
        margin: 0 !important;
        overflow: hidden !important;
        position: fixed !important;
        transform: none !important;
      }
      [data-testid="stDialog"] > div {
        align-items: center !important;
        justify-content: center !important;
      }
      [data-testid="stDialog"] div[role="dialog"] {
        background: #ffffff !important;
        margin: 0 !important;
        max-height: calc(100vh - 3rem) !important;
        overflow-y: auto !important;
        position: relative !important;
        transform: none !important;
      }
      div[class*="st-key-top_right_settings"] {
        position: fixed !important;
        right: 1.25rem !important;
        top: 0.55rem !important;
        width: auto !important;
        z-index: 999990 !important;
      }
      div[class*="st-key-top_right_settings"] > div {
        width: auto !important;
      }
      div[class*="st-key-top_right_settings"] button {
        background: #ffffff !important;
        border: 1.5px solid #111111 !important;
        border-radius: 0.7rem !important;
        box-shadow: 0 2px 9px rgba(17, 17, 17, 0.12) !important;
        color: #111111 !important;
        font-weight: 700 !important;
        min-height: 2.55rem !important;
        padding: 0.35rem 0.9rem !important;
      }
      div[class*="st-key-top_right_settings"] button:hover {
        background: #f2f5fb !important;
        border-color: #2f6fed !important;
      }
      [data-testid="stSidebarCollapseButton"] button,
      button[data-testid="stExpandSidebarButton"] {
        align-items: center !important;
        background: #111111 !important;
        border: 2px solid #ffffff !important;
        border-radius: 999px !important;
        box-shadow: 0 3px 12px rgba(17, 17, 17, 0.28) !important;
        display: flex !important;
        height: 3.1rem !important;
        justify-content: center !important;
        min-height: 3.1rem !important;
        min-width: 3.1rem !important;
        padding: 0 !important;
        transition: background 150ms ease, box-shadow 150ms ease, transform 150ms ease !important;
        width: 3.1rem !important;
      }
      [data-testid="stSidebarCollapseButton"] button span,
      button[data-testid="stExpandSidebarButton"] span,
      [data-testid="stSidebarCollapseButton"] button svg,
      button[data-testid="stExpandSidebarButton"] svg {
        color: #ffffff !important;
        fill: #ffffff !important;
        font-size: 2rem !important;
      }
      [data-testid="stSidebarCollapseButton"] button:hover,
      button[data-testid="stExpandSidebarButton"]:hover {
        background: #2f6fed !important;
        box-shadow: 0 5px 16px rgba(47, 111, 237, 0.38) !important;
        transform: scale(1.07);
      }
      [data-testid="stSidebarCollapseButton"] button:focus-visible,
      button[data-testid="stExpandSidebarButton"]:focus-visible {
        outline: 3px solid rgba(47, 111, 237, 0.42) !important;
        outline-offset: 2px !important;
      }
      [data-testid="stMain"] {
        color: #111111;
      }
      [data-testid="stMain"] h1,
      [data-testid="stMain"] h2,
      [data-testid="stMain"] h3,
      [data-testid="stMain"] h4,
      [data-testid="stMain"] label,
      [data-testid="stMain"] li {
        color: #111111 !important;
      }
      [data-testid="stMain"] div[data-testid="stCaptionContainer"] p {
        color: #333333 !important;
      }
      [data-testid="stMultiSelect"] [data-baseweb="tag"],
      [data-baseweb="select"] [data-baseweb="tag"],
      [data-testid="stMultiSelectTagsContainer"] [data-tag] {
        background: #eef4ff !important;
        border: 1.5px solid #2f6fed !important;
        border-radius: 0.5rem !important;
        box-shadow: none !important;
        color: #17324d !important;
        min-height: 2rem !important;
        padding-left: 0.35rem !important;
      }
      [data-testid="stMultiSelect"] [data-baseweb="tag"] span,
      [data-testid="stMultiSelect"] [data-baseweb="tag"] div,
      [data-baseweb="select"] [data-baseweb="tag"] span,
      [data-baseweb="select"] [data-baseweb="tag"] div,
      [data-testid="stMultiSelectTagsContainer"] [data-tag] span {
        color: #17324d !important;
        font-weight: 600 !important;
        opacity: 1 !important;
      }
      [data-testid="stMultiSelect"] [data-baseweb="tag"] svg,
      [data-baseweb="select"] [data-baseweb="tag"] svg,
      [data-testid="stMultiSelectTagsContainer"] [data-tag] button,
      [data-testid="stMultiSelectTagsContainer"] [data-tag] svg {
        color: #49627d !important;
        fill: #49627d !important;
      }
      [data-testid="stMultiSelect"] [data-baseweb="tag"]:hover,
      [data-baseweb="select"] [data-baseweb="tag"]:hover,
      [data-testid="stMultiSelectTagsContainer"] [data-tag]:hover {
        background: #dde9ff !important;
        border-color: #174ea6 !important;
      }
      div[data-testid="stButton"] > button,
      div[data-testid="stFormSubmitButton"] > button {
        border-radius: 0.75rem;
        min-height: 2.8rem;
        font-weight: 650;
      }
      div[data-testid="stFormSubmitButton"] > button {
        width: auto !important;
        min-width: 8.5rem !important;
        min-height: 3.25rem !important;
        background: #ffffff !important;
        border: 2px solid #111111 !important;
        border-radius: 0.35rem !important;
        color: #111111 !important;
        box-shadow: none !important;
        white-space: nowrap !important;
      }
      div[data-testid="stFormSubmitButton"] > button:hover {
        background: #eef4ff !important;
        border-color: #276ef1 !important;
      }
      div[data-testid="stFormSubmitButton"] > button p,
      div[data-testid="stFormSubmitButton"] > button span {
        width: auto !important;
        margin: 0 !important;
        color: #111111 !important;
        text-align: center !important;
        white-space: nowrap !important;
      }
      [data-testid="stMain"] div[data-testid="stButton"] > button[kind="primary"],
      [data-testid="stMain"] div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
        background: #2f6fed !important;
        border-color: #2f6fed !important;
        color: #ffffff !important;
      }
      [data-testid="stMain"] div[data-testid="stButton"] > button[kind="primary"]:hover,
      [data-testid="stMain"] div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
        background: #2459c7 !important;
        border-color: #2459c7 !important;
      }
      [data-testid="stMain"] div[data-testid="stButton"] > button[kind="primary"] p,
      [data-testid="stMain"] div[data-testid="stButton"] > button[kind="primary"] span,
      [data-testid="stMain"] div[data-testid="stFormSubmitButton"] > button[kind="primary"] p,
      [data-testid="stMain"] div[data-testid="stFormSubmitButton"] > button[kind="primary"] span {
        color: #ffffff !important;
      }
      div[class*="st-key-profile_save_action"] {
        max-width: 100%;
        width: 18rem;
      }
      div[class*="st-key-profile_save_action"] div[data-testid="stFormSubmitButton"] {
        width: 100%;
      }
      div[class*="st-key-profile_save_action"] div[data-testid="stFormSubmitButton"] > button {
        min-height: 3.15rem !important;
        width: 100% !important;
        white-space: nowrap !important;
      }
      div[class*="st-key-profile_save_action"] div[data-testid="stFormSubmitButton"] > button p,
      div[class*="st-key-profile_save_action"] div[data-testid="stFormSubmitButton"] > button span {
        width: auto !important;
        white-space: nowrap !important;
      }
      div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1.5px solid #111111;
        border-radius: 0.9rem;
        padding: 0.9rem 1rem;
      }
      div[data-testid="stMetric"] label,
      div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #111111 !important;
      }
      .campusmate-kicker {
        color: var(--campusmate-blue);
        font-size: 0.88rem;
        font-weight: 750;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .campusmate-muted {
        color: #111111 !important;
      }
      div[class*="st-key-portal_card_"],
      div[class*="st-key-mate_card_"] {
        background: #ffffff !important;
        border: 2px solid #111111 !important;
        border-radius: 1rem !important;
        box-shadow: 0 8px 20px rgba(17, 17, 17, 0.07);
        padding: 0.55rem;
      }
      div[class*="st-key-mate_card_"] .mate-card-icon {
        align-items: center;
        display: flex;
        font-size: 3.4rem;
        justify-content: center;
        line-height: 1.2;
        min-height: 7.5rem;
      }
      div[class*="st-key-portal_card_"] div[data-testid="stButton"] > button,
      div[class*="st-key-mate_card_"] div[data-testid="stButton"] > button {
        background: #111111 !important;
        border: 2px solid #111111 !important;
        color: #ffffff !important;
      }
      div[class*="st-key-portal_card_"] div[data-testid="stButton"] > button p,
      div[class*="st-key-portal_card_"] div[data-testid="stButton"] > button span,
      div[class*="st-key-mate_card_"] div[data-testid="stButton"] > button p,
      div[class*="st-key-mate_card_"] div[data-testid="stButton"] > button span {
        color: #ffffff !important;
      }
      div[class*="st-key-portal_card_"] div[data-testid="stButton"] > button:hover,
      div[class*="st-key-mate_card_"] div[data-testid="stButton"] > button:hover {
        background: #333333 !important;
        border-color: #333333 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

_initialise_session_state()
if not st.session_state.get("_browser_session_cookie_checked"):
    cookie_ready, browser_session_token = read_session_cookie()
    if not cookie_ready:
        st.stop()
    st.session_state["_browser_session_cookie_checked"] = True
    if browser_session_token:
        st.session_state["session_token"] = browser_session_token

logged_out_now = st.session_state.pop("logout_requested", False)
if logged_out_now:
    _logout()
else:
    restore_persistent_session()

is_authenticated = bool(st.session_state.get("auth_user"))
available_pages = _available_pages(is_authenticated)
navigation = st.navigation(available_pages, position="hidden")
requested_route = str(navigation.url_path or "")

if is_authenticated and not requested_route:
    if st.session_state.pop("login_transition_pending", False):
        # Home is already the authenticated default. Avoid a second automatic
        # page switch immediately after a successful login.
        st.session_state["last_authenticated_route"] = "home"
        st.session_state["last_authenticated_query_params"] = {}
    else:
        restored_route = str(st.session_state.get("last_authenticated_route") or "home")
        restored_path = AUTHENTICATED_ROUTE_PATHS.get(
            restored_route,
            AUTHENTICATED_ROUTE_PATHS["home"],
        )
        restored_query_params = st.session_state.get("last_authenticated_query_params")
        if restored_query_params:
            st.switch_page(restored_path, query_params=dict(restored_query_params))
        else:
            st.switch_page(restored_path)
elif is_authenticated:
    st.session_state.pop("login_transition_pending", None)

pending_cookie: str | None = None
if is_authenticated:
    if requested_route in AUTHENTICATED_ROUTE_PATHS:
        st.session_state["last_authenticated_route"] = requested_route
        st.session_state["last_authenticated_query_params"] = dict(st.query_params)
    pending_cookie_value = st.session_state.pop("session_cookie_pending", None)
    if pending_cookie_value:
        pending_cookie = str(pending_cookie_value)

if not is_authenticated:
    _inject_login_shell_css()

if is_authenticated:
    with st.sidebar:
        st.markdown("## 🤝 CampusMate")
        user = st.session_state.auth_user
        st.success(f"已登录：{user['email']}")
        current_email = str(user["email"])
        reset_col, logout_col = st.columns(2)
        with reset_col:
            if st.button("重置密码", key="open_reset_password_dialog"):
                _reset_password_dialog(current_email)
        with logout_col:
            st.button(
                "退出登录",
                key="logout_button",
                on_click=_request_logout,
            )

        st.page_link(
            "pages/home.py",
            label="首页",
            icon="🏠",
            width="stretch",
        )
        st.page_link(
            "pages/profile.py",
            label="个人资料",
            icon="👤",
            width="stretch",
        )
        st.page_link(
            "pages/activities.py",
            label="组局广场",
            icon="🎉",
            width="stretch",
        )
        st.page_link(
            "pages/cycle_match.py",
            label="周期匹配",
            icon="🔄",
            width="stretch",
        )
        st.page_link(
            "pages/messages.py",
            label="我的消息",
            icon="🔔",
            width="stretch",
        )
        st.divider()
        st.markdown("**当前搭子偏好**")
        selected_type = st.session_state.get("selected_match_type")
        type_icons = {"study": "📚", "sport": "🏃", "interest": "🎨"}
        type_labels_zh = {
            "study": "学习搭子",
            "sport": "运动搭子",
            "interest": "兴趣活动搭子",
        }
        if selected_type in type_labels_zh:
            selected_label = type_labels_zh[selected_type]
            st.success(f"当前选择：{type_icons[selected_type]} {selected_label}")
        else:
            st.info("请先在首页选择搭子类型")

    with st.container(key="top_right_settings"):
        with st.popover("⚙️ 设置", help="查看应用部署选项"):
            st.markdown("### 部署应用")
            st.caption("选择适合项目用途的部署方式。")

            community_tab, snowflake_tab, custom_tab = st.tabs(
                ["社区云", "Snowflake", "其他平台"]
            )

            with community_tab:
                st.markdown("#### Streamlit 社区云")
                st.write("适合个人项目、课程作业与学习展示，可免费部署公开应用。")
                st.markdown(
                    "- 连接 GitHub 仓库后快速部署\n"
                    "- 支持公开应用和分享链接\n"
                    "- 可浏览并学习社区中的热门应用"
                )
                st.link_button(
                    "立即部署",
                    "https://share.streamlit.io/",
                    use_container_width=True,
                )
                st.link_button(
                    "查看部署说明",
                    "https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy",
                    use_container_width=True,
                )

            with snowflake_tab:
                st.markdown("#### Snowflake")
                st.write("适合需要企业级安全、数据集成和托管基础设施的应用。")
                st.markdown(
                    "- 使用企业级权限与安全管理\n"
                    "- 部署带角色访问控制的私有应用\n"
                    "- 与 Snowflake 数据平台直接集成"
                )
                st.link_button(
                    "查看部署指南",
                    "https://docs.snowflake.com/en/developer-guide/streamlit/getting-started/overview",
                    use_container_width=True,
                )

            with custom_tab:
                st.markdown("#### 自定义部署")
                st.write("适合部署到自有硬件、服务器或其他云服务。")
                st.markdown(
                    "- 自行选择服务器或云平台\n"
                    "- 自主管理身份认证和运行资源\n"
                    "- 自主控制运维方式与成本"
                )
                st.link_button(
                    "查看其他部署方式",
                    "https://docs.streamlit.io/deploy/tutorials",
                    use_container_width=True,
                )

            st.caption("部署操作会在对应平台中完成，不会修改本地问卷数据。")

navigation.run()

# Revoke the old server session and update the browser cookie only after the
# destination page has drawn. This makes logout visibly immediate without
# weakening the final server-side logout result.
token_to_revoke = st.session_state.pop("session_token_revoke_pending", None)
if token_to_revoke:
    delete_login_session(str(token_to_revoke))
if pending_cookie:
    write_session_cookie(pending_cookie)
if st.session_state.pop("session_cookie_delete_pending", False):
    clear_session_cookie()

# Persist route and workflow state after the page has streamed its visible UI.
# The database write no longer blocks the page transition or leaves stale UI
# on screen while the new page is waiting to render.
if is_authenticated:
    persist_current_session_state()
