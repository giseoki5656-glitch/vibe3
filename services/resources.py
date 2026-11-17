"""자료 서비스 (PRD 4.3)."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

from sqlalchemy import or_, select

from core import permissions
from core.db import session_scope
from core.errors import PermissionDenied, ServiceError
from core.models import RESOURCE_CATEGORIES, Resource, User
from core.storage import get_storage, safe_filename

MAX_FILE_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "hwp", "hwpx",
    "txt", "md", "csv", "png", "jpg", "jpeg", "gif", "zip",
}


@dataclass(frozen=True)
class ResourceView:
    id: int
    title: str
    category: str
    category_label: str
    description: str | None
    file_name: str | None
    file_size: int | None
    link_url: str | None
    uploader_id: int
    uploader_name: str
    created_at: datetime
    can_edit: bool

    @property
    def is_link(self) -> bool:
        return bool(self.link_url)


def _clean_common(title: str, category: str, description: str) -> tuple[str, str | None]:
    title = (title or "").strip()
    if not title:
        raise ServiceError("제목을 입력해 주세요.")
    if len(title) > 200:
        raise ServiceError("제목은 200자 이하로 입력해 주세요.")
    if category not in RESOURCE_CATEGORIES:
        raise ServiceError("분류(공유/보고서/참고자료)를 선택해 주세요.")
    return title, (description or "").strip() or None


def _clean_link(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ServiceError("링크는 http:// 또는 https:// 로 시작하는 올바른 주소여야 합니다.")
    if len(url) > 1000:
        raise ServiceError("링크가 너무 깁니다.")
    return url


def check_upload(file_name: str, size: int) -> str:
    """업로드 가능 여부 검사. 통과하면 정리된 파일명을 반환."""
    name = safe_filename(file_name or "")
    ext = PurePosixPath(name).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ServiceError(
            "허용되지 않는 파일 형식입니다. 허용: " + ", ".join(sorted(ALLOWED_EXTENSIONS))
        )
    if size <= 0:
        raise ServiceError("빈 파일은 업로드할 수 없습니다.")
    if size > MAX_FILE_BYTES:
        raise ServiceError(f"파일 크기는 {MAX_FILE_BYTES // (1024 * 1024)}MB 이하여야 합니다.")
    return name


def _view(actor, r: Resource, uploader_name: str) -> ResourceView:
    return ResourceView(
        id=r.id,
        title=r.title,
        category=r.category,
        category_label=RESOURCE_CATEGORIES.get(r.category, r.category),
        description=r.description,
        file_name=r.file_name,
        file_size=r.file_size,
        link_url=r.link_url,
        uploader_id=r.uploader_id,
        uploader_name=uploader_name,
        created_at=r.created_at,
        can_edit=permissions.can_edit_resource(actor, r),
    )


def list_resources(
    actor,
    *,
    category: str | None = None,
    query: str = "",
    limit: int | None = None,
    uploader_id: int | None = None,
) -> list[ResourceView]:
    if actor is None:
        raise PermissionDenied()
    with session_scope() as s:
        q = select(Resource, User.name).join(User, Resource.uploader_id == User.id)
        if category in RESOURCE_CATEGORIES:
            q = q.where(Resource.category == category)
        if uploader_id:
            q = q.where(Resource.uploader_id == uploader_id)
        query = (query or "").strip()
        if query:
            q = q.where(
                or_(
                    Resource.title.contains(query, autoescape=True),
                    Resource.description.contains(query, autoescape=True),
                )
            )
        q = q.order_by(Resource.created_at.desc(), Resource.id.desc())
        if limit:
            q = q.limit(limit)
        return [_view(actor, r, name) for r, name in s.execute(q).all()]


def create_resource(
    actor,
    *,
    title: str,
    category: str,
    description: str = "",
    file_name: str | None = None,
    file_bytes: bytes | None = None,
    link_url: str | None = None,
) -> int:
    """파일 또는 링크 중 하나만 등록한다."""
    if actor is None:
        raise PermissionDenied()
    title, description = _clean_common(title, category, description)
    has_file = file_bytes is not None
    has_link = bool((link_url or "").strip())
    if has_file == has_link:
        raise ServiceError("파일 또는 링크 중 하나만 등록해 주세요.")
    storage_key = clean_name = size = url = None
    if has_file:
        clean_name = check_upload(file_name or "", len(file_bytes))
        size = len(file_bytes)
        storage_key = get_storage().save(file_bytes, clean_name)
    else:
        url = _clean_link(link_url)
    try:
        with session_scope() as s:
            r = Resource(
                title=title,
                category=category,
                description=description,
                storage_key=storage_key,
                file_name=clean_name,
                file_size=size,
                link_url=url,
                uploader_id=actor.id,
            )
            s.add(r)
            s.flush()
            return r.id
    except Exception:
        if storage_key:  # DB 저장 실패 시 고아 파일 제거
            get_storage().delete(storage_key)
        raise


def update_resource(
    actor, resource_id: int, *, title: str, category: str, description: str = "", link_url: str | None = None
) -> None:
    title, description = _clean_common(title, category, description)
    with session_scope() as s:
        r = s.get(Resource, resource_id)
        if not r:
            raise ServiceError("자료를 찾을 수 없습니다. (이미 삭제되었을 수 있습니다)")
        if not permissions.can_edit_resource(actor, r):
            raise PermissionDenied("이 자료를 수정할 권한이 없습니다.")
        if r.link_url:  # 링크 자료만 주소 수정 가능
            r.link_url = _clean_link(link_url or "")
        r.title, r.category, r.description = title, category, description


def delete_resource(actor, resource_id: int) -> None:
    with session_scope() as s:
        r = s.get(Resource, resource_id)
        if not r:
            raise ServiceError("자료를 찾을 수 없습니다. (이미 삭제되었을 수 있습니다)")
        if not permissions.can_edit_resource(actor, r):
            raise PermissionDenied("이 자료를 삭제할 권한이 없습니다.")
        key = r.storage_key
        s.delete(r)
    if key:
        get_storage().delete(key)


def read_file(actor, resource_id: int) -> tuple[str, bytes]:
    """(파일명, 내용). 로그인한 누구나 다운로드 가능."""
    if actor is None:
        raise PermissionDenied()
    with session_scope() as s:
        r = s.get(Resource, resource_id)
        if not r or not r.storage_key:
            raise ServiceError("파일을 찾을 수 없습니다.")
        name, key = r.file_name or "file", r.storage_key
    try:
        return name, get_storage().load(key)
    except FileNotFoundError:
        raise ServiceError("저장소에서 파일을 찾을 수 없습니다.")
