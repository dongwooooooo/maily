# Maily 작업 지침

## 저장소 성격

이 저장소는 AI 메일 비서 Maily의 기획, 디자인, 개발을 함께 관리한다.

Maily는 여러 Gmail 계정의 중요한 메일을 선별해 브리핑하고 정리하는 서비스다. Gmail을 대체하지 않는다. 원문 읽기, 답장, 작성, 발송은 Gmail에서 처리한다.

## 기준 문서 우선순위

충돌이 있으면 아래 순서를 따른다.

1. `docs/current/product-wireframe-final.md` - 제품 범위, 정보 구조, 핵심 화면 10종, 카드 문법, Gmail 신뢰 원칙.
2. `docs/current/product-features.md` - 기획 문서에서 추출한 기능 목록과 MVP 범위.
3. `docs/current/technical-foundation.md` - 개발 스택, 디렉토리 구조, 초기 세팅 기준.
4. `docs/areas/backend/module-boundaries.md` - 백엔드 모듈 경계와 모듈 간 기능 연결.
5. `docs/goals/backend-implementation-plan.md` - 백엔드 세부 구현 작업, POC gate, TDD 순서.
6. `design/brand-color-final.md` - 확정 색상, 상태 레이어, 접근성 기준.
7. `design/copy-principles.md` - 한국어 UI 카피와 신뢰 문구.
8. `DESIGN.md` (루트) - 확정된 시각 방향, 색상·타이포·레이아웃·컴포넌트·인터랙션 원칙과 금지 패턴.
9. `design/wireframes/*.svg` - 동결된 로우파이 와이어프레임. 명시 요청 없이 수정하지 않는다.

## AI 문서 경로 규칙

새 작업을 시작할 때는 `docs/INDEX.md`와 `docs/CONTEXT.md`를 먼저 확인한다.

활성 기준 문서는 아래 위치에 둔다.

- `docs/current/` - 현재 제품, 기능, 기술 source-of-truth.
- `docs/areas/<area>/` - 프론트엔드, 백엔드, 인프라 같은 영역별 설계와 모듈 경계.
- `docs/goals/` - 실행 가능한 구현 계획, POC/TDD 계획, goal-runner 계약.
- `docs/runbooks/` - 운영 절차, 검증 명령, 장애 대응.

`planning/`은 탐색 기획 보관용이다. 구현 기준으로 채택된 문서는 `docs/current/` 또는 `docs/areas/`로 승격한다.

## 디렉토리 기준

```text
docs/           AI 작업자가 먼저 읽는 활성 문서
  current/      제품, 기능, 기술 기준
  areas/        영역별 설계와 모듈 경계
  goals/        실행 가능한 구현 계획
  runbooks/     운영 절차와 검증 명령
planning/       탐색 기획 보관
design/         디자인
development/    개발
  frontend/     프론트엔드
  backend/      백엔드
  infra/        인프라
archive/        보관 자료
```

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

## 제품 제약

- 첫 화면은 전체 inbox가 아니라 오늘 브리핑이다.
- 메일 카드는 스캔과 선택만 담당한다. 카드 안에 액션 버튼, New 배지, 판단 라벨, 컬러 바를 넣지 않는다.
- 원문 읽기와 Gmail 변경 액션은 상세 패널 또는 정리 검토 화면에서 처리한다.
- Gmail에 실제 변경이 생기면 변경 결과와 Undo 가능 여부를 명확히 보여준다.
- 기본 브리핑 섹션은 상태 파생 목록이고, 사용자가 직접 이동시키는 목적지는 Gmail `Maily/` 라벨과 동기화되는 라벨이다.
- AI 판단 이유는 기본으로 노출하지 않는다. 사용자는 이동, 라벨, 다음부터 여기로 액션으로 분류를 고친다.
- 확정 카피가 없으면 즉흥 작성하지 말고 `[미확정: 필요한 카피 설명]` placeholder를 둔다.

## 작성 위치

- 활성 제품/기능/기술 기준: `docs/current/`
- 영역별 설계/모듈 경계: `docs/areas/<area>/`
- 구현 계획/POC/TDD 계약: `docs/goals/`
- 운영 절차/검증 명령: `docs/runbooks/`
- 탐색 기획 문서: `planning/`
- 디자인 결정, 색상, 카피, 목업 보드: `design/`
- 프론트엔드 코드: `development/frontend/`
- 백엔드 코드: `development/backend/`
- 인프라 코드: `development/infra/`
- 과거 자료: `archive/`
