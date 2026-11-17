from functools import partial

import streamlit as st

from core.auth import require_login
from core.errors import ServiceError
from core.models import RESOURCE_CATEGORIES
from core.viewutil import file_icon, human_size
from services import resources as rs
from ui.components import badge, empty_state, page_header

user = require_login()
ss = st.session_state

CAT_KEYS = list(RESOURCE_CATEGORIES)
CAT_COLORS = {"share": "blue", "report": "green", "reference": "orange"}


def _load(resource_id: int) -> bytes:
    return rs.read_file(user, resource_id)[1]


@st.dialog("자료 수정", width="large")
def edit_dialog(r: rs.ResourceView) -> None:
    k = f"redit_{r.id}_"
    title = st.text_input("제목", value=r.title, max_chars=200, key=k + "title")
    cat = st.selectbox(
        "분류", CAT_KEYS, index=CAT_KEYS.index(r.category), format_func=RESOURCE_CATEGORIES.get, key=k + "cat"
    )
    desc = st.text_area("설명", value=r.description or "", key=k + "desc")
    link = None
    if r.is_link:
        link = st.text_input("링크 주소", value=r.link_url, key=k + "link")
    else:
        st.caption(f"📎 {r.file_name} ({human_size(r.file_size)}) — 파일 자체는 교체할 수 없습니다. 새 파일은 새 자료로 등록해 주세요.")

    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("저장", type="primary", key=k + "save", use_container_width=True):
        try:
            rs.update_resource(user, r.id, title=title, category=cat, description=desc, link_url=link)
        except ServiceError as e:
            st.error(str(e))
        else:
            ss["res_flash"] = "자료를 수정했습니다."
            st.rerun()
    if b2.button("삭제", key=k + "del", use_container_width=True):
        ss[k + "confirm"] = True
    if ss.get(k + "confirm"):
        st.warning("이 자료를 삭제할까요? 업로드된 파일도 함께 삭제되며 되돌릴 수 없습니다.")
        y, n, _ = st.columns([1, 1, 3])
        if y.button("삭제 확인", type="primary", key=k + "yes", use_container_width=True):
            try:
                rs.delete_resource(user, r.id)
            except ServiceError as e:
                st.error(str(e))
                ss[k + "confirm"] = False
            else:
                ss["res_flash"] = "자료를 삭제했습니다."
                ss.pop(k + "confirm", None)
                st.rerun()
        if n.button("취소", key=k + "no", use_container_width=True):
            ss[k + "confirm"] = False
            st.rerun(scope="fragment")


def render_list(items: list[rs.ResourceView], tab: str) -> None:
    if not items:
        empty_state("등록된 자료가 없습니다.", "📁")
    for r in items:
        with st.container(border=True):
            left, right = st.columns([5, 2], vertical_alignment="center")
            icon = "🔗" if r.is_link else file_icon(r.file_name)
            left.markdown(f"{icon} **{r.title}**  {badge(r.category_label, CAT_COLORS[r.category])}")
            meta = f"{r.uploader_name} · {r.created_at:%Y-%m-%d %H:%M}"
            if r.file_name:
                meta += f" · {r.file_name} ({human_size(r.file_size)})"
            left.caption(meta)
            if r.description:
                left.write(r.description)
            with right:
                if r.is_link:
                    st.link_button("링크 열기", r.link_url, use_container_width=True)
                else:
                    st.download_button(
                        "다운로드",
                        data=partial(_load, r.id),  # 클릭할 때만 파일을 읽는다
                        file_name=r.file_name or "file",
                        key=f"dl_{tab}_{r.id}",
                        on_click="ignore",
                        use_container_width=True,
                    )
                if r.can_edit and st.button("수정/삭제", key=f"edit_{tab}_{r.id}", use_container_width=True):
                    edit_dialog(r)


# ------------------------------------------------------------------ 화면
if msg := ss.pop("res_flash", None):
    st.toast(msg, icon="✅")

page_header("자료", "공유 · 보고서 · 참고자료를 분류해서 보관합니다.")

with st.expander("＋ 자료 등록", expanded=False):
    kind = st.radio("종류", ["파일 업로드", "링크 등록"], horizontal=True, key="res_kind")
    # 검증 오류 시 입력값을 보존하고, 성공했을 때만 폼 키를 바꿔 초기화한다.
    with st.form(f"res_form_{ss.get('res_form_n', 0)}"):
        c1, c2 = st.columns([3, 1])
        title = c1.text_input("제목", max_chars=200)
        cat = c2.selectbox("분류", CAT_KEYS, format_func=RESOURCE_CATEGORIES.get)
        desc = st.text_area("설명 (선택)")
        upload = link = None
        if kind == "파일 업로드":
            upload = st.file_uploader(
                f"파일 (최대 {rs.MAX_FILE_BYTES // (1024 * 1024)}MB)",
                type=sorted(rs.ALLOWED_EXTENSIONS),
            )
        else:
            link = st.text_input("링크 주소", placeholder="https://")
        submitted = st.form_submit_button("등록", type="primary")
    if submitted:
        try:
            with st.spinner("등록 중..."):
                if kind == "파일 업로드":
                    if upload is None:
                        raise ServiceError("업로드할 파일을 선택해 주세요.")
                    rs.create_resource(
                        user, title=title, category=cat, description=desc,
                        file_name=upload.name, file_bytes=upload.getvalue(),
                    )
                else:
                    rs.create_resource(user, title=title, category=cat, description=desc, link_url=link)
        except ServiceError as e:
            st.error(str(e))
        else:
            ss["res_flash"] = "자료를 등록했습니다."
            ss["res_form_n"] = ss.get("res_form_n", 0) + 1
            st.rerun()

query = st.text_input("검색", key="res_q", placeholder="제목·설명 검색", label_visibility="collapsed")
tab_labels = ["전체"] + list(RESOURCE_CATEGORIES.values())
for tab, label, cat_key in zip(st.tabs(tab_labels), tab_labels, [None] + CAT_KEYS):
    with tab:
        render_list(rs.list_resources(user, category=cat_key, query=query), cat_key or "all")
