"""Member 4's interactive, offline AI explanation and feedback page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ai.explanation import generate_match_explanation
from ai.icebreaker import generate_icebreakers
from ai.text_similarity import bidirectional_text_scores
from data.data_loader import load_users
from evaluation.feedback import build_feedback, summarize_feedback


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _candidate_label(profile: dict[str, object]) -> str:
    return f"{profile['user_id']} · {profile['activity']} · {profile['goal']}"


st.markdown('<div class="campusmate-kicker">成员四 · 可解释 AI</div>', unsafe_allow_html=True)
st.title("💡 AI 匹配洞察")
st.caption("使用离线 TF-IDF 语义相似度生成可核验的推荐理由和破冰问题，不上传个人文本。")

current_profile = st.session_state.get("current_profile")
if not current_profile:
    st.warning("请先提交行动卡，再查看你的 AI 匹配洞察。")
    if st.button("去填写行动卡", type="primary"):
        st.switch_page("pages/questionnaire.py")
    st.stop()

candidate_pool = [
    profile
    for profile in load_users(PROJECT_ROOT / "data" / "users.csv")
    if profile["match_type"] == current_profile["match_type"]
]
if not candidate_pool:
    st.info("当前数据集中没有同类型候选人。")
    st.stop()

candidate_ids = [profile["user_id"] for profile in candidate_pool]
selected_id = st.selectbox(
    "选择一位候选人进行 AI 洞察演示",
    options=candidate_ids,
    format_func=lambda user_id: _candidate_label(
        next(profile for profile in candidate_pool if profile["user_id"] == user_id)
    ),
)
candidate = next(profile for profile in candidate_pool if profile["user_id"] == selected_id)

text_scores = bidirectional_text_scores(current_profile, candidate)
left, right = st.columns(2)
with left:
    st.metric("你对候选人的文本契合度", f"{text_scores['a_to_b']:.1f}/100")
with right:
    st.metric("候选人对你的文本契合度", f"{text_scores['b_to_a']:.1f}/100")

st.markdown("### 为什么值得进一步沟通")
for reason in generate_match_explanation(current_profile, candidate, text_scores=text_scores):
    st.write(f"- {reason}")

st.markdown("### 破冰问题")
for index, prompt in enumerate(generate_icebreakers(current_profile, candidate), start=1):
    st.info(f"{index}. {prompt}")

st.markdown("### 对这次推荐的反馈")
with st.form("member4_feedback"):
    match_score = st.slider("你认为这位候选人的匹配程度", 1, 5, 3)
    explanation_helpfulness = st.slider("推荐理由是否有帮助", 1, 5, 3)
    would_meet_again = st.checkbox("我愿意进一步约时间沟通")
    comment = st.text_area("可选建议（不填写联系方式或个人隐私）", max_chars=300)
    submitted = st.form_submit_button("提交匿名反馈", type="primary")

if submitted:
    match_id = "-".join(sorted((str(current_profile["user_id"]), str(candidate["user_id"]))))
    record = build_feedback(
        match_id=match_id,
        match_score=match_score,
        explanation_helpfulness=explanation_helpfulness,
        would_meet_again=would_meet_again,
        comment=comment,
    )
    st.session_state.feedback_records.append(record)
    st.success("反馈已记录在当前演示会话中。")

summary = summarize_feedback(st.session_state.feedback_records)
if summary["response_count"]:
    st.caption(
        f"当前会话已收到 {summary['response_count']} 份反馈：平均匹配评分 "
        f"{summary['average_match_score']}/5，解释帮助度 "
        f"{summary['average_explanation_helpfulness']}/5。"
    )
