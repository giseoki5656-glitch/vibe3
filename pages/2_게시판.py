import math

import streamlit as st

from core import permissions
from core.auth import require_login
from core.errors import ServiceError
from core.timeutil import fmt
from core.viewutil import is_edited
from services import posts as ps
from ui.components import category_badge, empty_state, page_header

user = require_login()
ss = st.session_state
ss.setdefault("board_mode", "list")  # list / detail / write / edit
ss.setdefault("board_post_id", None)
ss.setdefault("board_page", 1)
ss.setdefault("board_viewed", set())  # 새로고침(rerun)마다 조회수가 늘지 않도록 세션 내 1회만 집계


def go(mode: str, post_id: int | None = None) -> None:
    ss.board_mode, ss.board_post_id = mode, post_id


def reset_page() -> None:
    ss.board_page = 1


def flash(msg: str) -> None:
    ss["board_flash"] = msg


@st.dialog("삭제 확인")
def confirm_delete(kind: str, target_id: int) -> None:
    label = {"post": "게시글(댓글 포함)", "comment": "댓글"}[kind]
    st.warning(f"이 {label}을 삭제할까요? 되돌릴 수 없습니다.")
    c1, c2 = st.columns(2)
    if c1.button("삭제", type="primary", use_container_width=True):
        try:
            if kind == "post":
                ps.delete_post(user, target_id)
                go("list")
            else:
                ps.delete_comment(user, target_id)
        except ServiceError as e:
            st.error(str(e))
            return
        flash("삭제했습니다.")
        st.rerun()
    if c2.button("취소", use_container_width=True):
        st.rerun()


# ------------------------------------------------------------------ 목록
def render_list() -> None:
    cats = ps.list_categories(active_only=True)
    top1, top2 = st.columns([4, 1], vertical_alignment="bottom")
    cat_id = top1.radio(
        "분류",
        [0] + [c.id for c in cats],
        format_func=lambda i: "전체" if i == 0 else next(c.name for c in cats if c.id == i),
        horizontal=True,
        key="board_cat",
        on_change=reset_page,
    )
    if top2.button("✏️ 글쓰기", type="primary", use_container_width=True):
        go("write")
        st.rerun()
    query = st.text_input(
        "검색", key="board_q", placeholder="제목·본문·작성자 검색", label_visibility="collapsed", on_change=reset_page
    )

    posts, total = ps.list_posts(user, category_id=cat_id or None, query=query, page=ss.board_page)
    pages = max(1, math.ceil(total / ps.PAGE_SIZE))
    if ss.board_page > pages:
        ss.board_page = pages
        st.rerun()

    if not posts:
        empty_state("검색 결과가 없습니다." if query else "아직 게시글이 없습니다. 첫 글을 작성해 보세요!", "📝")
    else:
        with st.container(border=True, key="board_list"):
            for i, p in enumerate(posts):
                if i:
                    st.markdown("<hr style='margin:0.15rem 0;opacity:.35'>", unsafe_allow_html=True)
                tone = "red" if p.category_name == "공지" else "blue"
                title = (
                    f":{tone}[**{p.category_name}**]  "
                    + ("📌 " if p.is_pinned else "")
                    + p.title
                    + (f"  :gray[[{p.comment_count}]]" if p.comment_count else "")
                )
                if st.button(title, key=f"post_{p.id}", type="tertiary", use_container_width=True):
                    go("detail", p.id)
                    st.rerun()
                st.caption(f"{p.author_name} · {p.created_at:%Y-%m-%d %H:%M} · 조회 {p.view_count}")

    p1, p2, p3 = st.columns([1, 2, 1], vertical_alignment="center")
    if p1.button("◀ 이전", disabled=ss.board_page <= 1, use_container_width=True):
        ss.board_page -= 1
        st.rerun()
    p2.markdown(f"<div style='text-align:center'>{ss.board_page} / {pages} 페이지 · 총 {total}건</div>", unsafe_allow_html=True)
    if p3.button("다음 ▶", disabled=ss.board_page >= pages, use_container_width=True):
        ss.board_page += 1
        st.rerun()


