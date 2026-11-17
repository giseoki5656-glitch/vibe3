"""디자인 토큰과 전역 CSS. 색상은 이 파일(및 .streamlit/config.toml의 [theme])에서만 정의한다.

Streamlit 내부 클래스명에는 의존하지 않고, 안정적인 data-testid 와 st.container(key=...) 가 만드는
`st-key-<key>` 클래스만 사용한다.
"""
import re

import streamlit as st

PRIMARY = "#3B5BDB"  # config.toml 의 primaryColor 와 같은 값
MUTED = "#6B7280"
BORDER = "#E3E7EF"
SURFACE = "#F3F5FB"
NOTICE = "#E03131"

_CSS = f"""
.block-container {{ max-width: 1180px; padding-top: 2.2rem; }}
h1 {{ font-size: 1.85rem !important; letter-spacing: -0.02em; margin-bottom: 0.1rem; }}
h2, h3 {{ letter-spacing: -0.01em; }}

/* 목록형 버튼: 왼쪽 정렬 + 한 줄 말줄임 */
.st-key-month_grid button, .st-key-week_grid button, .st-key-board_list button {{
    justify-content: flex-start; text-align: left; width: 100%;
}}
.st-key-month_grid button p, .st-key-board_list button p {{
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left;
}}
.st-key-week_grid button p {{ white-space: normal; text-align: left; line-height: 1.3; }}
.st-key-month_grid button > div, .st-key-week_grid button > div, .st-key-board_list button > div {{
    justify-content: flex-start; width: 100%;
}}
.st-key-board_list button {{ padding-left: 0; min-height: 1.8rem; }}
.st-key-board_list [data-testid="stVerticalBlock"] {{ gap: 0.2rem; }}
.st-key-board_list button:hover {{ color: {PRIMARY}; }}

/* 월간 달력 셀 */
.st-key-month_grid [data-testid="stVerticalBlockBorderWrapper"] {{ min-height: 118px; padding: 0.35rem; }}
.st-key-month_grid [data-testid="stVerticalBlock"] {{ gap: 0.2rem; }}
.st-key-week_grid [data-testid="stVerticalBlock"] {{ gap: 0.25rem; }}

/* 일정 칩: 유형 색은 페이지에서 키별 규칙으로 덧붙인다 */
.evchip button {{ border-radius: 5px; min-height: 1.7rem; padding: 0.1rem 0.45rem; }}

.legend-chip {{
    display: inline-block; padding: 0.1rem 0.55rem; margin: 0 0.3rem 0.2rem 0;
    border-radius: 999px; font-size: 0.8rem; border: 1px solid transparent;
}}
.st-key-cookie_sync {{ position: absolute; width: 0; height: 0; overflow: hidden; }}
.muted {{ color: {MUTED}; }}
.center {{ text-align: center; }}

@media (max-width: 640px) {{
    .block-container {{ padding: 1.2rem 0.7rem 3rem; }}
    h1 {{ font-size: 1.5rem !important; }}
    /* 이동 버튼 줄도 모바일에서 한 줄 유지 */
    .st-key-nav_row [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: 0.3rem !important; }}
    .st-key-nav_row [data-testid="stColumn"] {{ min-width: 0 !important; flex: 1 1 0 !important; width: auto !important; }}
    /* 월간 달력은 모바일에서도 7열을 유지 */
    .st-key-month_grid [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: 0.15rem !important; }}
    .st-key-month_grid [data-testid="stColumn"] {{ min-width: 0 !important; flex: 1 1 0 !important; width: auto !important; }}
    .st-key-month_grid [data-testid="stVerticalBlockBorderWrapper"] {{ min-height: 74px; padding: 0.15rem; }}
    .st-key-month_grid button {{ padding: 0.05rem 0.15rem; min-height: 1.4rem; }}
    .st-key-month_grid button p {{ font-size: 0.66rem !important; }}
}}
"""

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def inject_global_css() -> None:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def chip_rule(key: str, color: str, *, dashed: bool = False) -> str:
    """키가 `key` 인 버튼/컨테이너에 유형 색(왼쪽 띠 + 옅은 배경)을 입히는 CSS 규칙."""
    if not _SAFE_KEY.match(key) or not _SAFE_COLOR.match(color):
        return ""
    style = "dashed" if dashed else "solid"
    return (
        f".st-key-{key} button {{ background: {color}1F; border-left: 3px {style} {color}; }}"
        f".st-key-{key} button:hover {{ background: {color}33; }}"
    )


def card_rule(key: str, color: str) -> str:
    """st.container(border=True, key=key) 카드의 왼쪽 띠 색."""
    if not _SAFE_KEY.match(key) or not _SAFE_COLOR.match(color):
        return ""
    return f".st-key-{key} {{ border-left: 4px solid {color}; border-radius: 0.6rem; }}"


def inject_css(rules: list[str]) -> None:
    css = "".join(r for r in rules if r)
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
