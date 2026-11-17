# 팀 포털 (Team Portal)

스케줄 · 게시판 · 자료를 제공하는 팀 내부 포털 (Streamlit). 자세한 요구사항은 [PRD.md](PRD.md) 참고.

## 로컬 실행 (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 시크릿 설정: 예시 파일을 복사해 관리자 비밀번호를 바꾼다
copy .streamlit\secrets.toml.example .streamlit\secrets.toml

streamlit run app.py
```

- DB 기본값은 `sqlite:///local.db` (파일 자동 생성). `DATABASE_URL` 환경변수 또는 `secrets.toml`의 `DATABASE_URL`로 PostgreSQL 등을 지정할 수 있다.
- 최초 실행 시 `secrets.toml`의 `[admin]` 값으로 관리자 계정이 생성된다.
- 가입 흐름: 가입 신청(pending) → 관리자가 `관리 > 가입 승인`에서 승인 → 로그인 가능.

## 테스트

```powershell
python -m pytest -q
```

## 구조

```
app.py            진입점 (로그인 가드 + 내비게이션)
pages/            화면 (홈/스케줄/게시판/자료/마이페이지/관리)
core/             auth, permissions, db, models, storage, config
services/         DB 접근 및 비즈니스 로직 (페이지에서 DB 직접 호출 금지)
tests/            pytest
```

## 배포 (Streamlit Community Cloud)

앱 서버의 파일시스템은 휘발성이므로 외부 PostgreSQL + 외부 오브젝트 스토리지를 사용하고,
접속 정보는 Cloud의 Secrets에 설정한다. (PRD 7장 참고)
