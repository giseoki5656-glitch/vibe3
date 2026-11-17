"""팀 포털 진입점: 로그인 가드 + 내비게이션."""
import streamlit as st

st.set_page_config(page_title="팀 포털", page_icon="🗂️", layout="wide")

from core import permissions  # noqa: E402
from core.auth import current_user, logout, render_login_page, sync_cookie  # noqa: E402
from core.db import get_engine  # noqa: E402
from services import users as user_service  # noqa: E402
from ui.components import badge  # noqa: E402
from ui.theme import inject_global_css  # noqa: E402

get_engine()  # 스키마 생성 + 시드 (프로세스당 1회)
inject_global_css()

user = current_user()
sync_cookie()  # 로그인 유지 쿠키를 현재 상태에 맞춤 (새로고침 후에도 로그인 유지)

if user is None:
    pg = st.navigation([st.Page(render_login_page, title="로그인", url_path="login")], position="hidden")
    pg.run()
    st.stop()

pages = [
    st.Page("pages/0_홈.py", title="홈", icon="🏠", default=True),
    st.Page("pages/1_스케줄.py", title="스케줄", icon="📅"),
    st.Page("pages/2_게시판.py", title="게시판", icon="📝"),
    st.Page("pages/3_자료.py", title="자료", icon="📁"),
    st.Page("pages/4_마이페이지.py", title="마이페이지", icon="👤"),
]
if permissions.is_admin(user):
    pending = user_service.count_pending(user)
    title = f"관리 ({pending})" if pending else "관리"
    pages.append(st.Page("pages/9_관리.py", title=title, icon="🛠️", url_path="admin"))

with st.sidebar:
    with st.container(border=True):
        st.markdown(f"**{user.name}**  \n`{user.username}`")
        st.markdown(badge("관리자", "red") if permissions.is_admin(user) else badge("팀원", "blue"))
        if st.button("로그아웃", use_container_width=True):
            logout()

st.navigation(pages).run()
