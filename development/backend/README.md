# Maily Backend

백엔드 영역이다. 현재는 FastAPI 최소 앱과 스택 버전만 고정했다.

계획 문서는 역할별로 나눈다.

- `../../docs/current/product-features.md`: 사용자 기능 설명과 제품 완료 판정
- `../../docs/areas/backend/module-boundaries.md`: 백엔드 모듈 바운더리와 모듈 간 연결
- `../../docs/goals/backend-implementation-plan.md`: 세부 구현 작업, POC gate, TDD 순서

## 스택

- Python 3.14.x
- FastAPI 0.139.0
- PostgreSQL 18.x
- Redis 8.8.x
- JWT: PyJWT 2.13.0
- OAuth2/Gmail: Authlib 1.7.2 + google-auth-oauthlib 1.4.0
- Docker

## 책임

- Google 로그인과 서비스 워크스페이스
- 연결 Gmail 계정 OAuth token 관리
- Gmail 메타데이터 수집, 읽음 처리, 라벨 적용, 아카이브
- 브리핑/정리 worker
- LLM 요약 호출
- 활동 로그와 Undo
- 브라우저 알림 payload

## 로컬 실행

Python 3.14 런타임 설치 후 실행한다.

```bash
cd development/backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
uvicorn app.main:app --reload
```
