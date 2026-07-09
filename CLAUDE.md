# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 저장소 성격

AI 메일 비서 **Maily**(서비스명 확정)의 **기획·디자인·개발 저장소**. 활성 기준 문서는 `docs/`, 디자인 결정과 자산은 `design/`, 실제 코드는 `development/` 아래에서 관리한다. `planning/`은 탐색 기획 보관용이다.

## 개발 명령 (development/frontend/)

```bash
cd development/frontend
pnpm dev          # Next dev 서버 (localhost:3000)
pnpm build        # Next production build
pnpm lint         # ESLint
pnpm format       # Prettier 검사
pnpm format:write # Prettier 자동 수정
```

- 버전 고정: node `24.18.x`, pnpm `11.10.x` (`package.json` engines)
- 테스트: 0개 (POC 단계). 방침·구성 규칙은 `@docs/current/technical-foundation.md`의 "테스트 방침" 참조
- 디자인 토큰 단일 소스: `development/frontend/src/styles/tokens.css` — `design/brand-color-final.md`에서 도출. 컴포넌트에서 hex 하드코딩 금지, `var(--...)` 토큰만 사용
- 현재 진입점은 `app-shell/MailyApp.tsx` + `app-shell/App.css` — 오늘 브리핑 3-pane 실화면(사이드바·상단 계정 스코프·목록·상세 패널·Undo toast)으로, `design/boards/v1/current/03-keystone.html`을 옮기는 작업이 진행 중이다

제품: 여러 Gmail 계정의 중요 메일을 선별해 브리핑하는 웹 서비스. Gmail 대체가 아니라 그 위의 브리핑/우선순위/정리 레이어. 원문 확인·답장·발송은 Gmail에서 한다.

## 문서 구조와 근거 순서

충돌 시 아래 순서로 우선한다.

1. `docs/current/product-wireframe-final.md` — 제품 기획·와이어프레임 통합 최종본. 화면 10종 정의, 카드 문법, 브리핑 상태, Gmail 신뢰 원칙, 완료 체크리스트(§17)
2. `docs/current/product-features.md` — 사용자 기능 설명, MVP 범위, 백엔드 우선 POC 범위
3. `docs/current/technical-foundation.md` — 개발 스택, 디렉토리 구조, 실행 기준
4. `docs/areas/backend/module-boundaries.md` — 백엔드 모듈 경계와 모듈 간 기능 연결
5. `docs/goals/backend-implementation-plan.md` — 백엔드 세부 구현 작업, POC gate, TDD 순서
6. `design/wireframes/*.svg` — 로우파이 와이어프레임 11장 (00 플로우맵 + 화면 01~10). **동결됨 — 수정 금지.** 구조 변경은 목업에 직접 반영한다
7. `DESIGN.md` (루트) — 결정된 시각 방향과 금지 패턴 요약. 색상·타이포·레이아웃·컴포넌트·인터랙션 원칙의 단일 근거
8. `design/brand-color-final.md` — 확정 팔레트, 알파/상태 시스템, 접근성 체제, 기각 이력
9. `design/copy-principles.md` — 한국어 UI 확정 카피 (내비게이션·액션·신뢰 문구)
10. `design/boards/v1/current/*.html` + `shared.css` — 현재 하이파이 기준 목업 10장과 공용 스타일시트 (결정의 실물 근거)

## 작업 방식

- **결정은 실물로**: 미결 항목은 토론이 아니라 비교 보드/키스톤 스켈레톤을 만들어 보고 결정. 결과는 `DESIGN.md`를 갱신해 반영한다
- **확정 사항 재논의 금지**: 변경이 필요하면 `DESIGN.md`를 갱신하고 진행
- **대비 검증 반복**: 화면 추가 때마다 대비 확인 (AA는 차단이 아니라 측정·보고)
- 하이파이 목업에 로렘 입숨 금지 — 실카피·실제 길이의 제목/요약 사용

## 디자인 토큰

색상·타이포·레이아웃·컴포넌트·인터랙션 원칙과 금지 패턴은 `@DESIGN.md`가 단일 근거. 상세 팔레트·알파 체계는 `@design/brand-color-final.md`. 컴포넌트에서 hex 하드코딩 금지, `var(--...)` 토큰만 사용.

## 카피 규칙

확정 카피(내비게이션·액션·신뢰 문구)는 `@design/copy-principles.md`가 단일 근거.

동작 규칙:

- Gmail 변경 여부를 항상 명시: 변경 없음 = "브리핑만 생성했습니다. Gmail 변경은 없습니다.", 변경 시 과거형 + 시각 + Undo
- `완료`·`나중에`는 버튼이 아니라 **파생 상태**: 완료 = Gmail 읽음(또는 `Gmail도 읽음 처리` 실행) 결과, 나중에 = 읽음 확정 없음 상태. `이동`은 서비스 내부 섹션 재분류(Gmail 변경 아님). Gmail 변경은 상세 패널 액션 또는 정리 승인 화면에서만
- `Gmail`, `Inbox`, `Label`, 이메일 주소, 사용자 라벨은 원문 유지
- **카피 즉흥 생성 금지**: 안내문·빈 상태 문구·신뢰 문구·설명문 등 UI 카피는 새로 짓지 않는다. `design/copy-principles.md`에 확정 문구가 없으면 `[미확정: 필요한 카피 설명]` placeholder로 두고, 작업 완료 보고 시 미확정 카피 목록을 함께 보고한다. 예외: 가짜 메일 제목·요약·발신자 등 샘플 데이터는 실제 같은 내용으로 지어서 채운다(위 로렘 입숨 금지 규칙 대상)

## 프론트엔드 진행 상태

`@docs/current/frontend-status.md` 참조 (IA 확정 요약, 포팅 진행상태, 열린 이슈).

## 디렉토리 구조

```text
docs/
├─ INDEX.md          AI 작업자용 문서 라우터
├─ CONTEXT.md        현재 source-of-truth와 작업별 진입점
├─ current/          제품·기능·기술 기준
├─ areas/            영역별 설계와 모듈 경계
├─ goals/            실행 가능한 구현 계획
└─ runbooks/         운영 절차와 검증 명령
planning/            탐색 기획 보관
design/              브랜드 색상·카피 원칙·컴포넌트 인벤토리·보드·와이어프레임 (결정 로그·금지 패턴은 루트 DESIGN.md)
development/
├─ frontend/         프론트엔드 (Next.js 16 + React 19 + TS)
├─ backend/          백엔드 예정 영역
└─ infra/            인프라 예정 영역
archive/             프로젝트와 무관한 보관 문서
```
