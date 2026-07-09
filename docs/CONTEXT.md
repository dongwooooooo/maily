# Maily Current Context

정리일: 2026-07-08

## 현재 운영 기준

Maily는 여러 Gmail 계정의 중요한 메일을 선별해 브리핑하는 웹 서비스다. Gmail을 대체하지 않는다. 원문 읽기, 답장, 작성, 발송은 Gmail에서 처리한다.

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
5. `docs/goals/backend-implementation-plan.md`  
   백엔드 세부 구현 작업, POC gate, TDD 순서.
6. `design/brand-color-final.md`  
   확정 색상, 상태 레이어, 접근성 기준.
7. `design/copy-principles.md`  
   한국어 UI 카피와 신뢰 문구.
8. `DESIGN.md` (루트)  
   확정된 시각 방향, 색상·타이포·레이아웃·컴포넌트·인터랙션 원칙과 금지 패턴.
9. `design/wireframes/*.svg`  
   동결된 로우파이 와이어프레임. 명시 요청 없이 수정하지 않는다.

## 현재 결정

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

## 문서 작성 규칙

- 활성 기준 문서는 `docs/current/`에 둔다.
- 영역별 설계 문서는 `docs/areas/<area>/`에 둔다.
- 실행 가능한 구현 계획과 goal 계약은 `docs/goals/`에 둔다.
- 운영 절차는 `docs/runbooks/`에 둔다.
- 디자인 결정, 카피, 와이어프레임, 보드는 `design/`에 둔다.
- 실제 코드와 영역별 README는 `development/`에 둔다.
- 탐색 기획은 `planning/`에 둘 수 있지만, 구현 기준으로 채택되면 `docs/current/`나 `docs/areas/`로 승격한다.

## 작업 라우팅

- 기능을 뽑거나 범위를 확인할 때: `docs/current/product-features.md`
- 화면/카드/상세/정보 구조를 확인할 때: `docs/current/product-wireframe-final.md`
- 백엔드 모듈 경계를 확인할 때: `docs/areas/backend/module-boundaries.md`
- 백엔드 구현을 실행할 때: `docs/goals/backend-implementation-plan.md`
- 기술 스택이나 디렉토리 기준을 확인할 때: `docs/current/technical-foundation.md`
- 프론트 UI 세부 구현을 확인할 때: `development/frontend/README.md`, `design/*`
