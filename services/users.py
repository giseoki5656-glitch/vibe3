"""사용자 서비스: 가입 신청, 인증, 승인/거절."""
import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from core import permissions
from core.db import session_scope
from core.errors import PermissionDenied, ServiceError
from core.models import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    STATUS_ACTIVE,
    STATUS_DISABLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    LoginAttempt,
    User,
)
from core.security import DUMMY_HASH, hash_password, verify_password
from core.timeutil import now_kst

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
MIN_PASSWORD_LEN = 8

STATUS_MESSAGES = {
    STATUS_PENDING: "가입 승인 대기 중입니다. 관리자가 승인하면 로그인할 수 있습니다.",
    STATUS_REJECTED: "가입 신청이 거절되었습니다. 관리자에게 문의해 주세요.",
    STATUS_DISABLED: "비활성화된 계정입니다. 관리자에게 문의해 주세요.",
}


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    name: str
    role: str


def _to_current(u: User) -> CurrentUser:
    return CurrentUser(id=u.id, username=u.username, name=u.name, role=u.role)


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ServiceError(f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다.")


def register_user(username: str, name: str, password: str) -> None:
    """가입 신청. status=pending 으로 저장되며 승인 전에는 로그인할 수 없다."""
    username, name = username.strip(), name.strip()
    if not USERNAME_RE.match(username):
        raise ServiceError("아이디는 영문/숫자/._- 조합 3~30자로 입력해 주세요.")
    if not name or len(name) > 50:
        raise ServiceError("이름을 1~50자로 입력해 주세요.")
    validate_password(password)
    with session_scope() as s:
        if s.scalar(select(User.id).where(User.username == username)):
            raise ServiceError("이미 사용 중인 아이디입니다.")
        s.add(User(username=username, name=name, password_hash=hash_password(password)))


MAX_LOGIN_FAILURES = 5  # 이 횟수만큼 연속 실패하면 잠금
LOGIN_WINDOW = timedelta(minutes=10)  # 실패를 세는 기간 (첫 실패 이후)
LOGIN_LOCK = timedelta(minutes=10)  # 잠금 시간


def _attempt_key(username: str) -> str:
    return username.strip().lower()[:50]


def _ensure_not_locked(key: str) -> None:
    with session_scope() as s:
        row = s.get(LoginAttempt, key)
        locked_until = row.locked_until if row else None
    now = now_kst()
    if locked_until and locked_until > now:
        minutes = max(1, -(-int((locked_until - now).total_seconds()) // 60))
        raise ServiceError(f"로그인 시도가 너무 많습니다. {minutes}분 후에 다시 시도해 주세요.")


def _record_failure(key: str) -> bool:
    """실패를 기록하고, 이번 실패로 잠겼으면 True. (예외 롤백과 분리하려고 별도 트랜잭션)"""
    now = now_kst()
    with session_scope() as s:
        row = s.get(LoginAttempt, key)
        if row is None:
            row = LoginAttempt(username_key=key, fail_count=0, window_start=now)
            s.add(row)
        if now - row.window_start > LOGIN_WINDOW or (row.locked_until and row.locked_until <= now):
            row.fail_count, row.window_start, row.locked_until = 0, now, None  # 기간/잠금이 지났으면 새로 센다
        row.fail_count += 1
        if row.fail_count >= MAX_LOGIN_FAILURES:
            row.locked_until = now + LOGIN_LOCK
            return True
        return False


def _clear_failures(key: str) -> None:
    with session_scope() as s:
        row = s.get(LoginAttempt, key)
        if row is not None:
            s.delete(row)


def authenticate(username: str, password: str) -> CurrentUser:
    """성공 시 CurrentUser 반환. 실패/미승인 상태는 ServiceError.

    아이디별로 연속 실패가 MAX_LOGIN_FAILURES 회가 되면 LOGIN_LOCK 동안 올바른 비밀번호도 거부한다.
    미승인/비활성 안내는 비밀번호가 맞았을 때만 보이므로 실패로 세지 않는다.
    """
    key = _attempt_key(username)
    _ensure_not_locked(key)
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username.strip()))
        ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
        credentials_ok = bool(user and ok)
        status = user.status if user else None
        current = _to_current(user) if credentials_ok else None
    if not credentials_ok:
        if _record_failure(key):
            raise ServiceError(
                f"로그인에 {MAX_LOGIN_FAILURES}회 실패해 {int(LOGIN_LOCK.total_seconds() // 60)}분간 잠겼습니다."
            )
        raise ServiceError("아이디 또는 비밀번호가 올바르지 않습니다.")
    _clear_failures(key)
    if status != STATUS_ACTIVE:
        raise ServiceError(STATUS_MESSAGES.get(status, "로그인할 수 없는 계정입니다."))
    return current


def get_current_user(user_id: int) -> CurrentUser | None:
    """세션의 사용자가 여전히 active 인지 매 실행마다 확인(비활성화 즉시 반영)."""
    with session_scope() as s:
        user = s.get(User, user_id)
        if not user or user.status != STATUS_ACTIVE:
            return None
        return _to_current(user)


def list_users_by_status(actor, status: str) -> list[User]:
    if not permissions.can_manage_users(actor):
        raise PermissionDenied()
    with session_scope() as s:
        return list(s.scalars(select(User).where(User.status == status).order_by(User.created_at)))


def count_pending(actor) -> int:
    if not permissions.can_manage_users(actor):
        return 0
    return len(list_users_by_status(actor, STATUS_PENDING))


def _decide(actor, user_id: int, new_status: str) -> None:
    if not permissions.can_manage_users(actor):
        raise PermissionDenied()
    with session_scope() as s:
        user = s.get(User, user_id)
        if not user:
            raise ServiceError("대상 사용자를 찾을 수 없습니다.")
        if user.status != STATUS_PENDING:
            raise ServiceError("이미 처리된 가입 신청입니다.")
        user.status = new_status
        user.approved_at = now_kst()
        user.approved_by = actor.id


def approve_user(actor, user_id: int) -> None:
    _decide(actor, user_id, STATUS_ACTIVE)


def reject_user(actor, user_id: int) -> None:
    _decide(actor, user_id, STATUS_REJECTED)


def list_active_users() -> list[tuple[int, str]]:
    """팀원 선택(참석자/필터)용 (id, 이름) 목록. 로그인한 누구나 사용."""
    with session_scope() as s:
        rows = s.execute(
            select(User.id, User.name).where(User.status == STATUS_ACTIVE).order_by(User.name)
        ).all()
        return [(r.id, r.name) for r in rows]


def list_managed_users(actor) -> list[User]:
    """관리 화면용: 승인 대기를 제외한 전체 사용자."""
    if not permissions.can_manage_users(actor):
        raise PermissionDenied()
    with session_scope() as s:
        return list(
            s.scalars(select(User).where(User.status != STATUS_PENDING).order_by(User.created_at))
        )


def _get_target(s, actor, user_id: int) -> User:
    if not permissions.can_manage_users(actor):
        raise PermissionDenied()
    if actor.id == user_id:
        raise ServiceError("본인 계정은 변경할 수 없습니다.")  # 관리자 잠금 방지
    user = s.get(User, user_id)
    if not user:
        raise ServiceError("대상 사용자를 찾을 수 없습니다.")
    if user.status == STATUS_PENDING:
        raise ServiceError("승인 대기 중인 사용자는 가입 승인 탭에서 처리해 주세요.")
    return user


def set_user_active(actor, user_id: int, active: bool) -> None:
    with session_scope() as s:
        user = _get_target(s, actor, user_id)
        user.status = STATUS_ACTIVE if active else STATUS_DISABLED


def set_user_role(actor, user_id: int, role: str) -> None:
    if role not in (ROLE_MEMBER, ROLE_ADMIN):
        raise ServiceError("올바르지 않은 역할입니다.")
    with session_scope() as s:
        _get_target(s, actor, user_id).role = role


def reset_password(actor, user_id: int, new_password: str) -> None:
    validate_password(new_password)
    with session_scope() as s:
        _get_target(s, actor, user_id).password_hash = hash_password(new_password)


def change_password(user_id: int, old_password: str, new_password: str) -> None:
    validate_password(new_password)
    with session_scope() as s:
        user = s.get(User, user_id)
        if not user or not verify_password(old_password, user.password_hash):
            raise ServiceError("현재 비밀번호가 올바르지 않습니다.")
        user.password_hash = hash_password(new_password)
