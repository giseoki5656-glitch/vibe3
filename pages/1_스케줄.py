import calendar
import html
from datetime import date, datetime, time, timedelta

import streamlit as st

from core.auth import require_login
from core.errors import ServiceError
from core.models import SCOPE_PERSONAL, SCOPE_TEAM
from core.timeutil import now_kst
from core.viewutil import (
    SCOPE_ICON,
    WEEKDAYS,
    color_dot,
    day_label,
    event_label,
    event_period_text,
    event_time_text,
)
from services import events as es
from services import users as us
from ui.components import empty_state, legend_chips, page_header
from ui.theme import card_rule, chip_rule, inject_css

user = require_login()
ss = st.session_state
TODAY = now_kst().date()
VIEWS = ["일별", "주별", "월별"]
SCOPE_FILTERS = {"전체": None, "개인": SCOPE_PERSONAL, "팀": SCOPE_TEAM}

ss.setdefault("sched_view", "월별")
ss.setdefault("sched_date", TODAY)
ss.setdefault("sched_f_scope", "전체")

css_rules: list[str] = []  # 이번 렌더링에서 쓰는 일정 칩/카드 색 규칙


def _view() -> str:
    return ss.get("sched_view") or "월별"  # segmented_control 은 선택 해제 시 None


# ------------------------------------------------------------------ 이동 콜백
def _shift(direction: int) -> None:
    view, d = _view(), ss.sched_date
    if view == "일별":
        d += timedelta(days=direction)
    elif view == "주별":
        d += timedelta(weeks=direction)
    else:
        m = d.month - 1 + direction
        d = date(d.year + m // 12, m % 12 + 1, 1)
    ss.sched_date = d


def _today() -> None:
    ss.sched_date = TODAY


def _open_day(day: date) -> None:
    ss.sched_date, ss.sched_view = day, "일별"


# ------------------------------------------------------------------ 일정 대화상자
def _details(ev: es.EventView) -> None:
    st.markdown(f"### {SCOPE_ICON[ev.scope]} {ev.title}")
    st.write(f"{color_dot(ev.color)} **{ev.type_name}** · {es.SCOPE_LABELS[ev.scope]} 일정")
    st.write(f"🕒 {event_period_text(ev)}")
    st.write(f"✍️ 작성자: {ev.author_name}")
    if ev.location:
        st.write(f"📍 {ev.location}")
    if ev.attendee_names:
        st.write("👥 참석자: " + ", ".join(ev.attendee_names))
    if ev.description:
        st.markdown(ev.description)
    st.caption(
        "팀 일정은 작성자와 관리자만 수정할 수 있습니다."
        if ev.scope == SCOPE_TEAM
        else "개인 일정은 작성자만 수정할 수 있습니다."
    )


@st.dialog("일정", width="large")
def event_dialog(ev: es.EventView | None, default_day: date) -> None:
    if ev is not None and not ev.can_edit:
        _details(ev)
        return

    is_new = ev is None
    k = f"evf_{'new' if is_new else ev.id}_"
    types = [t for t in es.list_event_types(active_only=False) if t.is_active or (ev and t.id == ev.type_id)]
    members = us.list_active_users()
    member_names = dict(members)

    title = st.text_input("제목", value="" if is_new else ev.title, max_chars=200, key=k + "title")
    c1, c2 = st.columns(2)
    scope = c1.radio(
        "범위",
        [SCOPE_PERSONAL, SCOPE_TEAM],
        index=0 if is_new or ev.scope == SCOPE_PERSONAL else 1,
        format_func=lambda s: f"{SCOPE_ICON[s]} {es.SCOPE_LABELS[s]}",
        horizontal=True,
        key=k + "scope",
    )
    type_ids = [t.id for t in types]
    type_id = c2.selectbox(
        "유형",
        type_ids,
        index=0 if is_new else type_ids.index(ev.type_id),
        format_func=lambda i: next(f"{color_dot(t.color)} {t.name}" for t in types if t.id == i),
        key=k + "type",
    )
    all_day = st.checkbox("종일", value=False if is_new else ev.all_day, key=k + "allday")

    d0 = default_day if is_new else ev.start_at.date()
    d1 = default_day if is_new else ev.end_at.date()
    t0 = time(9, 0) if is_new else ev.start_at.time()
    t1 = time(10, 0) if is_new else ev.end_at.time()
    if all_day:
        col_a, col_b = st.columns(2)
        start_d = col_a.date_input("시작일", value=d0, key=k + "sd")
        end_d = col_b.date_input("종료일", value=d1, key=k + "ed")
        start_t, end_t = time(0, 0), time(23, 59)
    else:
        col_a, col_b, col_c, col_d = st.columns(4)
        start_d = col_a.date_input("시작일", value=d0, key=k + "sd")
        start_t = col_b.time_input("시작 시간", value=t0, key=k + "st", step=300)
        end_d = col_c.date_input("종료일", value=d1, key=k + "ed")
        end_t = col_d.time_input("종료 시간", value=t1, key=k + "et", step=300)

    location = st.text_input("장소 (선택)", value="" if is_new else ev.location or "", max_chars=200, key=k + "loc")
    description = st.text_area("설명/메모 (선택)", value="" if is_new else ev.description or "", key=k + "desc")
    attendee_ids: list[int] = []
    if scope == SCOPE_TEAM:
        default_att = [] if is_new else [i for i in ev.attendee_ids if i in member_names]
        attendee_ids = st.multiselect(
            "참석자 (선택)",
            list(member_names),
            default=default_att,
            format_func=lambda i: member_names[i],
            key=k + "att",
        )

    payload = dict(
        title=title,
        scope=scope,
        type_id=type_id,
        start_at=datetime.combine(start_d, start_t),
        end_at=datetime.combine(end_d, end_t),
        all_day=all_day,
        location=location,
        description=description,
        attendee_ids=attendee_ids,
    )

    confirm_key = k + "confirm_delete"
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("저장", type="primary", key=k + "save", use_container_width=True):
        try:
            with st.spinner("저장 중..."):
                if is_new:
                    es.create_event(user, **payload)
                else:
                    es.update_event(user, ev.id, **payload)
        except ServiceError as e:
            st.error(str(e))
        else:
            ss["sched_flash"] = "일정을 저장했습니다."
            st.rerun()
    if not is_new and b2.button("삭제", key=k + "del", use_container_width=True):
        ss[confirm_key] = True
    if not is_new and ss.get(confirm_key):
        st.warning("이 일정을 삭제할까요? 되돌릴 수 없습니다.")
        y, n, _ = st.columns([1, 1, 3])
        if y.button("삭제 확인", type="primary", key=k + "del_yes", use_container_width=True):
            try:
                es.delete_event(user, ev.id)
            except ServiceError as e:
                st.error(str(e))
                ss[confirm_key] = False
            else:
                ss["sched_flash"] = "일정을 삭제했습니다."
                ss.pop(confirm_key, None)
                st.rerun()
        if n.button("취소", key=k + "del_no", use_container_width=True):
            ss[confirm_key] = False
            st.rerun(scope="fragment")


# ------------------------------------------------------------------ 보기 렌더링
def _overlaps(ev: es.EventView, day: date) -> bool:
    ds = datetime.combine(day, time.min)
    de = ds + timedelta(days=1)
    return ev.start_at < de and (ev.end_at > ds or ev.start_at >= ds)


def _event_button(ev: es.EventView, day: date, view: str, **label_kw) -> None:
    key = f"evb_{view}_{ev.id}_{day.isoformat()}"
    css_rules.append(chip_rule(key, ev.color, dashed=ev.scope == SCOPE_PERSONAL))
    if st.button(
        event_label(ev, on=day, dot=False, **label_kw),
        key=key,
        help=f"{ev.title} · {ev.type_name} · {ev.author_name}",
        type="tertiary",
        use_container_width=True,
    ):
        event_dialog(ev, day)


def _day_title(day: date, *, with_weekday=True) -> str:
    color = ":red" if day.weekday() == 6 else ":blue" if day.weekday() == 5 else ""
    text = f"{day.day}" if not with_weekday else f"{day.month}/{day.day} {WEEKDAYS[day.weekday()]}"
    return f"{color}[{text}]" if color else text


def render_month(d: date, events: list[es.EventView]) -> None:
    weeks = calendar.Calendar(0).monthdatescalendar(d.year, d.month)
    with st.container(key="month_grid"):
        for col, name in zip(st.columns(7), WEEKDAYS):
            tone = "color:#E03131" if name == "일" else "color:#3B5BDB" if name == "토" else ""
            col.markdown(f"<div class='center' style='font-weight:600;{tone}'>{name}</div>", unsafe_allow_html=True)
        for week in weeks:
            for day, col in zip(week, st.columns(7)):
                with col.container(border=True):
                    label = _day_title(day, with_weekday=False)
                    if day.month != d.month:
                        label = f":gray[{day.day}]"
                    st.button(
                        label,
                        key=f"mday_{day.isoformat()}",
                        type="primary" if day == TODAY else "tertiary",
                        on_click=_open_day,
                        args=(day,),
                        help="이 날짜의 일별 보기",
                    )
                    todays = [e for e in events if _overlaps(e, day)]
                    for ev in todays[:3]:
                        _event_button(ev, day, "m", max_title=10, show_time=False)
                    if len(todays) > 3:
                        st.button(
                            f"+{len(todays) - 3}개 더보기",
                            key=f"mmore_{day.isoformat()}",
                            type="tertiary",
                            on_click=_open_day,
                            args=(day,),
                        )


def render_week(d: date, events: list[es.EventView]) -> None:
    monday = d - timedelta(days=d.weekday())
    with st.container(key="week_grid"):
        for i, col in enumerate(st.columns(7)):
            day = monday + timedelta(days=i)
            with col.container(border=True):
                st.button(
                    _day_title(day),
                    key=f"wday_{day.isoformat()}",
                    type="primary" if day == TODAY else "tertiary",
                    on_click=_open_day,
                    args=(day,),
                    help="이 날짜의 일별 보기",
                )
                todays = [e for e in events if _overlaps(e, day)]
                if not todays:
                    st.caption("일정 없음")
                for ev in todays:
                    _event_button(ev, day, "w", max_title=12)


def render_day(d: date, events: list[es.EventView]) -> None:
    st.subheader(day_label(d) + (" · 오늘" if d == TODAY else ""))
    todays = [e for e in events if _overlaps(e, d)]
    if not todays:
        empty_state("이 날은 일정이 없습니다.", "🗓️")
    for ev in todays:
        key = f"dayev_{ev.id}"
        css_rules.append(card_rule(key, ev.color))
        with st.container(border=True, key=key):
            left, right = st.columns([5, 1], vertical_alignment="center")
            left.markdown(
                f"{SCOPE_ICON[ev.scope]} **{ev.title}**  \n"
                f":gray[{ev.type_name} · {event_time_text(ev, d)} · 작성자 {ev.author_name}]"
                + (f"  \n📍 {ev.location}" if ev.location else "")
                + (f"  \n👥 {', '.join(ev.attendee_names)}" if ev.attendee_names else "")
            )
            if ev.description:
                left.caption(ev.description)
            if right.button(
                "수정" if ev.can_edit else "상세",
                key=f"evd_{ev.id}",
                type="secondary" if ev.can_edit else "tertiary",
                use_container_width=True,
            ):
                event_dialog(ev, d)


# ------------------------------------------------------------------ 화면
if msg := ss.pop("sched_flash", None):
    st.toast(msg, icon="✅")

page_header("스케줄", "일정을 클릭하면 상세 보기, 내 일정이면 수정할 수 있습니다.")

# 툴바: 이동 | 제목 | 보기 전환 | 등록
t_nav, t_title, t_view, t_add = st.columns([3.6, 2.4, 2.4, 1.6], vertical_alignment="center")
with t_nav, st.container(key="nav_row"):
    n1, n2, n3, n4 = st.columns([1, 1.7, 1, 1.2])
    n1.button("◀", on_click=_shift, args=(-1,), help="이전", use_container_width=True)
    n2.button("오늘", on_click=_today, use_container_width=True)
    n3.button("▶", on_click=_shift, args=(1,), help="다음", use_container_width=True)
    with n4.popover("📅", help="날짜 선택", use_container_width=True):
        st.date_input("날짜 선택", key="sched_date")
t_view.segmented_control("보기", VIEWS, key="sched_view", label_visibility="collapsed")
if t_add.button("＋ 일정 등록", type="primary", use_container_width=True):
    event_dialog(None, ss.sched_date)

view, d = _view(), ss.sched_date

# 조회 구간 + 제목
if view == "일별":
    r0, r1, title = d, d + timedelta(days=1), f"{d.month}월 {d.day}일"
elif view == "주별":
    monday = d - timedelta(days=d.weekday())
    r0, r1 = monday, monday + timedelta(days=7)
    title = f"{monday.month}/{monday.day} ~ {(monday + timedelta(days=6)).month}/{(monday + timedelta(days=6)).day}"
else:
    weeks = calendar.Calendar(0).monthdatescalendar(d.year, d.month)
    r0, r1 = weeks[0][0], weeks[-1][-1] + timedelta(days=1)
    title = f"{d.year}년 {d.month}월"
t_title.markdown(f"<div style='font-size:1.35rem;font-weight:700'>{html.escape(title)}</div>", unsafe_allow_html=True)

# 필터
types_all = es.list_event_types(active_only=False)
members = us.list_active_users()
f1, f2, f3 = st.columns([2, 2, 2])
scope_f = f1.segmented_control("범위", list(SCOPE_FILTERS), key="sched_f_scope", label_visibility="collapsed") or "전체"
type_f = f2.selectbox(
    "유형", [0] + [t.id for t in types_all], key="sched_f_type", label_visibility="collapsed",
    format_func=lambda i: "전체 유형" if i == 0 else next(t.name for t in types_all if t.id == i),
)
member_f = f3.selectbox(
    "팀원", [0] + [i for i, _ in members], key="sched_f_member", label_visibility="collapsed",
    format_func=lambda i: "전체 팀원" if i == 0 else dict(members)[i],
)

events = es.list_events(
    user,
    datetime.combine(r0, time.min),
    datetime.combine(r1, time.min),
    scope=SCOPE_FILTERS[scope_f],
    type_id=type_f or None,
    member_id=member_f or None,
)

legend_chips([(t.name, t.color) for t in types_all if t.is_active])
st.caption("👤 개인(점선) · 👥 팀(실선)")

if view == "월별":
    render_month(d, events)
elif view == "주별":
    render_week(d, events)
else:
    render_day(d, events)

inject_css(css_rules)
