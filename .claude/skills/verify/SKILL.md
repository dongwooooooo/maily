---
name: verify
description: 완료 선언 전 결과를 3층(자동/구조/반례)으로 검증. 구현을 끝냈다고 말하기 전 실행. 만든 에이전트가 자기 작업을 채점하지 않도록 verifier 서브에이전트로 독립 검증한다.
---

세 층을 모두 통과해야 완료다. 생성과 평가를 분리한다 — 구현한 쪽이 채점하지 않는다.

## 1. 자동 검증
- 백엔드: `pytest`, ruff/lint, 빌드
- 프론트: `pnpm lint`, `pnpm build` (vitest 도입 시 `pnpm test`)
- 하나라도 실패면 완료 아님.

## 2. 구조 검증 (diff 리뷰)
- `git diff --stat` — **예상한 파일만** 바뀌었나
- public API/인터페이스 변경 여부 — 의도된 것만
- secret/config 건드렸나 (`.env`, settings, 마이그레이션)

## 3. 반례 검증
- edge case 최소 1개 직접 실행
- race condition / 동시성 (Gmail Continuous Sync 중복 알림, 동시 정리 승인 등)
- prod 설정 차이 (로컬 fake vs 실제 OAuth/Gmail)

## 실행

`verifier` 서브에이전트에 변경 범위를 넘겨 3층 결과를 받는다. 판정은 PASS/FAIL + 층별 근거. FAIL이면 재현 가능한 최소 증거와 함께 `/debug`로 넘어간다.
