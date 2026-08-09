"""Email registration and login page for CampusMate."""

from __future__ import annotations

import streamlit as st

from services.auth import (
    AuthError,
    account_exists,
    authenticate,
    diagnose_mail_service,
    init_db,
    register_user,
    reset_password,
    send_password_reset_code,
    send_verification_code,
    start_persistent_session,
)


init_db()

if st.session_state.get("auth_user"):
    st.switch_page("pages/home.py")

if "login_mode_next" in st.session_state:
    st.session_state["login_mode"] = st.session_state.pop("login_mode_next")
else:
    st.session_state.setdefault("login_mode", "登录")

st.markdown(
    """
    <style>
      .stApp {
        background:
          radial-gradient(circle at 15% 18%, rgba(47, 111, 237, 0.13), transparent 26rem),
          radial-gradient(circle at 82% 88%, rgba(43, 183, 169, 0.16), transparent 28rem),
          linear-gradient(180deg, #ffffff 0%, #f6f8fc 100%) !important;
      }
      div[class*="st-key-login_shell"] {
        padding: 9vh 1.25rem 3rem;
      }
      div[class*="st-key-login_card"] {
        background: rgba(255, 255, 255, 0.94);
        border: 1.5px solid rgba(17, 17, 17, 0.16);
        border-radius: 0.65rem;
        box-shadow: 0 22px 60px rgba(17, 17, 17, 0.12);
        padding: 3rem 3.1rem 2.7rem;
      }
      div[class*="st-key-login_card"] h1 {
        color: #20263a !important;
        font-size: 3rem !important;
        line-height: 1.1 !important;
        text-align: center;
      }
      .login-welcome {
        color: #5d6572 !important;
        font-size: 1.05rem;
        font-weight: 650;
        margin: -0.45rem 0 1.55rem;
        text-align: center;
      }
      div[class*="st-key-login_card"] p,
      div[class*="st-key-login_card"] label,
      div[class*="st-key-login_card"] span {
        color: #5d6572 !important;
      }
      div[class*="st-key-login_card"] [data-testid="stTextInput"] input {
        border-radius: 0.25rem !important;
        min-height: 3.25rem;
      }
      div[class*="st-key-login_card"] div[data-testid="stButton"] > button,
      div[class*="st-key-login_card"] div[data-testid="stFormSubmitButton"] > button {
        min-height: 3.25rem !important;
        border-radius: 0.25rem !important;
        font-weight: 700 !important;
      }
      div[class*="st-key-login_card"] div[data-testid="stFormSubmitButton"] > button {
        background: #cf7f91 !important;
        border: 2px solid #cf7f91 !important;
        color: #ffffff !important;
      }
      div[class*="st-key-login_card"] div[data-testid="stFormSubmitButton"] > button p {
        color: #ffffff !important;
      }
      @media (max-width: 640px) {
        div[class*="st-key-login_card"] {
          padding: 2.1rem 1.35rem 2rem;
        }
        div[class*="st-key-login_card"] h1 {
          font-size: 2.25rem !important;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(key="login_shell"):
    left_space, card_column, right_space = st.columns([1, 1.15, 1])
    with card_column.container(key="login_card"):
        st.title("注册 / 登录")
        st.markdown(
            '<p class="login-welcome">欢迎来到 CampusMate，一起来寻找你的搭子。</p>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("login_notice"):
            st.success(st.session_state.pop("login_notice"))

        mode = st.segmented_control(
            "选择操作",
            ["登录", "注册", "重置密码"],
            key="login_mode",
            label_visibility="collapsed",
        )

        if mode == "登录":
            with st.form("login_form"):
                email = st.text_input(
                    "邮箱",
                    key="login_email",
                    placeholder="your.name@pku.edu.cn / your.name@example.com",
                )
                password = st.text_input("密码", type="password", key="login_password")
                submitted = st.form_submit_button("登录", type="primary")

            if submitted:
                with st.spinner("正在登录，请稍候…", show_time=True):
                    try:
                        user = authenticate(email, password)
                        st.session_state.auth_user = user
                        st.session_state["last_authenticated_route"] = "home"
                        st.session_state["last_authenticated_query_params"] = {}
                        token = start_persistent_session(user)
                    except AuthError as error:
                        st.error(str(error))
                    else:
                        # The authenticated shell writes the cookie once. Keeping
                        # the component off this page avoids a duplicate iframe
                        # handshake and makes one submit sufficient.
                        st.session_state["session_cookie_pending"] = token
                        # This run's navigation map contains only the public page.
                        # A single automatic rerun rebuilds the authenticated map;
                        # app.py then routes to /home without another user click.
                        st.rerun()

            if st.button("忘记密码？点击重置"):
                st.session_state.login_mode_next = "重置密码"
                st.rerun()

        elif mode == "注册":
            register_email = st.text_input(
                "邮箱",
                key="register_email",
                placeholder="your.name@pku.edu.cn / your.name@example.com",
            )
            if st.button("向邮箱发送验证码"):
                try:
                    if account_exists(register_email):
                        st.warning("这个邮箱已经注册，请切换到登录。")
                    else:
                        debug_code = send_verification_code(register_email)
                        if debug_code:
                            st.warning(
                                "线上邮件服务尚未配置 SMTP Secrets，暂时无法真实发到邮箱。"
                                f"课程演示验证码：{debug_code}"
                            )
                        else:
                            st.success("验证码已发送，请检查邮箱和垃圾箱。")
                except AuthError as error:
                    st.error(str(error))

            with st.expander("邮件服务自检"):
                st.caption("用于定位线上发信失败原因；不会显示任何密钥。")
                if st.button("测试邮件服务", key="mail_diagnostic"):
                    try:
                        for line in diagnose_mail_service(register_email):
                            st.write(f"- {line}")
                    except AuthError as error:
                        st.error(str(error))

            with st.form("register_form"):
                code = st.text_input("验证码", max_chars=6, key="register_code")
                password = st.text_input(
                    "设置密码", type="password", key="register_password"
                )
                confirm = st.text_input(
                    "确认密码", type="password", key="register_confirm"
                )
                submitted = st.form_submit_button("确认注册", type="primary")

            if submitted:
                if password != confirm:
                    st.error("两次输入的密码不一致。")
                else:
                    try:
                        register_user(register_email, password, code)
                    except AuthError as error:
                        st.error(str(error))
                    else:
                        st.session_state.login_mode_next = "登录"
                        st.session_state.login_notice = "注册成功，请输入密码登录。"
                        st.rerun()

        else:
            reset_email = st.text_input(
                "注册邮箱",
                key="reset_email",
                placeholder="your.name@pku.edu.cn / your.name@example.com",
            )
            if st.button("向邮箱发送重置验证码"):
                try:
                    debug_code = send_password_reset_code(reset_email)
                    if debug_code:
                        st.warning(
                            "线上邮件服务尚未配置，暂时无法真实发到邮箱。"
                            f"课程演示验证码：{debug_code}"
                        )
                    else:
                        st.success("重置验证码已发送，请检查邮箱和垃圾箱。")
                except AuthError as error:
                    st.error(str(error))

            with st.form("reset_form"):
                code = st.text_input("验证码", max_chars=6, key="reset_code")
                password = st.text_input(
                    "设置新密码", type="password", key="reset_password"
                )
                confirm = st.text_input(
                    "确认新密码", type="password", key="reset_confirm"
                )
                submitted = st.form_submit_button("确认重置密码", type="primary")

            if submitted:
                if password != confirm:
                    st.error("两次输入的密码不一致。")
                else:
                    try:
                        reset_password(reset_email, code, password)
                    except AuthError as error:
                        st.error(str(error))
                    else:
                        st.session_state.login_mode_next = "登录"
                        st.session_state.login_notice = "密码已重置，请使用新密码登录。"
                        st.rerun()
