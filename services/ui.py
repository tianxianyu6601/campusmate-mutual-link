"""Shared, native Streamlit patterns for page introductions and empty states."""

from __future__ import annotations

import streamlit as st


def render_page_intro(*, eyebrow: str, title: str, description: str) -> None:
    st.caption(eyebrow)
    st.title(title)
    st.write(description)


def render_empty_state(
    *,
    icon: str,
    title: str,
    description: str,
    next_step: str,
    action_label: str | None = None,
    action_path: str | None = None,
) -> None:
    with st.container(border=True):
        st.markdown(f"# {icon}")
        st.subheader(title)
        st.write(description)
        st.caption(next_step)
        if action_label and action_path:
            st.page_link(
                action_path,
                label=action_label,
                icon=":material/arrow_forward:",
                width="stretch",
            )
