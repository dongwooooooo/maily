---
name: tdd
description: Maily 구현을 red→green→refactor로 진행. 새 백엔드/프론트 동작을 짤 때 사용. 백엔드는 backend-implementation-plan.md의 G0–G8 fake-TDD 순서를 따른다.
---

한 번에 한 동작. 테스트부터 쓴다.

## 1. Red
아직 없는 동작을 실패 테스트로 명세한다. 실행해서 **실패 이유가 '기능 없음'인지** 확인(다른 이유로 깨지면 테스트가 틀린 것).

- 백엔드: `pytest` (development/backend)
- 프론트: vitest 도입 시 그쪽, 아직 0개면 동작 명세를 이슈/주석으로

## 2. Green
테스트를 통과시키는 **최소** 구현. 그 이상 안 짠다.

## 3. Refactor
테스트 초록 유지하며 정리. 매 단계 테스트 재실행.

## 규칙

- 한 번에 한 동작. 요청 범위 밖 리팩터링 금지.
- 테스트 통과 전 완료 선언 금지 → 완료는 `/verify` 3층으로 확정.
- 백엔드 작업 순서·게이트는 `docs/goals/backend-implementation-plan.md`의 G0–G8을 따른다. Gmail Continuous Sync는 fake TDD(G2) 후 라이브 경로 IG1로 분리.
