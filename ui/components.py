"""여러 페이지에서 재사용하는 UI 조각 (비즈니스 로직 없음)."""
import html
from typing import Callable

import streamlit as st

from core.errors import ServiceError


def page_header(title: str, description: str | None = None) -> None:
    st.title(title)
    if description:
        st.caption(description)


def badge(text: str, color: str = "gray") -> str:
    """st.markdown 에서 쓰는 배지 문자열. color: gray/red/blue/green/orange/violet ..."""
    return f":{color}-badge[{text}]"


def category_badge(name: str) -> str:
    return badge(name, "red" if name == "공지" else "blue")


def empty_state(message: str, icon: str = "📭") -> None:
    with st.container(border=True):
        st.markdown(f"<div class='center muted' style='padding:1.2rem 0'>{icon}<br>{html.escape(message)}</div>", unsafe_allow_html=True)


def stat_card(label: str, value: int | str, help: str | None = None) -> None:
    st.metric(label, value, help=help, border=True)


def legend_chips(items: list[tuple[str, str]]) -> None:
    """[(이름, #RRGGBB)] 를 색 칩으로 표시."""
    chips = "".join(
        f"<span class='legend-chip' style='background:{c}22;border-color:{c}'>{html.escape(n)}</span>"
        for n, c in items
        if len(c) == 7 and c.startswith("#")
    )
    st.markdown(chips, unsafe_allow_html=True)


@st.dialog("확인")
def confirm_dialog(message: str, action: Callable[[], None], ok_label: str = "확인", success: str | None = None) -> None:
    """파괴적 동작 전 확인 단계. action() 이 ServiceError 를 던지면 메시지를 보여준다."""
    st.warning(message)
    c1, c2 = st.columns(2)
    if c1.button(ok_label, type="primary", use_container_width=True):
        try:
            action()
        except ServiceError as e:
            st.error(str(e))
            return
        if success:
            st.session_state["admin_flash"] = success
        st.rerun()
    if c2.button("취소", use_container_width=True):
        st.rerun()
