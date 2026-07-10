# Maily

여러 Gmail 계정의 중요 메일을 선별해 브리핑하는 웹 서비스. Gmail 대체가 아니라 그 위의 브리핑·우선순위·정리 레이어. 상세 제품 정의는 `PRODUCT.md`.

## 구조

| 경로 | 내용 |
|---|---|
| `AGENTS.md` | Codex 작업 규칙, 개발 명령, 문서 경로 규칙 (소스 우선순위는 `docs/CONTEXT.md`, 제품 제약은 스펙 문서) |
| `docs/INDEX.md` | AI 작업자용 문서 라우터 |
| `docs/CONTEXT.md` | 현재 source-of-truth 스택과 작업별 진입점 (단일 근거) |
| `docs/current/` | 제품, 기능, 기술 기준 |
| `docs/areas/` | 영역별 설계와 모듈 바운더리 (backend, frontend) |
| `docs/goals/` | 실행 가능한 구현 계획과 POC/TDD 계약 |
| `planning/` | 탐색 기획 보관 |
| `design/` | 디자인 원칙, 결정 로그, 카피 원칙 |
| `design/boards/v1/current/` | 확정 하이파이 목업 (결정 근거) |
| `design/boards/v1/candidates/`, `legacy/` | 기각·과거 후보안 |
| `design/wireframes/` | 로우파이 와이어프레임 SVG 11장 (동결) |
| `development/frontend/` | 프론트엔드 (Next.js + React 19 + TypeScript) |
| `development/backend/` | 백엔드 모듈 경계, 구현 계획, API/worker 예정 영역 |
| `development/infra/` | 인프라 예정 영역 |
| `archive/` | 보관 문서 |

## 개발

```bash
corepack prepare pnpm@11.10.0 --activate
pnpm install
pnpm frontend:dev
```

## 상세

- 스택·버전 상세: `docs/current/technical-foundation.md` (프론트 Next.js 16 + React 19, 백엔드 Python 3.14 + FastAPI + PostgreSQL + Redis).
- 구조: `development/frontend/src/features/*` 기준 feature-first.

문서 진입점은 `docs/INDEX.md`, 현재 기준은 `docs/CONTEXT.md`.
