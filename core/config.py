"""설정/시크릿 접근. 우선순위: 환경변수 > st.secrets > 기본값."""
import os

import streamlit as st

DEFAULT_DB_URL = "sqlite:///local.db"


def _secret(path: tuple[str, ...], default=None):
    try:
        node = st.secrets
        for key in path:
            node = node[key]
        return node
    except Exception:  # secrets.toml 이 없거나 키가 없는 경우
        return default


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL") or _secret(("DATABASE_URL",)) or DEFAULT_DB_URL


def get_admin_seed() -> dict | None:
    username = os.environ.get("ADMIN_USERNAME") or _secret(("admin", "username"))
    password = os.environ.get("ADMIN_PASSWORD") or _secret(("admin", "password"))
    if not username or not password:
        return None
    name = os.environ.get("ADMIN_NAME") or _secret(("admin", "name"), "관리자")
    return {"username": str(username), "password": str(password), "name": str(name)}


def get_storage_config() -> dict:
    return {
        "backend": os.environ.get("STORAGE_BACKEND") or _secret(("storage", "backend"), "db"),
        "local_dir": os.environ.get("STORAGE_LOCAL_DIR") or _secret(("storage", "local_dir"), "local_uploads"),
    }
