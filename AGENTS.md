# Maily 작업 지침

## 저장소 성격

이 저장소는 AI 메일 비서 Maily의 기획, 디자인, 개발을 함께 관리한다.

제품 정의는 `PRODUCT.md`가 근거. 요약: 여러 Gmail 계정의 중요한 메일을 선별해 브리핑하고 정리하는 서비스. Gmail을 대체하지 않는다 — 원문 읽기, 답장, 작성, 발송은 Gmail에서 처리한다.

## 기준 문서 우선순위

우선순위 스택의 단일 근거는 `docs/CONTEXT.md`(Source-of-Truth Stack)다. 충돌 시 그 순서를 따른다.

## 문서·코드 배치

새 작업 시작 전 `docs/INDEX.md`(읽는 순서)와 `docs/CONTEXT.md`(현재 기준)를 먼저 확인한다. 배치 규칙의 단일 근거는 이 섹션이다.

```text
docs/           AI 작업자가 먼저 읽는 활성 문서
  current/      현재 제품·기능·기술 source-of-truth
  areas/<area>/ 영역별 설계와 모듈 경계 (backend, frontend)
  goals/        실행 가능한 구현 계획, POC/TDD 계약
  runbooks/     운영 절차, 검증 명령, 장애 대응
planning/       탐색 기획 보관 (채택되면 docs/current 또는 docs/areas로 승격)
design/         디자인 결정, 색상, 카피, 목업 보드
development/     실제 코드와 영역별 README (frontend, backend, infra)
archive/        보관 자료
```

활성 기준 문서는 `planning/`이나 `development/` 루트에 새로 만들지 않는다.

## 개발 명령

프론트엔드 명령은 pnpm workspace 기준으로 실행한다.

```bash
corepack prepare pnpm@11.10.0 --activate
pnpm install
pnpm frontend:dev
pnpm frontend:lint
pnpm frontend:build
```

## 프론트엔드 규칙

- 현재 프론트엔드는 Next.js 16 + React 19 + TypeScript + pnpm 기준이다.
- Vite는 메인 앱 프레임워크가 아니라 UI 샌드박스/프로토타입 보조로만 둔다.
- 제품 코드는 `development/frontend/src/features/` 아래에 기능 단위로 둔다.
- 범용 UI는 `development/frontend/src/shared/` 아래에 둔다.
- 소스 경로 import는 `@/*` alias를 사용한다.
- 색상, 간격, 폰트, 반경, 상태 레이어는 `development/frontend/src/styles/tokens.css`를 기준으로 한다.
- 컴포넌트 안에 raw hex 색상을 직접 넣지 않는다.
- 일반 UI 아이콘은 `lucide-react`를 사용한다.
- UI 문구는 한국어를 기본으로 한다. Gmail, Inbox, Label처럼 제품상 필요한 용어만 영어를 유지한다.

## 제품 제약 근거

제품 화면·카드 문법·Gmail 신뢰 규칙 같은 제품 제약은 프론트·백엔드 공통으로 스펙 문서가 근거다. AGENTS.md에 중복 서술하지 않는다.

- 화면·카드 문법·정보 구조·Gmail 신뢰 원칙: `docs/current/product-wireframe-final.md`
- 제품 원칙·피해야 할 방향: `PRODUCT.md`
- 시각·컴포넌트 금지 패턴: `DESIGN.md`

작업 중 항상 지키는 authoring 규칙만 여기 둔다.

- 확정 카피가 없으면 즉흥 작성하지 말고 `[미확정: 필요한 카피 설명]` placeholder를 둔다.
