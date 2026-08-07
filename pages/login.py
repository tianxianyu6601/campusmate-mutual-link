"""Email registration and login page for CampusMate."""

from __future__ import annotations

import streamlit as st

from services.auth import (
    AuthError,
    account_exists,
    authenticate,
    init_db,
    register_user,
    send_verification_code,
)


init_db()

st.markdown('<div class="campusmate-kicker">CampusMate 账号</div>', unsafe_allow_html=True)
st.title("邮箱登录 / 注册")
st.caption("先用邮箱确认身份，再填写行动卡并参加匹配。")

if st.session_state.get("auth_user"):
    user = st.session_state.auth_user
    st.success(f"已登录：{user['email']}（匿名编号 {user['user_id']}）")
    if st.button("进入首页", type="primary"):
        st.switch_page("pages/home.py")
    if st.button("退出登录"):
        for key in (
            "auth_user",
            "selected_match_type",
            "questionnaire_answers",
            "current_profile",
            "matching_run",
            "current_match",
        ):
            st.session_state[key] = None if key != "questionnaire_answers" else {}
        st.rerun()
    st.stop()

email = st.text_input("邮箱", placeholder="your.name@example.com")
email_ready = bool(email.strip())
existing = False
if email_ready:
    try:
        existing = account_exists(email)
    except AuthError as error:
        st.error(str(error))

if existing:
    st.subheader("已有账号，输入密码登录")
    with st.form("login_form"):
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")
    if submitted:
        try:
            st.session_state.auth_user = authenticate(email, password)
        except AuthError as error:
            st.error(str(error))
        else:
            st.success("登录成功")
            st.switch_page("pages/home.py")
else:
    st.subheader("新邮箱，先发送验证码完成注册")
    st.info("如果部署环境未配置 SMTP，页面会显示验证码用于课程演示；配置后会真实发送到邮箱。")
    if st.button("向邮箱发送验证码", disabled=not email_ready):
        try:
            debug_code = send_verification_code(email)
        except AuthError as error:
            st.error(str(error))
        else:
            if debug_code:
                st.warning(f"邮件服务未配置。演示验证码：{debug_code}")
            else:
                st.success("验证码已发送，请检查邮箱和垃圾箱。")

    with st.form("register_form"):
        code = st.text_input("验证码", max_chars=6)
        password = st.text_input("设置密码", type="password")
        confirm = st.text_input("确认密码", type="password")
        submitted = st.form_submit_button("确认注册", type="primary")
    if submitted:
        if password != confirm:
            st.error("两次输入的密码不一致")
        else:
            try:
                user = register_user(email, password, code)
            except AuthError as error:
                st.error(str(error))
            else:
                st.session_state.auth_user = user
                st.success("注册成功，已自动登录。")
                st.switch_page("pages/home.py")
