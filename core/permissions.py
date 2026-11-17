"""권한 판단 모음 (PRD 2장 권한 매트릭스).

모든 페이지/서비스는 권한을 이 모듈로만 판단한다.
`user` 는 id, role 속성을 가진 객체(CurrentUser 또는 User), None 이면 비로그인으로 본다.
"""
from core.models import ROLE_ADMIN, SCOPE_TEAM


def is_admin(user) -> bool:
    return user is not None and getattr(user, "role", None) == ROLE_ADMIN


def _is_author(user, author_id: int) -> bool:
    return user is not None and user.id == author_id


# --- 일정 ---
def can_view_event(user, event) -> bool:
    """팀 일정과 개인 일정 모두 로그인한 팀원에게 공개."""
    return user is not None


def can_edit_event(user, event) -> bool:
    """팀 일정: 작성자 + 관리자 / 개인 일정: 작성자 본인만(관리자도 불가)."""
    if user is None:
        return False
    if event.scope == SCOPE_TEAM:
        return _is_author(user, event.author_id) or is_admin(user)
    return _is_author(user, event.author_id)


# --- 게시판 ---
def can_post_in_category(user, category) -> bool:
    """공지처럼 admin_only 분류는 관리자만 작성."""
    if user is None:
        return False
    return (not category.admin_only) or is_admin(user)


def can_edit_post(user, post) -> bool:
    return _is_author(user, post.author_id) or is_admin(user)


def can_edit_comment(user, comment) -> bool:
    return _is_author(user, comment.author_id) or is_admin(user)


# --- 자료 ---
def can_edit_resource(user, resource) -> bool:
    return _is_author(user, resource.uploader_id) or is_admin(user)


# --- 관리 ---
def can_manage_users(user) -> bool:
    return is_admin(user)


def can_manage_types(user) -> bool:
    """일정 유형 / 게시판 분류 관리."""
    return is_admin(user)
