"""로그인 유지 세션 서비스. 새로고침해도 쿠키의 토큰으로 로그인 상태를 복원한다."""
import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select

from core.db import session_scope
from core.models import UserSession
from core.timeutil import now_kst
from services.users import CurrentUser, get_current_user

SESSION_DAYS = 7


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> str:
    """새 토큰을 발급해 해시를 저장하고 원문을 반환한다. 만료된 세션은 함께 정리."""
    token = secrets.token_urlsafe(32)
    now = now_kst()
    with session_scope() as s:
        s.execute(delete(UserSession).where(UserSession.expires_at < now))
        s.add(UserSession(user_id=user_id, token_hash=_hash(token), expires_at=now + timedelta(days=SESSION_DAYS)))
    return token


def resolve_session(token: str | None) -> CurrentUser | None:
    """유효(미만료 + 활성 계정)하면 사용자, 아니면 None."""
    if not token or len(token) > 200:
        return None
    with session_scope() as s:
        row = s.scalar(select(UserSession).where(UserSession.token_hash == _hash(token)))
        if row is None or row.expires_at < now_kst():
            return None
        user_id = row.user_id
    return get_current_user(user_id)


def delete_session(token: str | None) -> None:
    if not token:
        return
    with session_scope() as s:
        s.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))
