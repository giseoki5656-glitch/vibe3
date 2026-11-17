"""파일 저장소 추상화. resources 테이블에는 storage_key 만 저장한다.

백엔드:
- `db`    (기본): 파일 내용을 DB(stored_files)에 저장. 외부 DB 하나만 있으면 되고 Streamlit Cloud 에서 유지된다.
- `local` : 로컬 폴더. 개발용 (Cloud 에서는 재시작 시 사라짐).
외부 오브젝트 스토리지(S3 호환 등)는 같은 인터페이스로 추가할 수 있다.
"""
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from core.config import get_storage_config


def safe_filename(name: str) -> str:
    """경로 구분자/제어문자를 제거한 안전한 파일명."""
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "", name).strip(" .")
    return name or "file"


class Storage(ABC):
    @abstractmethod
    def save(self, data: bytes, filename: str) -> str: ...

    @abstractmethod
    def load(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, base_dir: str):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.base / key).resolve()
        if self.base not in path.parents:  # 경로 탈출 방지
            raise ValueError("잘못된 저장소 키입니다.")
        return path

    def save(self, data: bytes, filename: str) -> str:
        key = f"{uuid.uuid4().hex}_{safe_filename(filename)}"
        self._path(key).write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class DbStorage(Storage):
    def save(self, data: bytes, filename: str) -> str:
        from core.db import session_scope
        from core.models import StoredFile

        key = f"{uuid.uuid4().hex}_{safe_filename(filename)}"
        with session_scope() as s:
            s.add(StoredFile(key=key, data=data, size=len(data)))
        return key

    def load(self, key: str) -> bytes:
        from core.db import session_scope
        from core.models import StoredFile

        with session_scope() as s:
            row = s.get(StoredFile, key)
            if row is None:
                raise FileNotFoundError(key)
            return bytes(row.data)

    def delete(self, key: str) -> None:
        from core.db import session_scope
        from core.models import StoredFile

        with session_scope() as s:
            row = s.get(StoredFile, key)
            if row is not None:
                s.delete(row)


def get_storage() -> Storage:
    cfg = get_storage_config()
    if cfg["backend"] == "db":
        return DbStorage()
    if cfg["backend"] == "local":
        return LocalStorage(cfg["local_dir"])
    raise NotImplementedError(f"지원하지 않는 스토리지 백엔드: {cfg['backend']}")
