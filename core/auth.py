"""로그인 화면, 세션 처리, 페이지 가드."""
import streamlit as st
import streamlit.components.v1 as components

from core import permissions
from core.errors import ServiceError
from services import sessions as session_service
from services import users as user_service

SESSION_KEY = "user_id"
TOKEN_KEY = "session_token"
COOKIE_NAME = "portal_session"


def _cookie_token() -> str | None:
    try:
        return st.context.cookies.get(COOKIE_NAME)
    except Exception:  # 쿠키를 읽을 수 없는 실행 환경
        return None


def current_user():
    """세션의 사용자를 매번 DB 로 재검증해서 반환. 없으면 None.

    새로고침으로 session_state 가 비었어도 쿠키의 토큰이 유효하면 로그인 상태를 복원한다.
    """
    ss = st.session_state
    uid = ss.get(SESSION_KEY)
    if uid is None:
        token = _cookie_token()
        restored = session_service.resolve_session(token) if token else None
        if restored is None:
            return None
        ss[SESSION_KEY], ss[TOKEN_KEY] = restored.id, token
        ss.pop("clear_cookie", None)
        return restored
    user = user_service.get_current_user(uid)
    if user is None:  # 비활성화/삭제된 계정은 즉시 로그아웃
        ss.pop(SESSION_KEY, None)
        session_service.delete_session(ss.pop(TOKEN_KEY, None))
        ss["clear_cookie"] = True
    return user


def start_session(user) -> None:
    """로그인 성공 처리: 세션 상태 + 로그인 유지 토큰 발급."""
    ss = st.session_state
    ss[SESSION_KEY] = user.id
    ss[TOKEN_KEY] = session_service.create_session(user.id)
    ss.pop("clear_cookie", None)


def logout() -> None:
    ss = st.session_state
    session_service.delete_session(ss.pop(TOKEN_KEY, None) or _cookie_token())
    ss.pop(SESSION_KEY, None)
    ss["clear_cookie"] = True
    st.rerun()


def sync_cookie() -> None:
    """브라우저 쿠키를 현재 로그인 상태에 맞춘다. 매 실행마다 호출(멱등).

    쿠키는 JS 로만 설정할 수 있어서 높이 0 인 컴포넌트를 쓴다.
    """
    ss = st.session_state
    token, clear = ss.get(TOKEN_KEY), ss.get("clear_cookie")
    if not token and not clear:
        return
    if token:
        value, age = token, session_service.SESSION_DAYS * 86400
    else:
        value, age = "", 0
    js = (
        "<script>(function(){var p=window.parent;"
        f"var c='{COOKIE_NAME}={value}; max-age={age}; path=/; SameSite=Lax';"
        "if(p.location.protocol==='https:'){c+='; Secure';}"
        "p.document.cookie=c;})();</script>"
    )
    with st.container(key="cookie_sync"):
        components.html(js, height=0)


def require_login():
    """모든 페이지 최상단에서 호출. 로그인 안 되어 있으면 이후 렌더링을 중단."""
    user = current_user()
    if user is None:
        st.warning("로그인이 필요합니다.")
        st.stop()
    return user


def require_admin():
    user = require_login()
    if not permissions.is_admin(user):
        st.error("관리자만 접근할 수 있습니다.")
        st.stop()
    return user


def render_login_page() -> None:
    """로그인/가입 신청 화면."""
    _, center, _ = st.columns([1, 2.2, 1])
    with center:
        st.markdown(
            "<div class='center' style='margin:2rem 0 1.2rem'>"
            "<div style='font-size:2.6rem'>🗂️</div>"
            "<div style='font-size:1.8rem;font-weight:700;letter-spacing:-0.02em'>팀 포털</div>"
            "<div class='muted'>일정 · 게시판 · 자료를 한 곳에서</div></div>",
            unsafe_allow_html=True,
        )
        if st.session_state.pop("signup_done", False):
            st.success("가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.")
        tab_login, tab_signup = st.tabs(["로그인", "가입 신청"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("아이디")
                password = st.text_input("비밀번호", type="password")
                submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
            if submitted:
                try:
                    user = user_service.authenticate(username, password)
                except ServiceError as e:
                    st.error(str(e))
                else:
                    start_session(user)
                    st.rerun()

        with tab_signup:
            st.caption("가입 신청 후 관리자가 승인하면 로그인할 수 있습니다.")
            n = st.session_state.get("signup_form_n", 0)  # 성공 시에만 키를 바꿔 입력값 초기화
            with st.form(f"signup_form_{n}"):
                username = st.text_input("아이디 (영문/숫자 3~30자)", key=f"su_username_{n}")
                name = st.text_input("이름", key=f"su_name_{n}")
                pw1 = st.text_input("비밀번호 (8자 이상)", type="password", key=f"su_pw1_{n}")
                pw2 = st.text_input("비밀번호 확인", type="password", key=f"su_pw2_{n}")
                submitted = st.form_submit_button("가입 신청", use_container_width=True)
            if submitted:
                if pw1 != pw2:
                    st.error("비밀번호 확인이 일치하지 않습니다.")
                else:
                    try:
                        user_service.register_user(username, name, pw1)
                    except ServiceError as e:
                        st.error(str(e))
                    else:
                        st.session_state["signup_form_n"] = n + 1
                        st.session_state["signup_done"] = True
                        st.rerun()
