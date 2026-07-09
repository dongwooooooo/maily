---
name: doc-audit
description: Maily 거버넌스·스펙 문서 전체를 크로스-문서 정합성 / 필수성 / 배치 규칙 3축으로 감사. 문서를 여러 개 고친 뒤, 또는 doc-guard 훅이 거버넌스 변경을 알릴 때 실행.
---

Maily 문서를 3축으로 감사한다. 결과는 우선순위별 findings 목록으로만 보고한다 — 이 스킬은 파일을 고치지 않는다.

## 단일 근거 맵 (위반 = 중복/드리프트)

| 규칙 | 원본 |
|---|---|
| 우선순위 스택 | `docs/CONTEXT.md` |
| 문서·코드 배치 | `AGENTS.md` "문서·코드 배치" |
| 제품 정의·원칙 | `PRODUCT.md` |
| 시각·컴포넌트 | `DESIGN.md` |
| 확정 카피 | `design/copy-principles.md` |

## 감사 축

1. **정합성**: 화면 수·사이드바 항목·스택 버전·계정 모델·섹션/라벨 모델·완료/나중에 파생상태·AI 이유 노출이 문서 간 일치하는가. 한 문서가 rename/폐지한 화면·용어를 다른 문서가 참조하는가.
2. **필수성**: 각 문서가 자기 역할 고유 내용만 담는가. 다른 문서 소유 내용을 복제하는가.
3. **배치**: 활성 기준 문서가 규칙 위치(`docs/current|areas|goals`)에 있는가.

## 실행

문서군별로 `doc-auditor` 서브에이전트를 병렬 디스패치한다. 각 에이전트는 findings 목록만 반환한다(수정 금지).

- 제품: `docs/current/product-wireframe-final.md` + `product-features.md`
- 기술: `docs/current/technical-foundation.md` + `development/*/README.md`
- 백엔드: `docs/areas/backend/*.md` + `docs/goals/backend-implementation-plan.md`
- 크로스-문서: 위 전부 + 루트 거버넌스 5종(`CLAUDE.md`·`AGENTS.md`·`README.md`·`PRODUCT.md`·`DESIGN.md`) + `docs/CONTEXT.md`·`docs/INDEX.md`

결과를 우선순위(Critical/Major/Minor)로 취합해 보고한다. 세부 스펙 수정은 사용자 결정 사항으로 남긴다.
