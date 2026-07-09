# Maily Docs Index

이 문서는 AI 작업자가 현재 저장소에서 어떤 문서를 먼저 읽어야 하는지 정하는 라우터다.

## 먼저 읽을 문서

1. `AGENTS.md`  
   저장소 작업 규칙, 소스 우선순위, 제품 제약, 작성 위치 규칙.
2. `docs/CONTEXT.md`  
   현재 활성 문서 구조와 작업별 진입점.
3. `docs/current/product-wireframe-final.md`  
   제품 범위, 정보 구조, 핵심 화면, 카드 문법, Gmail 신뢰 원칙.
4. `docs/current/product-features.md`  
   사용자 기능 설명, MVP 범위, 백엔드 우선 POC 범위.
5. `docs/current/technical-foundation.md`  
   개발 스택, 디렉토리 구조, 실행 기준.

## 작업별 진입점

| 작업 | 먼저 읽을 문서 | 보조 문서 |
|---|---|---|
| 제품 범위 확인 | `docs/current/product-wireframe-final.md` | `docs/current/product-features.md` |
| 기능 목록 확인 | `docs/current/product-features.md` | `docs/areas/backend/module-boundaries.md` |
| 백엔드 모듈 설계 | `docs/areas/backend/module-boundaries.md` | `docs/goals/backend-implementation-plan.md` |
| 백엔드 구현 계획 실행 | `docs/goals/backend-implementation-plan.md` | `development/backend/README.md` |
| 프론트엔드 구현 | `docs/current/product-wireframe-final.md` | `docs/current/technical-foundation.md`, `docs/current/frontend-status.md`, `development/frontend/README.md` |
| 디자인/카피 결정 | `DESIGN.md` (루트) | `design/brand-color-final.md`, `design/copy-principles.md` |
| 와이어프레임 확인 | `design/wireframes/*.svg` | `docs/current/product-wireframe-final.md` |
| 인프라/로컬 실행 | `docs/current/technical-foundation.md` | `development/infra/README.md` |

## 디렉토리 의미

| 경로 | 역할 |
|---|---|
| `docs/current/` | 현재 활성 source-of-truth 계약 |
| `docs/areas/` | 영역별 설계와 모듈 바운더리 |
| `docs/goals/` | 실행 가능한 구현 계획과 goal 계약 |
| `docs/runbooks/` | 운영 절차와 검증 명령 |
| `design/` | 디자인 결정, 카피 원칙, 와이어프레임, 비교 보드 |
| `development/` | 실제 애플리케이션 코드와 영역별 README |
| `planning/` | 탐색 기획 보관. 활성 기준 문서는 `docs/current/`로 승격한다 |
| `archive/` | 현재 프로젝트 기준에서 벗어난 보관 자료 |

## 오래된 경로 규칙

활성 기준 문서는 `planning/`이나 `development/` 루트에 새로 만들지 않는다.

- 제품/기능/기술 기준: `docs/current/`
- 백엔드/프론트엔드/인프라 영역 계약: `docs/areas/<area>/`
- 구현 실행 계획: `docs/goals/`
- 코드 실행 안내: 각 `development/<area>/README.md`
