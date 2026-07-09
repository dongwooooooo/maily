# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 저장소 성격

AI 메일 비서 **Maily**(서비스명 확정)의 **기획·디자인·개발 저장소**. 저장소 전반 작업 규칙·디렉토리 기준·제품 제약은 `AGENTS.md`가 근거. 이 문서는 Claude Code 작업 시 추가로 필요한 내용만 담는다.

제품 정의는 `PRODUCT.md` 참조.

## 개발 명령

`AGENTS.md`의 개발 명령(루트에서 `pnpm frontend:dev` 등)을 그대로 쓴다.

- 버전 고정: node `24.18.x`, pnpm `11.10.x` (`package.json` engines)
- 테스트: 0개 (POC 단계). 방침·구성 규칙은 `@docs/current/technical-foundation.md`의 "테스트 방침" 참조
- 디자인 토큰 단일 소스: `development/frontend/src/styles/tokens.css` — `design/brand-color-final.md`에서 도출. 컴포넌트에서 hex 하드코딩 금지, `var(--...)` 토큰만 사용
- 현재 진입점은 `app-shell/MailyApp.tsx` + `app-shell/App.css` — 오늘 브리핑 3-pane 실화면(사이드바·상단 계정 스코프·목록·상세 패널·Undo toast)으로, `design/boards/v1/current/03-keystone.html`을 옮기는 작업이 진행 중이다

## 개발 harness (TDD·검증·디버깅)

- 작업 요청은 Context Pack으로 프레이밍한다: 목표 / 증거 / 관련 파일 / 수정 허용 범위 / 금지 경로 / 검증 명령.
- 구현은 `/tdd`(red→green→refactor). 완료 선언 전 `/verify`(자동·구조·반례 3층, `verifier` 서브에이전트로 독립 검증). 에러는 `/debug`(Symptom→Evidence→Hypotheses→Verification Loop, `debugger` 서브에이전트).
- 테스트 통과 전 완료 선언 금지. 만든 에이전트가 자기 작업을 채점하지 않는다.
- 강제 장치: `.env`·secrets·마이그레이션 편집은 settings.json `deny`, wireframes·`git push`는 `ask`.
- 백엔드 예외·로깅은 `docs/areas/backend/error-handling-and-logging.md`가 단일 근거. `.claude/hooks/log-guard.mjs`가 위반을 리마인드한다.

## 문서 구조와 근거 순서

우선순위 스택의 단일 근거는 `docs/CONTEXT.md`(Source-of-Truth Stack)다. 충돌 시 그 순서를 따른다.

## 작업 방식

- **결정은 실물로**: 미결 항목은 토론이 아니라 비교 보드/키스톤 스켈레톤을 만들어 보고 결정. 결과는 `DESIGN.md`를 갱신해 반영한다
- **확정 사항 재논의 금지**: 변경이 필요하면 `DESIGN.md`를 갱신하고 진행
- **대비 검증 반복**: 화면 추가 때마다 대비 확인 (AA는 차단이 아니라 측정·보고)
- 하이파이 목업에 로렘 입숨 금지 — 실카피·실제 길이의 제목/요약 사용

## 디자인 토큰

색상·타이포·레이아웃·컴포넌트·인터랙션 원칙과 금지 패턴은 `@DESIGN.md`가 단일 근거. 상세 팔레트·알파 체계는 `@design/brand-color-final.md`. 컴포넌트에서 hex 하드코딩 금지, `var(--...)` 토큰만 사용.

## 카피 규칙

확정 카피는 `@design/copy-principles.md`가 단일 근거. Gmail 변경 표기·`완료`/`나중에` 파생 상태·`이동` 재분류 규칙은 `copy-principles.md`와 `docs/current/product-wireframe-final.md`를 따른다.

- **카피 즉흥 생성 금지**: 안내문·빈 상태 문구·신뢰 문구·설명문 등 UI 카피는 새로 짓지 않는다. 확정 문구가 없으면 `[미확정: 필요한 카피 설명]` placeholder로 두고, 작업 완료 보고 시 미확정 카피 목록을 함께 보고한다. 예외: 가짜 메일 제목·요약·발신자 등 샘플 데이터는 실제 같은 내용으로 지어서 채운다(로렘 입숨 금지 규칙 대상).

## 프론트엔드 진행 상태

`@docs/areas/frontend/frontend-status.md` 참조 (IA 확정 요약, 포팅 진행상태, 열린 이슈).

## 디렉토리 구조

`AGENTS.md`의 "문서·코드 배치" 참조.
