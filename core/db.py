"""DB 연결, 스키마 생성, 시드 데이터."""
from contextlib import contextmanager

import streamlit as st
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_admin_seed, get_database_url
from core.models import (
    ROLE_ADMIN,
    STATUS_ACTIVE,
    Base,
    EventType,
    PostCategory,
    User,
)
from core.security import hash_password
from core.timeutil import now_kst

DEFAULT_EVENT_TYPES = [
    ("회의", "#3B82F6"),
    ("출장", "#F59E0B"),
    ("행사", "#10B981"),
    ("휴가", "#EF4444"),
    ("기타", "#6B7280"),
]
# (이름, 관리자 전용 여부)
DEFAULT_POST_CATEGORIES = [("공지", True), ("자유", False), ("질문", False), ("정보공유", False)]


def make_engine(url: str) -> Engine:
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite 는 외래키(CASCADE)를 기본으로 끄고 있음
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def init_schema_and_seed(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as s:
        if not s.scalar(select(EventType.id).limit(1)):
            for i, (name, color) in enumerate(DEFAULT_EVENT_TYPES):
                s.add(EventType(name=name, color=color, is_default=True, sort_order=i))
        if not s.scalar(select(PostCategory.id).limit(1)):
            for i, (name, admin_only) in enumerate(DEFAULT_POST_CATEGORIES):
                s.add(PostCategory(name=name, admin_only=admin_only, sort_order=i))
        seed = get_admin_seed()
        if seed and not s.scalar(select(User.id).where(User.username == seed["username"])):
            s.add(
                User(
                    username=seed["username"],
                    name=seed["name"],
                    password_hash=hash_password(seed["password"]),
                    role=ROLE_ADMIN,
                    status=STATUS_ACTIVE,
                    approved_at=now_kst(),
                )
            )


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    engine = make_engine(get_database_url())
    init_schema_and_seed(engine)
    return engine


@contextmanager
def session_scope():
    """서비스 계층 전용. 정상 종료 시 commit, 예외 시 rollback."""
    session: Session = sessionmaker(get_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