# ------------------------------------------------------------------ 상세 + 댓글
def render_detail() -> None:
    pid = ss.board_post_id
    if st.button("← 목록"):
        go("list")
        st.rerun()
    try:
        first = pid not in ss.board_viewed
        post = ps.get_post(user, pid, count_view=first)
        ss.board_viewed.add(pid)
    except ServiceError as e:
        st.error(str(e))
        return

    st.markdown(category_badge(post.category_name))
    st.header(("📌 " if post.is_pinned else "") + post.title)
    edited = " (수정됨)" if is_edited(post.created_at, post.updated_at) else ""
    st.caption(f"{post.author_name} · {fmt(post.created_at)}{edited} · 조회 {post.view_count}")
    with st.container(border=True):
        st.markdown(post.content)

    if post.can_edit:
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("수정", use_container_width=True):
            go("edit", post.id)
            st.rerun()
        if b2.button("삭제", use_container_width=True):
            confirm_delete("post", post.id)

    st.divider()
    comments = ps.list_comments(user, post.id)
    st.subheader(f"댓글 {len(comments)}")
    for c in comments:
        with st.container(border=True):
            edited_c = " (수정됨)" if is_edited(c.created_at, c.updated_at) else ""
            st.caption(f"**{c.author_name}** · {fmt(c.created_at)}{edited_c}")
            edit_key = f"cedit_{c.id}"
            if ss.get(edit_key):
                new_text = st.text_area("댓글 수정", value=c.content, key=f"ctext_{c.id}", label_visibility="collapsed")
                s1, s2, _ = st.columns([1, 1, 4])
                if s1.button("저장", key=f"csave_{c.id}", type="primary", use_container_width=True):
                    try:
                        ps.update_comment(user, c.id, new_text)
                    except ServiceError as e:
                        st.error(str(e))
                    else:
                        ss[edit_key] = False
                        st.rerun()
                if s2.button("취소", key=f"ccancel_{c.id}", use_container_width=True):
                    ss[edit_key] = False
                    st.rerun()
            else:
                st.markdown(c.content)
                if c.can_edit:
                    e1, e2, _ = st.columns([1, 1, 6])
                    if e1.button("수정", key=f"cedit_btn_{c.id}", type="tertiary"):
                        ss[edit_key] = True
                        st.rerun()
                    if e2.button("삭제", key=f"cdel_{c.id}", type="tertiary"):
                        confirm_delete("comment", c.id)

    with st.form("comment_form", clear_on_submit=True):
        text = st.text_area("댓글 작성", placeholder="댓글을 입력하세요", max_chars=ps.MAX_COMMENT)
        if st.form_submit_button("댓글 등록", type="primary"):
            try:
                ps.add_comment(user, post.id, text)
            except ServiceError as e:
                st.error(str(e))
            else:
                st.rerun()


# ------------------------------------------------------------------ 작성 / 수정
def render_form(editing: bool) -> None:
    post = None
    if editing:
        try:
            post = ps.get_post(user, ss.board_post_id)
        except ServiceError as e:
            st.error(str(e))
            if st.button("← 목록"):
                go("list")
                st.rerun()
            return
        if not post.can_edit:
            st.error("이 글을 수정할 권한이 없습니다.")
            return

    st.subheader("글 수정" if editing else "글쓰기")
    cats = [c for c in ps.list_categories(active_only=True) if permissions.can_post_in_category(user, c)]
    if editing and all(c.id != post.category_id for c in cats):  # 현재 분류는 유지 가능
        cats = [c for c in ps.list_categories(active_only=False) if c.id == post.category_id] + cats
    if not cats:
        st.warning("글을 작성할 수 있는 분류가 없습니다.")
        return
    default_idx = 0
    if editing:
        default_idx = next(i for i, c in enumerate(cats) if c.id == post.category_id)
    else:
        default_idx = next((i for i, c in enumerate(cats) if c.name == "자유"), 0)

    with st.form("post_form"):
        cat_id = st.selectbox(
            "분류", [c.id for c in cats], index=default_idx, format_func=lambda i: next(c.name for c in cats if c.id == i)
        )
        title = st.text_input("제목", value=post.title if editing else "", max_chars=ps.MAX_TITLE)
        content = st.text_area(
            "본문 (마크다운 사용 가능)", value=post.content if editing else "", height=320, max_chars=ps.MAX_CONTENT
        )
        pinned = None
        if permissions.is_admin(user):
            pinned = st.checkbox("상단 고정", value=post.is_pinned if editing else False)
        submitted = st.form_submit_button("저장" if editing else "등록", type="primary")
    if st.button("취소"):
        go("detail", post.id) if editing else go("list")
        st.rerun()
    if submitted:
        try:
            if editing:
                ps.update_post(user, post.id, category_id=cat_id, title=title, content=content, pinned=pinned)
                new_id = post.id
            else:
                new_id = ps.create_post(user, category_id=cat_id, title=title, content=content, pinned=bool(pinned))
                ss.board_viewed.add(new_id)  # 작성자 본인의 첫 조회는 집계하지 않음
        except ServiceError as e:
            st.error(str(e))
        else:
            flash("저장했습니다.")
            go("detail", new_id)
            st.rerun()


# ------------------------------------------------------------------ 화면
if msg := ss.pop("board_flash", None):
    st.toast(msg, icon="✅")

page_header("게시판", "팀원 누구나 글을 쓰고 댓글을 달 수 있습니다.")
mode = ss.board_mode
if mode == "detail":
    render_detail()
elif mode == "write":
    render_form(False)
elif mode == "edit":
    render_form(True)
else:
    render_list()
