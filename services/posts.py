"""게시판 서비스 (PRD 4.2)."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from core import permissions
from core.db import session_scope
from core.errors import PermissionDenied, ServiceError
from core.models import Comment, Post, PostCategory, User
from core.timeutil import now_kst

PAGE_SIZE = 10
MAX_TITLE = 200
MAX_CONTENT = 20000
MAX_COMMENT = 2000


@dataclass(frozen=True)
class PostView:
    id: int
    category_id: int
    category_name: str
    title: str
    content: str
    author_id: int
    author_name: str
    is_pinned: bool
    view_count: int
    comment_count: int
    created_at: datetime
    updated_at: datetime
    can_edit: bool


@dataclass(frozen=True)
class CommentView:
    id: int
    post_id: int
    author_id: int
    author_name: str
    content: str
    created_at: datetime
    updated_at: datetime
    can_edit: bool


# ---------------------------------------------------------------- 분류
def list_categories(active_only: bool = True) -> list[PostCategory]:
    with session_scope() as s:
        q = select(PostCategory).order_by(PostCategory.sort_order, PostCategory.id)
        if active_only:
            q = q.where(PostCategory.is_active.is_(True))
        return list(s.scalars(q))


def _clean_category_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 30:
        raise ServiceError("분류 이름을 1~30자로 입력해 주세요.")
    return name


def create_category(actor, name: str, admin_only: bool = False) -> None:
    if not permissions.can_manage_types(actor):
        raise PermissionDenied()
    name = _clean_category_name(name)
    with session_scope() as s:
        if s.scalar(select(PostCategory.id).where(PostCategory.name == name)):
            raise ServiceError("이미 있는 분류 이름입니다.")
        max_order = s.scalar(select(func.max(PostCategory.sort_order))) or 0
        s.add(PostCategory(name=name, admin_only=admin_only, sort_order=max_order + 1))


def update_category(actor, category_id: int, name: str, admin_only: bool, is_active: bool) -> None:
    if not permissions.can_manage_types(actor):
        raise PermissionDenied()
    name = _clean_category_name(name)
    with session_scope() as s:
        cat = s.get(PostCategory, category_id)
        if not cat:
            raise ServiceError("분류를 찾을 수 없습니다.")
        dup = s.scalar(
            select(PostCategory.id).where(PostCategory.name == name, PostCategory.id != category_id)
        )
        if dup:
            raise ServiceError("이미 있는 분류 이름입니다.")
        cat.name, cat.admin_only, cat.is_active = name, admin_only, is_active


# ---------------------------------------------------------------- 게시글
def _clean_post(title: str, content: str) -> tuple[str, str]:
    title, content = (title or "").strip(), (content or "").strip()
    if not title:
        raise ServiceError("제목을 입력해 주세요.")
    if len(title) > MAX_TITLE:
        raise ServiceError(f"제목은 {MAX_TITLE}자 이하로 입력해 주세요.")
    if not content:
        raise ServiceError("본문을 입력해 주세요.")
    if len(content) > MAX_CONTENT:
        raise ServiceError(f"본문은 {MAX_CONTENT}자 이하로 입력해 주세요.")
    return title, content


def _post_view(actor, post: Post, cat_name: str, author_name: str, comment_count: int) -> PostView:
    return PostView(
        id=post.id,
        category_id=post.category_id,
        category_name=cat_name,
        title=post.title,
        content=post.content,
        author_id=post.author_id,
        author_name=author_name,
        is_pinned=post.is_pinned,
        view_count=post.view_count,
        comment_count=comment_count,
        created_at=post.created_at,
        updated_at=post.updated_at,
        can_edit=permissions.can_edit_post(actor, post),
    )


def _base_query():
    cc = (
        select(Comment.post_id, func.count(Comment.id).label("n"))
        .group_by(Comment.post_id)
        .subquery()
    )
    return (
        select(Post, PostCategory.name, User.name, func.coalesce(cc.c.n, 0))
        .join(PostCategory, Post.category_id == PostCategory.id)
        .join(User, Post.author_id == User.id)
        .outerjoin(cc, cc.c.post_id == Post.id)
    )


def list_posts(
    actor,
    *,
    category_id: int | None = None,
    query: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE,
    author_id: int | None = None,
) -> tuple[list[PostView], int]:
    """(해당 페이지 게시글, 전체 개수). 고정글 우선, 최신순."""
    if actor is None:
        raise PermissionDenied()
    page = max(1, page)
    with session_scope() as s:
        q = _base_query()
        if category_id:
            q = q.where(Post.category_id == category_id)
        if author_id:
            q = q.where(Post.author_id == author_id)
        query = (query or "").strip()
        if query:
            q = q.where(
                or_(
                    Post.title.contains(query, autoescape=True),
                    Post.content.contains(query, autoescape=True),
                    User.name.contains(query, autoescape=True),
                )
            )
        total = s.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
        rows = s.execute(
            q.order_by(Post.is_pinned.desc(), Post.created_at.desc(), Post.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
        return [_post_view(actor, p, c, a, n) for p, c, a, n in rows], total


def count_recent(actor, days: int = 7) -> int:
    """최근 N일 이내 작성된 게시글 수 (홈 요약 카드용)."""
    if actor is None:
        raise PermissionDenied()
    since = now_kst() - timedelta(days=days)
    with session_scope() as s:
        return s.scalar(select(func.count(Post.id)).where(Post.created_at >= since)) or 0


def get_post(actor, post_id: int, *, count_view: bool = False) -> PostView:
    if actor is None:
        raise PermissionDenied()
    with session_scope() as s:
        if count_view:
            post = s.get(Post, post_id)
            if post:
                post.view_count += 1
                s.flush()
        row = s.execute(_base_query().where(Post.id == post_id)).first()
        if not row:
            raise ServiceError("게시글을 찾을 수 없습니다. (삭제되었을 수 있습니다)")
        p, c, a, n = row
        return _post_view(actor, p, c, a, n)


def create_post(actor, *, category_id: int, title: str, content: str, pinned: bool = False) -> int:
    if actor is None:
        raise PermissionDenied()
    title, content = _clean_post(title, content)
    with session_scope() as s:
        cat = s.get(PostCategory, category_id)
        if not cat or not cat.is_active:
            raise ServiceError("분류를 선택해 주세요.")
        if not permissions.can_post_in_category(actor, cat):
            raise PermissionDenied(f"'{cat.name}' 분류는 관리자만 작성할 수 있습니다.")
        if pinned and not permissions.is_admin(actor):
            raise PermissionDenied("고정은 관리자만 할 수 있습니다.")
        post = Post(category_id=category_id, title=title, content=content, author_id=actor.id, is_pinned=pinned)
        s.add(post)
        s.flush()
        return post.id


def update_post(
    actor, post_id: int, *, category_id: int, title: str, content: str, pinned: bool | None = None
) -> None:
    title, content = _clean_post(title, content)
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            raise ServiceError("게시글을 찾을 수 없습니다. (삭제되었을 수 있습니다)")
        if not permissions.can_edit_post(actor, post):
            raise PermissionDenied("이 글을 수정할 권한이 없습니다.")
        cat = s.get(PostCategory, category_id)
        if not cat:
            raise ServiceError("분류를 선택해 주세요.")
        if category_id != post.category_id:
            if not cat.is_active:
                raise ServiceError("비활성화된 분류로는 옮길 수 없습니다.")
            if not permissions.can_post_in_category(actor, cat):
                raise PermissionDenied(f"'{cat.name}' 분류는 관리자만 작성할 수 있습니다.")
        if pinned is not None and pinned != post.is_pinned:
            if not permissions.is_admin(actor):
                raise PermissionDenied("고정은 관리자만 할 수 있습니다.")
            post.is_pinned = pinned
        post.category_id, post.title, post.content = category_id, title, content
        post.updated_at = now_kst()


def delete_post(actor, post_id: int) -> None:
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            raise ServiceError("게시글을 찾을 수 없습니다. (이미 삭제되었을 수 있습니다)")
        if not permissions.can_edit_post(actor, post):
            raise PermissionDenied("이 글을 삭제할 권한이 없습니다.")
        s.delete(post)  # 댓글은 cascade 로 함께 삭제


# ---------------------------------------------------------------- 댓글
def _clean_comment(content: str) -> str:
    content = (content or "").strip()
    if not content:
        raise ServiceError("댓글 내용을 입력해 주세요.")
    if len(content) > MAX_COMMENT:
        raise ServiceError(f"댓글은 {MAX_COMMENT}자 이하로 입력해 주세요.")
    return content


def list_comments(actor, post_id: int) -> list[CommentView]:
    if actor is None:
        raise PermissionDenied()
    with session_scope() as s:
        rows = s.execute(
            select(Comment, User.name)
            .join(User, Comment.author_id == User.id)
            .where(Comment.post_id == post_id)
            .order_by(Comment.created_at, Comment.id)
        ).all()
        return [
            CommentView(
                id=c.id,
                post_id=c.post_id,
                author_id=c.author_id,
                author_name=name,
                content=c.content,
                created_at=c.created_at,
                updated_at=c.updated_at,
                can_edit=permissions.can_edit_comment(actor, c),
            )
            for c, name in rows
        ]


def add_comment(actor, post_id: int, content: str) -> int:
    if actor is None:
        raise PermissionDenied()
    content = _clean_comment(content)
    with session_scope() as s:
        if not s.get(Post, post_id):
            raise ServiceError("게시글을 찾을 수 없습니다. (삭제되었을 수 있습니다)")
        c = Comment(post_id=post_id, author_id=actor.id, content=content)
        s.add(c)
        s.flush()
        return c.id


def update_comment(actor, comment_id: int, content: str) -> None:
    content = _clean_comment(content)
    with session_scope() as s:
        c = s.get(Comment, comment_id)
        if not c:
            raise ServiceError("댓글을 찾을 수 없습니다.")
        if not permissions.can_edit_comment(actor, c):
            raise PermissionDenied("이 댓글을 수정할 권한이 없습니다.")
        c.content = content
        c.updated_at = now_kst()


def delete_comment(actor, comment_id: int) -> None:
    with session_scope() as s:
        c = s.get(Comment, comment_id)
        if not c:
            raise ServiceError("댓글을 찾을 수 없습니다.")
        if not permissions.can_edit_comment(actor, c):
            raise PermissionDenied("이 댓글을 삭제할 권한이 없습니다.")
        s.delete(c)
