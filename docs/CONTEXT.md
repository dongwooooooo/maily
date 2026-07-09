# Maily Current Context

정리일: 2026-07-09

이 문서는 `docs/INDEX.md`(처음 읽는 순서) 다음에 보는 **현재 상태 스냅샷 + 라우팅 표**다. 우선순위 스택의 단일 근거는 이 문서다 — `AGENTS.md`, `CLAUDE.md`는 여기를 참조만 한다.

## 현재 운영 기준

Maily는 여러 Gmail 계정의 중요한 메일을 선별해 브리핑하는 웹 서비스다. 제품 정의는 `PRODUCT.md`가 근거.

활성 source-of-truth 문서는 `docs/current/`에 둔다. `planning/`은 탐색 기획 보관 위치이며, 현재 기준으로 승격된 문서는 `docs/current/`를 본다.

## Source-of-Truth Stack

충돌이 있으면 아래 순서를 따른다.

1. `docs/current/product-wireframe-final.md`  
   제품 범위, 정보 구조, 핵심 화면 10종, 카드 문법, Gmail 신뢰 원칙.
2. `docs/current/product-features.md`  
   사용자 기능 설명, MVP 범위, 백엔드 우선 POC 범위.
3. `docs/current/technical-foundation.md`  
   개발 스택, 디렉토리 구조, 초기 세팅 기준.
4. `docs/areas/backend/module-boundaries.md`  
   백엔드 모듈 경계와 모듈 간 기능 연결.
5. `docs/areas/backend/db-schema.md`  
   백엔드 DB 테이블 필드/제약/열린 결정 사항.
6. `docs/goals/backend-implementation-plan.md`  
   백엔드 세부 구현 작업, POC gate, TDD 순서.
7. `docs/areas/backend/error-handling-and-logging.md`  
   백엔드 예외 계층, 에러 응답 계약, 구조화 로깅과 request context 규칙.
8. `DESIGN.md` (루트)  
   확정된 시각 방향, 색상·타이포·레이아웃·컴포넌트·인터랙션 원칙과 금지 패턴. 디자인 층 단일 근거.
9. `design/brand-color-final.md`  
   확정 색상, 상태 레이어, 접근성 기준.
10. `design/copy-principles.md`  
    한국어 UI 카피와 신뢰 문구.
11. `design/boards/v1/current/*.html` + `shared.css`  
    현재 하이파이 기준 목업 10장과 공용 스타일시트. `design/boards/v1/candidates/`·`legacy/`는 기각/과거 후보안이지 기준 아님.
12. `design/wireframes/*.svg`  
    동결된 로우파이 와이어프레임 11장(00 플로우맵 + 01~10). 구조 참조용이며 목업이 override한다 — 명시 요청 없이 수정하지 않는다.

## 현재 결정

제품 행동 규칙의 원본은 `PRODUCT.md`·`docs/current/product-wireframe-final.md`다. 아래는 프로젝트 상태·아키텍처 결정을 포함한 digest이며, 충돌 시 스펙 문서가 우선한다.

- 첫 화면은 전체 inbox가 아니라 오늘 브리핑이다.
- Gmail은 원본 시스템이며 Maily는 브리핑, 우선순위, 정리 보조 레이어다.
- 서비스 로그인 계정과 연결 Gmail 계정은 분리한다.
- 연결 Gmail 계정의 새 메일은 지속 동기화 대상으로 본다.
- 백엔드 우선 리스크는 Gmail Continuous Sync다.
- 메일 카드는 스캔과 선택만 담당한다.
- Gmail 변경 액션은 상세 패널 또는 정리 검토에서 처리한다.
- Gmail 변경이 발생하면 결과와 Undo 가능 여부를 보여준다.
- 사용자 이동 목적지는 기본 섹션이 아니라 Gmail `Maily/` 라벨과 동기화되는 라벨이다.
- AI 판단 이유는 기본으로 노출하지 않는다.

## 작업 라우팅

| 작업 | 먼저 읽을 문서 | 보조 문서 |
|---|---|---|
| 제품 범위 확인 | `docs/current/product-wireframe-final.md` | `docs/current/product-features.md` |
| 기능 목록 확인 | `docs/current/product-features.md` | `docs/areas/backend/module-boundaries.md` |
| 백엔드 모듈 설계 | `docs/areas/backend/module-boundaries.md` | `docs/goals/backend-implementation-plan.md` |
| 백엔드 DB 모델링 | `docs/areas/backend/db-schema.md` | `docs/areas/backend/module-boundaries.md` |
| 백엔드 구현 계획 실행 | `docs/goals/backend-implementation-plan.md` | `development/backend/README.md` |
| 백엔드 예외/로깅 구현 | `docs/areas/backend/error-handling-and-logging.md` | `docs/areas/backend/module-boundaries.md` |
| 프론트엔드 구현 | `docs/current/product-wireframe-final.md` | `docs/current/technical-foundation.md`, `docs/areas/frontend/frontend-status.md`, `development/frontend/README.md` |
| 디자인/카피 결정 | `DESIGN.md` (루트) | `design/brand-color-final.md`, `design/copy-principles.md` |
| 와이어프레임 확인 | `design/wireframes/*.svg` | `docs/current/product-wireframe-final.md` |
| 인프라/로컬 실행 | `docs/current/technical-foundation.md` | `development/infra/README.md` |
