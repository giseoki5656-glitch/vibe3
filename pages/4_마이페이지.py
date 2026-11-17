from datetime import datetime, time

import streamlit as st

from core.auth import require_login
from core.errors import ServiceError
from core.timeutil import now_kst
from core.viewutil import SCOPE_ICON, color_dot, event_period_text
from services import events as es
from services import posts as ps
from services import resources as rs
from services import users as us
from ui.components import category_badge, empty_state, page_header

user = require_login()
page_header("마이페이지", f"{user.name} ({user.username}) · {'관리자' if user.role == 'admin' else '팀원'}")

tab_events, tab_posts, tab_res, tab_pw = st.tabs(["내 일정", "내 글", "내 자료", "비밀번호 변경"])

with tab_events:
    today = datetime.combine(now_kst().date(), time.min)
    rows = es.list_events(user, today, datetime(2100, 1, 1), member_id=user.id)
    mine = [e for e in rows if e.author_id == user.id]
    st.caption("오늘 이후 내가 작성한 일정")
    if not mine:
        empty_state("예정된 내 일정이 없습니다.", "🗓️")
    for e in mine:
        st.markdown(
            f"{SCOPE_ICON[e.scope]} {color_dot(e.color)} **{e.title}** · {e.type_name}  \n:gray[{event_period_text(e)}]"
        )

with tab_posts:
    posts, total = ps.list_posts(user, author_id=user.id, page_size=50)
    st.caption(f"내가 쓴 글 {total}건 (최근 50건 표시)")
    if not posts:
        empty_state("작성한 글이 없습니다.", "📝")
    for p in posts:
        st.markdown(
            f"**{p.title}** {category_badge(p.category_name)}  \n:gray[{p.created_at:%Y-%m-%d %H:%M} · 댓글 {p.comment_count}]"
        )

with tab_res:
    items = rs.list_resources(user, uploader_id=user.id)
    if not items:
        empty_state("등록한 자료가 없습니다.", "📁")
    for r in items:
        st.markdown(
            f"{'🔗' if r.is_link else '📎'} **{r.title}** :gray-badge[{r.category_label}]  \n:gray[{r.created_at:%Y-%m-%d %H:%M}]"
        )

with tab_pw:
    with st.form("pw_form", clear_on_submit=True):
        old = st.text_input("현재 비밀번호", type="password")
        new1 = st.text_input("새 비밀번호 (8자 이상)", type="password")
        new2 = st.text_input("새 비밀번호 확인", type="password")
        submitted = st.form_submit_button("변경", type="primary")
    if submitted:
        if new1 != new2:
            st.error("새 비밀번호 확인이 일치하지 않습니다.")
        else:
            try:
                us.change_password(user.id, old, new1)
            except ServiceError as e:
                st.error(str(e))
            else:
                st.success("비밀번호를 변경했습니다.")
