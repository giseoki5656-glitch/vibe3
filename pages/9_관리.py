from functools import partial

import streamlit as st

from core.auth import require_admin
from core.errors import ServiceError
from core.models import STATUS_ACTIVE, STATUS_PENDING
from core.timeutil import fmt
from services import events as es
from services import posts as ps
from services import users as us
from ui.components import confirm_dialog, page_header

admin = require_admin()
ss = st.session_state

STATUS_LABEL = {"active": "활성", "disabled": "비활성", "rejected": "거절됨", "pending": "대기"}
ROLE_LABEL = {"member": "팀원", "admin": "관리자"}


def attempt(fn, *args, ok_msg: str | None = None, **kw) -> None:
    """서비스 호출 → 성공 시 rerun, 실패 시 오류 표시."""
    try:
        fn(*args, **kw)
    except ServiceError as e:
        st.error(str(e))
    else:
        if ok_msg:
            ss["admin_flash"] = ok_msg
        st.rerun()


if msg := ss.pop("admin_flash", None):
    st.toast(msg, icon="✅")

page_header("관리", "가입 승인, 사용자, 일정 유형·게시판 분류를 관리합니다.")
pending = us.list_users_by_status(admin, STATUS_PENDING)
tab_pending, tab_users, tab_types = st.tabs([f"가입 승인 ({len(pending)})", "사용자 관리", "유형/분류"])

# ------------------------------------------------------------ 가입 승인
with tab_pending:
    if not pending:
        st.info("승인 대기 중인 가입 신청이 없습니다.")
    for u in pending:
        c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="center")
        c1.markdown(f"**{u.name}** (`{u.username}`)  \n신청: {fmt(u.created_at)}")
        if c2.button("승인", key=f"ok_{u.id}", type="primary", use_container_width=True):
            attempt(us.approve_user, admin, u.id, ok_msg="승인했습니다.")
        if c3.button("거절", key=f"no_{u.id}", use_container_width=True):
            confirm_dialog(
                f"{u.name}({u.username})님의 가입 신청을 거절할까요?",
                partial(us.reject_user, admin, u.id), "거절", success="거절했습니다.",
            )

# ------------------------------------------------------------ 사용자 관리
with tab_users:
    st.caption("본인 계정은 변경할 수 없습니다. (관리자 잠금 방지)")
    for u in us.list_managed_users(admin):
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 2, 2], vertical_alignment="center")
            c1.markdown(
                f"**{u.name}** (`{u.username}`)  \n:gray[{ROLE_LABEL[u.role]} · {STATUS_LABEL[u.status]} · 가입 {fmt(u.created_at)}]"
            )
            if u.id == admin.id:
                c2.caption("(본인)")
                continue
            if u.status == STATUS_ACTIVE:
                if c2.button("비활성화", key=f"dis_{u.id}", use_container_width=True):
                    confirm_dialog(
                        f"{u.name}({u.username}) 계정을 비활성화할까요? 즉시 로그아웃되며 로그인할 수 없게 됩니다.",
                        partial(us.set_user_active, admin, u.id, False), "비활성화", success="비활성화했습니다.",
                    )
            else:
                if c2.button("활성화", key=f"act_{u.id}", use_container_width=True):
                    attempt(us.set_user_active, admin, u.id, True, ok_msg="활성화했습니다.")
            new_role = "member" if u.role == "admin" else "admin"
            if c3.button("관리자 지정" if new_role == "admin" else "팀원으로", key=f"role_{u.id}", use_container_width=True):
                confirm_dialog(
                    f"{u.name}({u.username})님을 '{ROLE_LABEL[new_role]}'(으)로 변경할까요?",
                    partial(us.set_user_role, admin, u.id, new_role), "변경", success="역할을 변경했습니다.",
                )
            with st.expander("비밀번호 초기화"):
                pw = st.text_input("새 비밀번호 (8자 이상)", type="password", key=f"pw_{u.id}")
                if st.button("초기화", key=f"pwbtn_{u.id}"):
                    attempt(us.reset_password, admin, u.id, pw, ok_msg="비밀번호를 초기화했습니다.")

# ------------------------------------------------------------ 유형 / 분류
with tab_types:
    st.subheader("일정 유형")
    st.caption("기본 유형은 삭제할 수 없고, 사용 중인 유형은 삭제 대신 비활성화합니다.")
    for t in es.list_event_types(active_only=False):
        with st.container(border=True):
            c = st.columns([3, 2, 1.2, 1.2, 1.2], vertical_alignment="bottom")
            name = c[0].text_input("이름", value=t.name, key=f"etn_{t.id}")
            color = c[1].color_picker("색상", value=t.color, key=f"etc_{t.id}")
            active = c[2].checkbox("사용", value=t.is_active, key=f"eta_{t.id}")
            if c[3].button("저장", key=f"ets_{t.id}", use_container_width=True):
                attempt(es.update_event_type, admin, t.id, name, color, active, ok_msg="저장했습니다.")
            if c[4].button("삭제", key=f"etd_{t.id}", disabled=t.is_default, use_container_width=True):
                confirm_dialog(
                    f"일정 유형 '{t.name}'을(를) 삭제할까요?",
                    partial(es.delete_event_type, admin, t.id), "삭제", success="삭제했습니다.",
                )
    with st.form("new_type", clear_on_submit=True):
        n1, n2 = st.columns([3, 1], vertical_alignment="bottom")
        nname = n1.text_input("새 유형 이름")
        ncolor = n2.color_picker("색상", value="#8B5CF6")
        if st.form_submit_button("유형 추가"):
            attempt(es.create_event_type, admin, nname, ncolor, ok_msg="유형을 추가했습니다.")

    st.divider()
    st.subheader("게시판 분류")
    for cat in ps.list_categories(active_only=False):
        with st.container(border=True):
            c = st.columns([3, 1.5, 1.2, 1.2], vertical_alignment="bottom")
            name = c[0].text_input("이름", value=cat.name, key=f"pcn_{cat.id}")
            only = c[1].checkbox("관리자만 작성", value=cat.admin_only, key=f"pco_{cat.id}")
            active = c[2].checkbox("사용", value=cat.is_active, key=f"pca_{cat.id}")
            if c[3].button("저장", key=f"pcs_{cat.id}", use_container_width=True):
                attempt(ps.update_category, admin, cat.id, name, only, active, ok_msg="저장했습니다.")
    with st.form("new_cat", clear_on_submit=True):
        m1, m2 = st.columns([3, 1.5], vertical_alignment="bottom")
        cname = m1.text_input("새 분류 이름")
        conly = m2.checkbox("관리자만 작성")
        if st.form_submit_button("분류 추가"):
            attempt(ps.create_category, admin, cname, conly, ok_msg="분류를 추가했습니다.")
