"""일정 서비스 (PRD 4.1). 권한은 core.permissions 로 판단하고 서버단에서 재검증한다."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select

from core import permissions
from core.db import session_scope
from core.errors import PermissionDenied, ServiceError
from core.models import (
    SCOPE_PERSONAL,
    SCOPE_TEAM,
    Event,
    EventAttendee,
    EventType,
    User,
)
from core.timeutil import now_kst

SCOPES = (SCOPE_PERSONAL, SCOPE_TEAM)
SCOPE_LABELS = {SCOPE_PERSONAL: "개인", SCOPE_TEAM: "팀"}


@dataclass(frozen=True)
class EventView:
    id: int
    title: str
    scope: str
    type_id: int
    type_name: str
    color: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    location: str | None
    description: str | None
    author_id: int
    author_name: str
    attendee_ids: tuple[int, ...]
    attendee_names: tuple[str, ...]
    can_edit: bool


# ---------------------------------------------------------------- 일정 유형
def list_event_types(active_only: bool = True) -> list[EventType]:
    with session_scope() as s:
        q = select(EventType).order_by(EventType.sort_order, EventType.id)
        if active_only:
            q = q.where(EventType.is_active.is_(True))
        return list(s.scalars(q))


def _clean_type_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 30:
        raise ServiceError("유형 이름을 1~30자로 입력해 주세요.")
    return name


def _check_color(color: str) -> str:
    color = color.strip()
    if len(color) != 7 or not color.startswith("#") or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
        raise ServiceError("색상은 #RRGGBB 형식이어야 합니다.")
    return color.upper()


def create_event_type(actor, name: str, color: str) -> None:
    if not permissions.can_manage_types(actor):
        raise PermissionDenied()
    name, color = _clean_type_name(name), _check_color(color)
    with session_scope() as s:
        if s.scalar(select(EventType.id).where(EventType.name == name)):
            raise ServiceError("이미 있는 유형 이름입니다.")
        max_order = s.scalar(select(func.max(EventType.sort_order))) or 0
        s.add(EventType(name=name, color=color, sort_order=max_order + 1))


def update_event_type(actor, type_id: int, name: str, color: str, is_active: bool) -> None:
    if not permissions.can_manage_types(actor):
        raise PermissionDenied()
    name, color = _clean_type_name(name), _check_color(color)
    with session_scope() as s:
        et = s.get(EventType, type_id)
        if not et:
            raise ServiceError("유형을 찾을 수 없습니다.")
        dup = s.scalar(select(EventType.id).where(EventType.name == name, EventType.id != type_id))
        if dup:
            raise ServiceError("이미 있는 유형 이름입니다.")
        et.name, et.color, et.is_active = name, color, is_active


def delete_event_type(actor, type_id: int) -> None:
    """기본 유형은 삭제 불가, 사용 중인 유형은 삭제 대신 비활성화."""
    if not permissions.can_manage_types(actor):
        raise PermissionDenied()
    with session_scope() as s:
        et = s.get(EventType, type_id)
        if not et:
            raise ServiceError("유형을 찾을 수 없습니다.")
        if et.is_default:
            raise ServiceError("기본 유형은 삭제할 수 없습니다. (비활성화는 가능)")
        if s.scalar(select(Event.id).where(Event.type_id == type_id).limit(1)):
            raise ServiceError("사용 중인 유형은 삭제할 수 없습니다. 비활성화해 주세요.")
        s.delete(et)


# ---------------------------------------------------------------- 일정 CRUD
def _validate(
    s,
    title: str,
    scope: str,
    type_id: int,
    start_at: datetime,
    end_at: datetime,
    all_day: bool,
    attendee_ids,
    current_type_id: int | None = None,
):
    title = (title or "").strip()
    if not title:
        raise ServiceError("제목을 입력해 주세요.")
    if len(title) > 200:
        raise ServiceError("제목은 200자 이하로 입력해 주세요.")
    if scope not in SCOPES:
        raise ServiceError("범위(개인/팀)를 선택해 주세요.")
    et = s.get(EventType, type_id)
    if not et:
        raise ServiceError("유형을 선택해 주세요.")
    if not et.is_active and type_id != current_type_id:  # 기존 일정이 쓰던 비활성 유형은 유지 가능
        raise ServiceError("비활성화된 유형은 선택할 수 없습니다.")
    if all_day:
        start_at = datetime.combine(start_at.date(), time.min)
        end_at = datetime.combine(end_at.date(), time(23, 59))
        if end_at.date() < start_at.date():
            raise ServiceError("종료일은 시작일보다 빠를 수 없습니다.")
    elif end_at < start_at:
        raise ServiceError("종료 일시는 시작 일시보다 빠를 수 없습니다.")
    ids = sorted({int(i) for i in (attendee_ids or [])}) if scope == SCOPE_TEAM else []
    if ids:
        found = set(s.scalars(select(User.id).where(User.id.in_(ids), User.status == "active")))
        if found != set(ids):
            raise ServiceError("참석자 중 유효하지 않은 사용자가 있습니다.")
    return title, start_at, end_at, ids


def _set_attendees(s, event: Event, ids: list[int]) -> None:
    event.attendees.clear()
    s.flush()
    for uid in ids:
        event.attendees.append(EventAttendee(user_id=uid))


def create_event(
    actor,
    *,
    title: str,
    scope: str,
    type_id: int,
    start_at: datetime,
    end_at: datetime,
    all_day: bool = False,
    location: str = "",
    description: str = "",
    attendee_ids=(),
) -> int:
    if actor is None:
        raise PermissionDenied()
    with session_scope() as s:
        title, start_at, end_at, ids = _validate(
            s, title, scope, type_id, start_at, end_at, all_day, attendee_ids
        )
        ev = Event(
            title=title,
            scope=scope,
            type_id=type_id,
            start_at=start_at,
            end_at=end_at,
            all_day=all_day,
            location=(location or "").strip()[:200] or None,
            description=(description or "").strip() or None,
            author_id=actor.id,
        )
        s.add(ev)
        s.flush()
        _set_attendees(s, ev, ids)
        return ev.id


def update_event(
    actor,
    event_id: int,
    *,
    title: str,
    scope: str,
    type_id: int,
    start_at: datetime,
    end_at: datetime,
    all_day: bool = False,
    location: str = "",
    description: str = "",
    attendee_ids=(),
) -> None:
    with session_scope() as s:
        ev = s.get(Event, event_id)
        if not ev:
            raise ServiceError("일정을 찾을 수 없습니다. (이미 삭제되었을 수 있습니다)")
        if not permissions.can_edit_event(actor, ev):
            raise PermissionDenied("이 일정을 수정할 권한이 없습니다.")
        title, start_at, end_at, ids = _validate(
            s, title, scope, type_id, start_at, end_at, all_day, attendee_ids, ev.type_id
        )
        ev.title, ev.scope, ev.type_id = title, scope, type_id
        ev.start_at, ev.end_at, ev.all_day = start_at, end_at, all_day
        ev.location = (location or "").strip()[:200] or None
        ev.description = (description or "").strip() or None
        ev.updated_at = now_kst()
        _set_attendees(s, ev, ids)


def delete_event(actor, event_id: int) -> None:
    with session_scope() as s:
        ev = s.get(Event, event_id)
        if not ev:
            raise ServiceError("일정을 찾을 수 없습니다. (이미 삭제되었을 수 있습니다)")
        if not permissions.can_edit_event(actor, ev):
            raise PermissionDenied("이 일정을 삭제할 권한이 없습니다.")
        s.delete(ev)


# ---------------------------------------------------------------- 조회
def list_events(
    actor,
    range_start: datetime,
    range_end: datetime,
    *,
    scope: str | None = None,
    type_id: int | None = None,
    member_id: int | None = None,
) -> list[EventView]:
    """[range_start, range_end) 구간과 겹치는 일정. member_id 는 작성자 또는 참석자."""
    if actor is None:
        raise PermissionDenied()
    with session_scope() as s:
        q = (
            select(Event, EventType, User)
            .join(EventType, Event.type_id == EventType.id)
            .join(User, Event.author_id == User.id)
            .where(
                Event.start_at < range_end,
                or_(Event.end_at > range_start, Event.start_at >= range_start),
            )
            .order_by(Event.start_at, Event.id)
        )
        if scope in SCOPES:
            q = q.where(Event.scope == scope)
        if type_id:
            q = q.where(Event.type_id == type_id)
        if member_id:
            attending = select(EventAttendee.event_id).where(EventAttendee.user_id == member_id)
            q = q.where(or_(Event.author_id == member_id, Event.id.in_(attending)))
        rows = s.execute(q).all()
        ids = [ev.id for ev, _, _ in rows]
        att: dict[int, list[tuple[int, str]]] = {}
        if ids:
            for a, name in s.execute(
                select(EventAttendee, User.name)
                .join(User, EventAttendee.user_id == User.id)
                .where(EventAttendee.event_id.in_(ids))
                .order_by(User.name)
            ):
                att.setdefault(a.event_id, []).append((a.user_id, name))
        return [
            EventView(
                id=ev.id,
                title=ev.title,
                scope=ev.scope,
                type_id=et.id,
                type_name=et.name,
                color=et.color,
                start_at=ev.start_at,
                end_at=ev.end_at,
                all_day=ev.all_day,
                location=ev.location,
                description=ev.description,
                author_id=ev.author_id,
                author_name=u.name,
                attendee_ids=tuple(i for i, _ in att.get(ev.id, [])),
                attendee_names=tuple(n for _, n in att.get(ev.id, [])),
                can_edit=permissions.can_edit_event(actor, ev),
            )
            for ev, et, u in rows
        ]


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min)
    return start, start + timedelta(days=1)
