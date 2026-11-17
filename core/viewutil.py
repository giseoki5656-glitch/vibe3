"""화면 표시용 작은 도우미 (비즈니스 로직 없음)."""
from datetime import date

from core.models import SCOPE_TEAM

SCOPE_ICON = {"personal": "👤", "team": "👥"}
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 유형 색상(#RRGGBB)을 가장 가까운 색 이모지로 표시 (st.button 라벨에는 색을 칠할 수 없어서)
_EMOJI_RGB = {
    "🟥": (221, 46, 68), "🟧": (244, 144, 12), "🟨": (253, 203, 88), "🟩": (120, 177, 89),
    "🟦": (85, 172, 238), "🟪": (170, 142, 214), "🟫": (193, 105, 79), "⬛": (49, 55, 61), "⬜": (230, 231, 232),
}


def color_dot(hex_color: str) -> str:
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "⬜"
    return min(_EMOJI_RGB, key=lambda e: sum((c - t) ** 2 for c, t in zip((r, g, b), _EMOJI_RGB[e])))


def is_edited(created_at, updated_at) -> bool:
    """생성/수정 시각 기본값이 서로 다른 순간에 계산되므로 몇 초의 오차는 '수정됨'으로 보지 않는다."""
    return (updated_at - created_at).total_seconds() > 2


def day_label(d: date) -> str:
    return f"{d.year}-{d.month:02d}-{d.day:02d} ({WEEKDAYS[d.weekday()]})"


def event_time_text(ev, on: date | None = None) -> str:
    """일정 시간 표시. on 이 주어지면 그 날짜 기준(여러 날 일정 구분)."""
    if ev.all_day:
        return "종일"
    s, e = ev.start_at, ev.end_at
    if s.date() == e.date():
        return f"{s:%H:%M}~{e:%H:%M}"
    if on is not None:
        if on == s.date():
            return f"{s:%H:%M}~"
        if on == e.date():
            return f"~{e:%H:%M}"
        return "계속"
    return f"{s:%m/%d %H:%M} ~ {e:%m/%d %H:%M}"


def event_period_text(ev) -> str:
    s, e = ev.start_at, ev.end_at
    if ev.all_day:
        return f"{s:%Y-%m-%d}" if s.date() == e.date() else f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d} (종일)"
    if s.date() == e.date():
        return f"{s:%Y-%m-%d} {s:%H:%M} ~ {e:%H:%M}"
    return f"{s:%Y-%m-%d %H:%M} ~ {e:%Y-%m-%d %H:%M}"


def event_label(
    ev, *, on: date | None = None, max_title: int = 14, show_time: bool = True, dot: bool = True
) -> str:
    title = ev.title if len(ev.title) <= max_title else ev.title[: max_title - 1] + "…"
    t = f"{event_time_text(ev, on)} " if show_time else ""
    return f"{SCOPE_ICON.get(ev.scope, '')}{color_dot(ev.color) if dot else ''} {t}{title}".strip()


_FILE_ICONS = {
    "pdf": "📕", "doc": "📘", "docx": "📘", "hwp": "📘", "hwpx": "📘", "txt": "📄", "md": "📄",
    "xls": "📗", "xlsx": "📗", "csv": "📗", "ppt": "📙", "pptx": "📙",
    "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "gif": "🖼️", "zip": "🗜️",
}


def file_icon(file_name: str | None) -> str:
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    return _FILE_ICONS.get(ext, "📎")


def human_size(n: int | None) -> str:
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return ""


def is_team(scope: str) -> bool:
    return scope == SCOPE_TEAM
