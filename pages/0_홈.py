from datetime import datetime, time, timedelta

import streamlit as st

from core.auth import require_login
from core.timeutil import now_kst
from core.viewutil import SCOPE_ICON, color_dot, event_period_text, event_time_text
from services import events as es
from services import posts as ps
from services import resources as rs
from ui.components import category_badge, badge, empty_state, page_header, stat_card

user = require_login()
today = now_kst().date()
monday = today - timedelta(days=today.weekday())

page_header("홈", f"{user.name}님, 안녕하세요. 오늘은 {today:%Y년 %m월 %d일}입니다.")

mine = es.list_events(
    user, datetime.combine(today, time.min), datetime.combine(today + timedelta(days=1), time.min), member_id=user.id
)
team = es.list_events(
    user,
    datetime.combine(monday, time.min),
    datetime.combine(monday + timedelta(days=7), time.min),
    scope="team",
)
posts, _ = ps.list_posts(user, page_size=5)
recent = rs.list_resources(user, limit=5)

s1, s2, s3 = st.columns(3)
with s1:
    stat_card("오늘 내 일정", f"{len(mine)}건")
with s2:
    stat_card("이번 주 팀 일정", f"{len(team)}건")
with s3:
    stat_card("최근 7일 새 글", f"{ps.count_recent(user, 7)}건")

left, right = st.columns(2)

with left:
    with st.container(border=True):
        st.subheader("오늘 내 일정")
        if not mine:
            st.caption("오늘 일정이 없습니다.")
        for e in mine:
            st.markdown(
                f"{SCOPE_ICON[e.scope]} {color_dot(e.color)} **{e.title}**  \n"
                f":gray[{e.type_name} · {event_time_text(e, today)}]"
            )
        st.page_link("pages/1_스케줄.py", label="스케줄 열기 →")

    with st.container(border=True):
        st.subheader("이번 주 팀 일정")
        if not team:
            st.caption("이번 주 팀 일정이 없습니다.")
        for e in team:
            st.markdown(
                f"{color_dot(e.color)} **{e.title}** {badge(e.type_name)}  \n"
                f":gray[{event_period_text(e)} · {e.author_name}]"
            )

with right:
    with st.container(border=True):
        st.subheader("최근 게시글")
        if not posts:
            st.caption("게시글이 없습니다.")
        for p in posts:
            st.markdown(
                f"{'📌 ' if p.is_pinned else ''}**{p.title}** {category_badge(p.category_name)}  \n"
                f":gray[{p.author_name} · {p.created_at:%m-%d %H:%M} · 댓글 {p.comment_count}]"
            )
        st.page_link("pages/2_게시판.py", label="게시판 열기 →")

    with st.container(border=True):
        st.subheader("최근 자료")
        if not recent:
            st.caption("등록된 자료가 없습니다.")
        for r in recent:
            st.markdown(
                f"{'🔗' if r.is_link else '📎'} **{r.title}** {badge(r.category_label)}  \n"
                f":gray[{r.uploader_name} · {r.created_at:%m-%d %H:%M}]"
            )
        st.page_link("pages/3_자료.py", label="자료 열기 →")
